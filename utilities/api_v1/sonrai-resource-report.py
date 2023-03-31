#!/usr/local/bin/python3
# This script provides a way for users to query the Sonrai API

# For more information on the GraphQL query format, open the
# search UI at https://crc.sonraisecurity.com/, select "Search" then click "Advanced Search".
# In the Advanced Search area, documentation is available to help build your searches.

# Dependencies:
# This script requires Python 3, as well as the requests and pyjwt libraries.
# The libraries can be installed by running:
#   pip3 install requests pyjwt
#   (OR)
#   pip3 install -r requirements.txt

# Environment Variables:
# TOKEN:   Authentication token for the GraphQL server
import datetime
import sys, logging
import os
import getopt
import json
import time
from datetime import datetime
from sonrai import SonraiApi

class ResourceQuery:

    def __init__(self):
        self.savedQueryName = None
        self.queryFileName = None # not required, just a placeholder
        self.swimlane = None
        self.queryName = "DefaultAPIQuery"
        self.queryVariables = "{}"
        self.outputMode="blob"
        self.ticketfile=None
        self.resourceMode="exclude"

        self.verbose=False

        self.loglevel = os.environ.get("LOGLEVEL", "INFO")
        self.logger = logging.getLogger("sonraiquery.py")
        self.logger.setLevel(self.loglevel)
        self.logger.info("logging level: " + self.loglevel)
        self.apiclient = SonraiApi(self.queryName, self.savedQueryName, self.queryFileName, self.queryVariables, self.outputMode)






    def print_usage(self):
        print("")
        print(" Usage:  ")
        print("   ./sonrai-resource-report.py --help")
        print("")
        print(" Options:")
        print("   -h, --help                  Show this message.")
        print("   --ticketfile [filename]     if exist, load tickets from here, if not exists, save ticket results to file.")
        print("   -v                          verbose logging.")
        print("   -i                          include mode.  see main() for [includeResourceTypes] list. ")
        print("   -x (default)                exclude mode.  see main() for [excludeResourceType] list. overrides -i")


        print("")
        print(" Environment variables:")
        print("   TOKEN                   Sonrai API auth token")
        print("   LOGLEVEL                ERROR, INFO, DEBUG - INFO is enabled by default")
        print("")


    def getTickets(self):
        # setup an API client

        ticketlimit=1000
        lessthanlimit = False
        offset = 0
        alltickets = []

        # valid status types = ['NEW','CLOSED','RISK_ACCEPTED','SNOOZED']
        # status: {op: IN_LIST values: [ "NEW","CLOSED","RISK_ACCEPTED","SNOOZED" ]}
        # status: {op: IN_LIST values: [ "RISK_ACCEPTED" ]}

        graphql='''
            query loadTickets ($limit: Long, $offset: Long) 
            { Tickets ( where: {
                status: {op: IN_LIST values: [ "NEW","CLOSED","RISK_ACCEPTED","SNOOZED" ]}
                # optional ticket key = policy or framwork srn
                # ticketKey: {value: "srn:integra::ControlFramework/906e8284-0733-4de5-b0db-9ab1098ae7d2"}
           }) 
             {
               count
               items (limit: $limit, offset: $offset) {
                 title
                 srn
                 ticketKey
                 ticketType
                 resourceName
                 resourceSRN
                 resourceLabel
                 status
               }
             }
           }          
        '''

        if self.ticketfile != None:
            # if file exists, load from file
            if os.path.isfile(self.ticketfile):
                with open(self.ticketfile) as json_tickets:
                    alltickets = json.load(json_tickets)
                    if self.verbose:
                        print("## loading tickets from file: " + str(self.ticketfile))
                    return alltickets

        if self.verbose:
            print("## loading tickets ("+str(ticketlimit) + " per .): ", end="")

        self.queryVariables = json.dumps({"limit": ticketlimit, "offset":  offset } )
        while not lessthanlimit:
            self.result=self.apiclient.executeQuery(graphql,self.queryVariables)
            results = self.result["data"]["Tickets"]["items"]
            if results is not None:
                alltickets.extend(results)
            else:
                lessthanlimit = True
                if self.verbose:
                    print("results=None", end="", flush=True )

            if len(results) < ticketlimit:
                    lessthanlimit = True

            if self.verbose:
                print(".", end="", flush=True )
            offset += ticketlimit
            self.queryVariables = json.dumps({"limit": ticketlimit, "offset":  offset } )

        print("")
        
        if self.ticketfile != None and not os.path.isfile(self.ticketfile):
            # save to disk
            if self.verbose:
                print("## saving tickets to file: " + str(self.ticketfile))
            with open(self.ticketfile,'w') as save_json_tickets:
                json.dump(alltickets,save_json_tickets)
        return alltickets


    def loadPolicies(self):
        # load policies from all enabled frameworks
        policyreport = {}
        basecards = []

        graphql='''
query controlpoliciesnsearches { ControlPolicies ( 
    where: {
    containedByControlFramework: { items: {
      enabled: { value: true }
      # optional - filter by a framework
      # srn: {value: "frameworksrn"}
    }}}
) {
    count
    items (limit: -1) {
        srn
        title
        contains { items {
            srn
            name
            ... on Search {
                    query
                }
        }}
  }
}}           
        '''
        activepolicies=self.apiclient.executeQuery(graphql)


        # for each search, get the search name, base card and policy srn

        for policy in activepolicies['data']['ControlPolicies']['items']:
            policysrn = policy['srn']
            policyreport[policysrn] = {}
            policyreport[policysrn]['srn'] = policy['srn']
            policyreport[policysrn]['title'] = policy['title']

            searchsrn = policy['contains']['items'][0]['srn']
            if not "SavedQuery" in searchsrn:
                querycards = policy['contains']['items'][0]['query']['fields']
                for entry in querycards:
                    # find the entry that doesn't have a parent id - that's the base card
                    # happy path - there must always be one!
                    if not 'parentId' in querycards[entry].keys():
                        rootCard = querycards[entry]['definition']['name']
                        policyreport[policysrn]['searchbasecard'] = rootCard
                        if not rootCard in basecards:
                            basecards.append(rootCard)

            else:
                # advanced search, skip
                next


        return policyreport, basecards


    def getResources(self, basecardtype):
        # setup an API client
        resourcelimit = 1000
        resourceCount = 0
        lessthanlimit = False
        offset = 0
        resources = []


        graphql='''
        query getResources ($limit: Int, $offset: Int) 
            { resource: ''' + basecardtype + ''' ( where: {
            active: { value: true }
            isPopulated: {value: true }
          }) { 
            count 
            items (limit: $limit, offset: $offset) {
              name
              srn
              resourceId
            }
          }}
        '''

        #if self.verbose:
        #    print(len(resources))

        self.queryVariables = json.dumps({"limit": resourcelimit, "offset":  offset } )
        while not lessthanlimit:
            self.result=self.apiclient.executeQuery(graphql,self.queryVariables)
            resourceCount = int(self.result["data"]["resource"]["count"])
            if resourceCount == 0:
                # none of these resources, return zero and next
                return 0,[]

            results = self.result["data"]["resource"]["items"]

            if results is not None:
                resources.extend(results)
            else:
                lessthanlimit = True
                if self.verbose:
                    print("results=None", end="", flush=True )


            if self.verbose:
                mycount = len(resources)
                percent = int((mycount/resourceCount)*100)
                print("# Loading " + basecardtype + ": "+str(resourceCount)+" / %d%%\r" %percent, end="")

            if len(results) < resourcelimit:
                lessthanlimit = True

            offset += resourcelimit
            self.queryVariables = json.dumps({"limit": resourcelimit, "offset":  offset } )



        print("")
        return resourceCount, resources


    def scanTicketsForResource(self, alltickets, resourcesrn):
        results = []
        # print("checking for - " + resourcesrn)

        for ticket in alltickets:
            # print(ticket)
            # time.sleep(1)
            if ticket['resourceSRN'] == resourcesrn:
                results.append(ticket['title'])

        return results

    def reportresults (self, reportbasecards, allResources, alltickets, resourceCounts):
        # for each resource type
        for resourcetype in reportbasecards:
            # count of resources
            print("##################################################################")
            print("Resource Type - " + str(resourcetype) + " - " + str(resourceCounts[resourcetype]))
            print(" ---------------------------------------------")
            for resource in allResources[resourcetype]:
                # print the resources,
                if resource['name'] == None:
                    namestring="None"
                else:
                    namestring = str(resource['name'])

                if resource['resourceId'] == None:
                    resourceidstring="None"
                else:
                    resourceidstring = str(resource['resourceId'])


                print(" Resource Name:    " + namestring)
                print(" SRN:              " + resource['srn'])
                print(" Cloud ResourceID: " + resourceidstring)
                print(" ------ ")

                resourcetickets = self.scanTicketsForResource(alltickets, resource['srn'])
                if resourcetickets == []:
                    print(" Tickets: None ")
                else:
                    print(" Tickets: " + str(len(resourcetickets)))
                    # print resourcetickets
                    print(" Policies: ")
                    for policytitle in resourcetickets:
                        if policytitle == None:
                            print("  .. untitled or deleted policy ticket ")
                        else:
                            print("  " + policytitle)

                print("")
                print("# ---------------------------------------------")
                # time.sleep(0.1)

            print("# ---------------------------------------------")



    def main (self, argv):

        # Include/Exclude mode.   Depending on which mode you choose, this script will
        # - include - only INCLUDE resource types in the "includeResourceTypes" list
        # - exluce - SKIP the resource types in the "excludeResourceTypes" list
        includeResourceTypes = ["Accounts"]
        excludeResourceTypes = ["AnalyticsResults", "Actions", "PermissionLists", "Policies", "Findings", "Resources"]

        try:
            opts, args = getopt.getopt(argv,'vhix', ["help","ticketfile="])
        except getopt.GetoptError as err:
            print(err)
            self.print_usage()
            sys.exit()

            #     # get the command line options mapped
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                self.print_usage()
                sys.exit()
            if opt in ("-v"):
                self.verbose=True
            if opt in ("--ticketfile"):
                self.ticketfile = arg
            if opt in ("-i"):
                self.resourceMode = "include"
            if opt in ("-x"):
                self.resourceMode = "exclude"



        resourceCounts = {}
        allResources = {}

        # step 1 - get list of searches for enabled policies & frameworks
        if self.verbose:
            curentdate = now = datetime.now()
            dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
            print("# date / time =", dt_string)


        print("# enabled policies: ", end="", flush=True )
        policyreport, basecards = self.loadPolicies()
        print(len(policyreport))

        # next - get counts for each of these base resource types, and the resources
        print("# resources types: " + str(len(basecards)))

        reportbasecards = []
        totalresourcecount=0

        for resourcetype in basecards:
            # print(resourcetype)
            if self.resourceMode == "include" and resourcetype in includeResourceTypes:
                # print("only")
                resourceCounts[resourcetype],allResources[resourcetype] = self.getResources(resourcetype)
                totalresourcecount += len(allResources[resourcetype])
                reportbasecards.append(resourcetype)

            elif self.resourceMode == "exclude" and resourcetype in excludeResourceTypes:
                # print("elseif not only and ignore")
                next

            elif self.resourceMode == "exclude" and resourcetype not in excludeResourceTypes:
                # print("else not only and not ignore")
                resourceCounts[resourcetype],allResources[resourcetype] = self.getResources(resourcetype)
                totalresourcecount += len(allResources[resourcetype])
                reportbasecards.append(resourcetype)
            # else:
                # print("no resource types selected")

        print("# total number of resources: " + str(totalresourcecount))


        # get dump of tickets, paging through
        alltickets=(self.getTickets())
        print("# number of tickets: " + str(len(alltickets)))

        # output
        self.reportresults(reportbasecards, allResources, alltickets, resourceCounts)





HANDLER=None

# def handle(event, context):
def handle(myargv):
    global HANDLER
    if not HANDLER:
        HANDLER = ResourceQuery()
    HANDLER.main(myargv)

if __name__ == "__main__":
    handle(sys.argv[1:])
