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

import sys, logging
import os
import json
import getopt
import re
from sonrai import SonraiApi

class policyDiff:

    def __init__(self):
        self.savedQueryName = None
        self.Framework = None
        self.queryFileName = None
        self.queryName = "DefaultAPIQuery"
        self.queryVariables = "{}"
        self.outputMode="blob"

        self.loglevel=os.environ.get("LOGLEVEL", "INFO")
        self.logger=logging.getLogger("sonraiquery.py")
        self.logger.setLevel(self.loglevel)
        self.logger.info("logging level: " + self.loglevel)

        try:
            opts, args = getopt.getopt(sys.argv[1:],'blhdf:', ["blob","linebyline", "help", "debug", "framework="] )
        except getopt.GetoptError as err:
            print(err)
            self.print_usage()
            sys.exit()

        # get the command line options mapped
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                self.print_usage()
                sys.exit()
            elif opt in ("-f", "--framework"):
                self.Framework = arg
            elif opt in ("-d", "--debug"):
                self.logger.setLevel("DEBUG")
            # else:
                # assert False, "unhandled error"

        if self.queryVariables !=  "{}":
            try:
                json.loads(self.queryVariables)
            except Exception as e:
                self.logger.error("Argument passed to -v/--vars is not valid JSON.")
                self.logger.error("Example of valid JSON on the command line would be: '{\"key\": \"value\"}'")
                self.print_usage()
                exit()

    def print_usage(self):
        print("")
        print(" Usage:  ")
        print("   ./sonrai-policy-diff.py.py [--debug] [--framework <frameworkname>] ")
        print("   ./sonrai-policy-diff.py.py --help")
        print("")
        print(" Options:")
        print("   -h, --help                  Show this message.")
        print("   -f <name>, --framework <name>   Search on Framework <name> (in double quotes.")
        print("")
        print(" Environment variables:")
        print("   TOKEN                   Sonrai API auth token")
        print("   LOGLEVEL                ERROR, INFO, DEBUG - INFO is enabled by default")
        print("")

    def createFrameworkQuery (self, Framework, tenant):
        if tenant == 'tenant':
            query = 'query tenantFrameworks'
        elif tenant == 'sonrai':
            query = 'query sonraiFrameworks'

        query += ''' 
           {
                ControlFrameworks 
                (where: { 
                srn: {op:CONTAINS value:"srn:supersonrai"}
        '''
        regexFilter = 'srn: {op:REGEX value:"srn:supersonrai::ControlFramework\/.*\/.*"} '
        if tenant == 'tenant':
            query += regexFilter

        elif tenant == 'sonrai':
            query += ' not: { ' + regexFilter + ' } '

        if Framework is not None:
           query  += '\n title: {op:EQ value:"' + Framework + '" } '

        query += '''
          }
          )
          {
    count
    items (limit: -1) {
      title
      srn
      contains {count items (limit: -1) {
        title
        srn
        createdDate
      }}
    }
  }
  }
        '''
        #print (query)
        return query


    def main (self):
        # setup an API client
        self.client = SonraiApi(self.queryName, self.savedQueryName, self.queryFileName, self.queryVariables, self.outputMode)

        # execute the query to find the tenant's version of the framework
        self.tenantFrameworkQuery = self.createFrameworkQuery(self.Framework, "tenant")
        resultsTenant = self.client.executeQuery(self.tenantFrameworkQuery)

        # execute the query to find the SuperSonrai version of the framework
        self.sonraiFrameworkQuery = self.createFrameworkQuery(self.Framework, "sonrai")
        resultsSonrai = self.client.executeQuery(self.sonraiFrameworkQuery)

        # Build the tenant version into a more usable format.
        resultsTenantItems = resultsTenant['data']['ControlFrameworks']['items']
        resultsTenantCount = resultsTenant['data']['ControlFrameworks']['count']
        frameworkTenant = {}
        srnPattern = re.compile('srn:supersonrai::ControlFramework\/\w+\-\w+\-\w+\-\w+\-\w+')
        for frameworksCounter in range(resultsTenantCount):
            #loop through all frameworks
            policiesTenantItems = resultsTenantItems[frameworksCounter]['contains']['items']
            policiesTenantCount = resultsTenantItems[frameworksCounter]['contains']['count']
            childFrameworkSRN = resultsTenantItems[frameworksCounter]['srn']
            # convert the child framework SRN to the same as the parent framework SRN
            frameworkSRN = srnPattern.findall(childFrameworkSRN)[0]
            frameworkTenant[frameworkSRN] = {}
            frameworkTenant[frameworkSRN]['title'] = resultsTenantItems[frameworksCounter]['title']
            # add the child Framework SRN into this for faster processing later
            frameworkTenant[frameworkSRN]['childFrameworkSRN'] = childFrameworkSRN

            for policyCounter in range(policiesTenantCount):
                #loop through all policies
                policySRN = policiesTenantItems[policyCounter]['srn']
                policyTitle = policiesTenantItems[policyCounter]['title']
                policyCreatedDate = policiesTenantItems[policyCounter]['createdDate']
                frameworkTenant[frameworkSRN][policySRN] = {}
                frameworkTenant[frameworkSRN][policySRN]['title'] = policyTitle
                frameworkTenant[frameworkSRN][policySRN]['createdDate'] = policyCreatedDate

        # Build the Sonrai version into a more usable format.
        resultsSonraiItems = resultsSonrai['data']['ControlFrameworks']['items']
        resultsSonraiCount = resultsSonrai['data']['ControlFrameworks']['count']
        frameworkSonrai = {}
        for frameworksCounter in range(resultsSonraiCount):
            #loop through all frameworks
            policiesSonraiItems = resultsSonraiItems[frameworksCounter]['contains']['items']
            policiesSonraiCount = resultsSonraiItems[frameworksCounter]['contains']['count']
            frameworkSRN = resultsSonraiItems[frameworksCounter]['srn']
            frameworkSonrai[frameworkSRN] = {}
            frameworkSonrai[frameworkSRN]['title'] = resultsSonraiItems[frameworksCounter]['title']
            for policyCounter in range(policiesSonraiCount):
                #loop through all policies
                policySRN = policiesSonraiItems[policyCounter]['srn']
                policyTitle = policiesSonraiItems[policyCounter]['title']
                policyCreatedDate = policiesSonraiItems[policyCounter]['createdDate']
                frameworkSonrai[frameworkSRN][policySRN] = {}
                frameworkSonrai[frameworkSRN][policySRN]['title'] = policyTitle
                frameworkSonrai[frameworkSRN][policySRN]['createdDate'] = policyCreatedDate


        # time to compare the 2 frameworks.  Need 2 comparison.
        # New ones in Sonrai Framework and then new different ones in tenant's framework

        # new Sonrai Policies first
        for fwSRN in frameworkSonrai:
            if fwSRN in frameworkTenant:
                # Framework is configured both superSonrai and customer
                print (frameworkSonrai[fwSRN]['title'])
                polNotFoundCount = 0
                tenPolNotFound = {}
                for polSRN in frameworkSonrai[fwSRN]:
                    if polSRN in frameworkTenant[fwSRN]:
                       # matching policy
                       pass
                    else:
                       polNotFoundCount += 1
                       tenPolNotFound[polSRN] = {}
                       tenPolNotFound[polSRN] = frameworkSonrai[fwSRN][polSRN]
                if polNotFoundCount > 0:
                    print ("https://app.sonraisecurity.com/App/ControlCenter/ControlGroup?controlGroupId="+frameworkTenant[fwSRN]['childFrameworkSRN'])
                    print ("Found the following " + str(polNotFoundCount) + " policies missing from tenant's Framework")
                    for srn in tenPolNotFound:
                       print (tenPolNotFound[srn])
                else:
                    print ("All policies Match")

            else:
                #print ("This framework is not enabled for tenant: " + frameworkSonrai[fwSRN]['title'])
                pass

            print () # add blank line between frameworks


HANDLER=None

# def handle(event, context):
def handle(myargv):
    global HANDLER
    if not HANDLER:
        HANDLER = policyDiff()
    HANDLER.main()

if __name__ == "__main__":
    handle(sys.argv[1:])
