#!/usr/local/bin/python3
import os
import sys
import getopt
import logging
import json
import time
import sonrai
import datetime as dt
from datetime import timedelta


# requires an SRN for a swimlane in order to find & close tickets.
# get srn from commandline, otherwise, print help
# also requires a token, either generic "api" token, or user token, which
# can be retrieved using "window.aat" in the browser console after logging in.
# note - user token will expire after 15 minutes if not kept active, where the
# api token is good for 1 day.

class TicketHandler():

   def __init__(self):
      global URL

      self.nocheckcertificate = False
      self.logger=logging.getLogger("closetickets.py")
      self.loglevel=os.environ.get("LOGLEVEL", "INFO")
      logging.basicConfig(level=self.loglevel,
                          format="%(asctime)s:%(name)s:%(funcName)s:%(levelname)s: %(message)s"
                          )

   # def iterTickets(self, swimlanesrn)

   def closeTickets(self, ticketsrns, testonly):
      variables = json.dumps( {"ticketsrns": ticketsrns  })

      ticketmutation = '''
               mutation close_tickets($ticketsrns: [String]) {
                  CloseTickets(input: { srns: $ticketsrns }) {
                     successCount
                     failureCount
                  }
               }
           '''
      self.logger.debug(" calling api to close " + str(len(ticketsrns)) + " tickets")
      QUERY_NAME = "TicketsAPI_CloseTickets"
      POST_FIELDS = {"query": ticketmutation, "variables": variables }
      POST_FIELDS = json.dumps(POST_FIELDS)

      if testonly is True:
         self.logger.info("testing only, close ticket call to Sonrai disabled")
         return  json.dumps( {"testing enabled": "no tickets closed" } )
      else:
         self.CloseTicketsJSON =self.sonrai.SonraiGraphQLQuery(self.ApiURL,POST_FIELDS,QUERY_NAME,self.apitoken)
         return self.CloseTicketsJSON

   def addCommentToTickets(self, ticketsrns, comment, userSrn, testonly ):
      # build the variable needed for the ticket Comments
      ticketList = ""
      for srn in ticketsrns:
        ticketList += ('{"ticketSrn":"' + srn + '", "createdBy":"' + userSrn + '", "body":"' + comment + '"},')

      variables =  ('{"requests": [' + ticketList[:-1] + ']}' )

      mutationAddComment = '''
         mutation CreateTicketCommentBulk($requests: [CreateTicketCommentRequestInput]) {
            CreateTicketCommentBulk(input: {requests: $requests}) {
               results {
                 ticketComment {
                   srn
                 }
                 success
                 error
               }
             }
           }
      '''
      self.logger.debug( " calling api to add comment on " + str(len(ticketsrns)) + " tickets")
      QUERY_NAME = "TicketsAPI_AddComment"
      POST_FIELDS = {"query": mutationAddComment, "variables": variables}
      POST_FIELDS = json.dumps(POST_FIELDS)

      if testonly is True:
         self.logger.info("testing only, adding comment to tickets call to Sonrai disabled")
         results = json.dumps({"testing enabled": "no comments on tickets"})
      else:
         self.TicketCommentJSON = self.sonrai.SonraiGraphQLQuery(self.ApiURL, POST_FIELDS, QUERY_NAME, self.apitoken)
         results = json.dumps(self.TicketCommentJSON)

      if "errors" in results:
         self.logger.error("Could not add comment, exiting with following error:")
         self.logger.error(results)
         sys.exit(8)

      return results


   def queryTickets(self, swimlanesrns, limit, hoursFlag, ticketAge, ticketKey, resourceSRN, allswimlanesflag, printquery, severityLower, severityUpper ):

      ticketKeyFilter=""
      now = int(time.time())
      lastModifiedTimeStamp = now - (int(ticketAge) * 3600)

      # determine lastModifiedTimeStamp filter
      if hoursFlag == "LT":
         # lastModified LT (now - ticketAge x hours)
         lastModifiedFilter = { "op": "LT", "value": lastModifiedTimeStamp }

      elif hoursFlag == "GT":
         # lastModified GT (now - ticketAge x hours)
         lastModifiedFilter = { "op": "GT", "value": lastModifiedTimeStamp }

      else:
         # lastModified LT (now)
         lastModifiedFilter = { "op": "LT", "value": now }

      # determine "ticketKey" filter
      if ticketKey != "":
         ticketKeyFilter = { "value": ticketKey }
      else:
         ticketKeyFilter = { "op": "NEQ", "value": "null" }

      # determine "resourceSRN" filter
      if resourceSRN != "":
         resourceSRNFilter = { "value": resourceSRN }
      else:
         resourceSRNFilter = { "op": "NEQ", "value": "null" }

      if allswimlanesflag is True:
         srnFilter = { "op": "NEQ", "value": "" }
      else:
         srnFilter = {"op": "IN_LIST", "values": [swimlanesrns] }


      variables = json.dumps( {
         "srns": srnFilter,
         "limit": limit,
         "lastModified": lastModifiedFilter,
         "ticketKey": ticketKeyFilter,
         "resourceSRN": resourceSRNFilter,
         "severityUpper": severityUpper,
         "severityLower": severityLower


            })

      # notes: orderby on tickets only supports "createdDate"
      #
      ticketquery = '''
           query SonraiPolicyTicketsQuery
               ( 
               $srns: Logical,
               $limit: Long, 
               $lastModified: DateLogical, 
               $ticketKey: Logical,
               $resourceSRN: Logical
               $severityLower: Long
               $severityUpper: Long
               )
               { Tickets
                   ( where: {
                       swimlaneSrns: $srns
                       status: {op: EQ value: "NEW"}
                       ticketType: {op: NEQ value: "Custom"}
                       lastModified: $lastModified
                       ticketKey: $ticketKey
                       resourceSRN: $resourceSRN
                       and: [
                           { severityNumeric:{ op: GT value: $severityLower} }
                           { severityNumeric: {op: LT value: $severityUpper} }
                       ]
                   })
                   {
                       count
                       items (
                           limit: $limit 
                           orderBy: {createdDate: {order: DESC}}
                       ) {
                           TicketSRN: srn
                           lastModified
                           lastModifiedtimestamp: lastModified @formatDateTime(epochSecond: true)
                           resource {
                               active
                           }
                       }
                   }
           }
           '''
      if printquery is True:
         print("\nquery\n" + ticketquery + "\n")
         print("\nvariables\n" + variables + "\n")

      # self.ticketResponse = self.sonrai.executeQuery(self, ticketquery)
      if allswimlanesflag:
         self.logger.info("calling api for tickets in all swimlanes")
      else:
         self.logger.info("calling api for tickets in swimlane: " + swimlanesrns )

      QUERY_NAME = "TicketsAPIQuery"
      POST_FIELDS = {"query": ticketquery, "variables": variables }
      POST_FIELDS = json.dumps(POST_FIELDS)

      self.SwimlaneTicketsJSON =self.sonrai.SonraiGraphQLQuery(self.ApiURL,POST_FIELDS,QUERY_NAME,self.apitoken)
      return self.SwimlaneTicketsJSON


   def help(self):
      print("Usage: closetickets.py [options]")
      print(" example:      ")
      print("   closetickets.py -g -i ")
      print("    closes tickets from global swimlane, where the resource is currently inactive,")
      print("    starting with the 50 most recent tickets ")
      print(" ")
      print(" -h                   - help ")
      print(" -f <ticketkeySRN>    - close tickets where ticketKey ControlPolicySRN or ControlFrameworkSRN ")
      print(" -m <number>          - retrieve <number> maximum tickets from sonrai api")
      print(" -a                   - close tickets where resourcs are active ")
      print(" -i                   - close tickets where resoures are inactive (deleted from cloud) ")
      print("                        one or both of -a or -i are required  ")
      print(" --all-swimlanes      - no swimlane filter, any tickets     ")
      print("                        overrides -g / -s ")
      print(" -g                   - close tickets in Global swimlane.  overrides -s [swimlane] option ")
      print(" -s <swimlaneSRN>     - close tickets in swimlane <swimlaneSRN> ")
      print("                        one of --all-swimlanes, -g or -s <swimlane> is required  ")
      print(" -r <resourceSRN>     - close tickets for <resourceSRN> ")
      print(" -l </path/filename>  - log closed ticket SRNs to file </path/filename>")
      print(" -n <hours>           - close tickets with lastModified time NEWER than <hours> hours ago. ")
      print(" -o <hours>           - close tickets with lastModified time OLDER than <hours> hours ago. ")
      print("                        only ONE of -n or -o is permitted  ")
      print(" -c \"<comment>\"     - add momment to ticket before closing. Comment must be in quotation marks")
      print(" -u <userSRN>         - SRN of user adding comment. Used in conjunction with the -c option.")
      print("                        Must be same user as the user that created the token")
      print("")
      print(" --no-check-certificate  - disable ssl verification to sonrai api (ie, ssl interception proxy) ")
      print(" --testonly             - do not close tickets, only output what would be updated. ")
      print(" --printquery           - print out graphql query and variables ")
      print(" --maxclose-per-request - maximum number of tickets to close per request.  default:50    ")
      print(" --severityUpper        - close tickets BELOW severity of N.  Default: 100               ")
      print(" --severityLower        - close tickets ABOVE severity of N.  Default: 0                 ")
      print("")
      print("  view closetickets_README.md for additional information ")


   def main(self,argv):
      # __init__(self=)

      resourceSRN = ''
      swimlaneSRN = ''
      maxticketsquerylimit = 50
      maxClosePerRequest=50
      ticketCount = 0
      closeTicketsList=[]
      ticketcloseresponse=""
      globalSwimlaneSRN = False
      logClosedTicketIDs = False
      allswimlanesflag=False
      ticketlog = ""
      ticketlogfile = ""
      ticketComment = None
      userSrn = None
      closeInactiveTickets = False
      closeActiveTickets = False
      printquery=False
      olderTickets=False
      newerTickets=False
      hoursFlag=""
      ticketAge=0
      ticketKey=""
      testonly=False
      resourceSRN=""
      severityUpper=100
      severityLower=0

      try:
         opts, args = getopt.getopt(argv,"hf:l:c:giam:r:s:n:o:u:",['testonly','maxclose-per-request=','all-swimlanes','printquery','no-check-certificate', "severityLower=", "severityUpper="])
      except getopt.GetoptError as err:
         print(err)
         self.help()
         sys.exit()

      swimlaneSRN = ""
      for opt, arg in opts:
         if opt == '-h':
            self.help()
            sys.exit()
         elif opt in ("-s"):
            swimlaneSRN = arg
            self.logger.info("## closing tickets on swimlane srn: " + arg )
         elif opt in ("-r"):
            resourceSRN = arg
            self.logger.info("## closing tickets on resource srn: " + arg )
         elif opt in ("-g") and allswimlanesflag is False:
            globalSwimlaneSRN = True
            self.logger.info("## closing tickets on global swimlane")
         elif opt in ("-m"):
            maxticketsquerylimit = arg
            self.logger.info("## max tickets: " + arg)
         elif opt in ("-c"):
            ticketComment = arg
            self.logger.info("## Comment to add to all closed tickets: " + arg)
         elif opt in ("-u"):
            userSrn = arg
            self.logger.info("## User to attribute comment to " + arg)
         elif opt in ("--no-check-certificate"):
            self.nocheckcertificate = True
            self.logger.info("## SSL verification disabled")
         elif opt in ("-l"):
            logClosedTicketIDs = True
            ticketlogfile = arg
            self.logger.info("## closed ticket srn logging enabled")
         elif opt in ("-n"):
            newerTickets=True
            hoursFlag="GT" # NEWER than N hours ago
            ticketAge = int(arg)
            self.logger.info("## closed tickets NEWER than: " + arg + " hours" )
         elif opt in ("-o"):
            olderTickets=True
            hoursFlag="LT" # OLDER than N hours ago
            ticketAge = int(arg)
            self.logger.info("## closed tickets OLDER than: " + arg + " hours" )
         elif opt in ("-i"):
            closeInactiveTickets = True
            self.logger.info("## closing tickets on INACTIVE resources")
         elif opt in ("-a"):
            closeActiveTickets = True
            self.logger.info("## closing tickets on ACTIVE resources")
         elif opt in ("-f"):
            ticketKey = arg
            self.logger.info("## closing tickets for policy/framework srn: " + arg)
         elif opt in ("--testonly"):
            testonly = True
            self.logger.info("## testing only - no tickets will be closed ")
         elif opt in ("--printquery"):
            printquery = True
            self.logger.info("## query output enabled ")
         elif opt in ("--maxclose-per-request"):
            maxClosePerRequest = arg
            self.logger.info("## maxclose-per-request: " + arg)
         elif opt in ("--all-swimlanes"):
            self.logger.info("## closing tickets on ALL swimlane - OVERRIDING -g, -s swimlane")
            allswimlanesflag=True
         elif opt in ("--severityUpper"):
            severityUpper = arg
            self.logger.info("## severityUpper: " + arg)
         elif opt in ("--severityLower"):
            severityLower = arg
            self.logger.info("## severityLower: " + arg)


      if swimlaneSRN == "" and not globalSwimlaneSRN and not allswimlanesflag:
         self.logger.error("No swimlane specified")
         self.help()
         sys.exit()

      # require one of "inactive" or "active" flags
      if closeInactiveTickets is False and closeActiveTickets is False:
         self.logger.error("must indicate at least one of tickets with -i/inactive and/or -a/active resources to close ")
         self.help()
         sys.exit()

      # if there is a comment included but the user SRN isn't exit
      if ticketComment is not None and userSrn is None:
         self.logger.error("must include user's SRN when trying to add a comment to tickets")
         self.help()
         sys.exit()

      # only one of "older" or "newer" is permitted
      if newerTickets is True and olderTickets is True:
         self.logger.error("must indicate only one -n/newer or -o/older tickets to close ")
         self.help()
         sys.exit()

      # find api token, api server, setup client connection
      self.ENV_TOKEN = os.environ.get("TOKEN",None)
      self.sonrai = sonrai.SonraiApi()
      self.apitoken = self.sonrai.getToken()
      self.ApiURL = self.sonrai.getGraphQLUrl(self.apitoken)

      if globalSwimlaneSRN is True and allswimlanesflag is False:
         self.logger.info("Closing tickets in Global swimlane ")
         org = self.sonrai.tokenOrg(self.apitoken)
         swimlaneSRN = "srn:" + org + "::Swimlane/Global"

      if self.nocheckcertificate is True:
         self.sonrai.verify(False)

      now = int(time.time())
      lastModifiedTimeStamp = now - (int(ticketAge) * 3600)
      lastModifiedDateTime = time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(lastModifiedTimeStamp))


      self.logger.debug(f'Checking for tickets where: ')
      self.logger.debug(f' - lastModified timestamp is {hoursFlag} {ticketAge} hours ago ')
      self.logger.debug(f'   (LT=older, GT=newer) (ticket.lastModified {hoursFlag} {lastModifiedTimeStamp} / {lastModifiedDateTime}) ')
      self.logger.debug(f' - ticketKey is "{ticketKey}" ')
      self.logger.debug(f'   control policy SRN or control framework SRN ')
      self.logger.debug(f' - resourceSRN is "{resourceSRN}"  ')
      self.logger.debug(f' - testonly: {testonly}  ')
      self.logger.debug(f' - maxclose-per-request: {maxClosePerRequest} ')
      self.logger.debug(f' - severityLower: {severityLower}  ')
      self.logger.debug(f' - severityUpper: {severityUpper}  ')



      self.logger.info("Finding up to " + str(maxticketsquerylimit) + " tickets for swimlane " + swimlaneSRN)
      SwimlaneTickets= self.queryTickets(swimlaneSRN, maxticketsquerylimit, hoursFlag, ticketAge, ticketKey, resourceSRN, allswimlanesflag, printquery, severityLower, severityUpper)

      # graphql error response checks
      if "data" not in SwimlaneTickets:
         self.logger.error("No data block in query result")
         self.logger.error(json.dumps(SwimlaneTickets))
         sys.exit(5)
      elif "errors" in SwimlaneTickets:
         self.logger.error("Error message received:")
         self.logger.error(json.dumps(SwimlaneTickets))
         sys.exit(6)
      elif SwimlaneTickets is None:
         self.logger.error("SwimlaneTickets result object == none ")
         sys.exit(7)


      # print # of results from "count"
      self.logger.info("Open tickets found: " + str(SwimlaneTickets["data"]["Tickets"]["count"]) )
      if int(SwimlaneTickets["data"]["Tickets"]["count"]) < int(maxticketsquerylimit):
         self.logger.info("(tickets found < requested maxTickets - this indicates all open tickets reviewed, see readme for additional details) ")

      if logClosedTicketIDs is True:
         if os.path.exists(ticketlogfile):
            self.logger.info("Ticket srn logging enabled")
            ticketlog = open(ticketlogfile, 'a')
         else:
            self.logger.info("Ticket srn logging enabled")
            ticketlog = open(ticketlogfile, 'w')
      
      



      for item in SwimlaneTickets["data"]["Tickets"]["items"]:

         if item["resource"] == None:
            self.logger.debug("ticket with null resource detected -  assuming deleted resource, closing - " + item["TicketSRN"])
            ticketCount += 1
            closeTicketsList.append(item["TicketSRN"])
            if logClosedTicketIDs is True:
               ticketlog.write(item["TicketSRN"] + "\n")

         elif closeActiveTickets and closeInactiveTickets:
             # closing tickets on active AND inactive resources, no need to check active flag
             self.logger.debug("closing tickets on ACTIVE and INACTIVE resources.  ticketSRN: " + item["TicketSRN"] )
             ticketCount += 1
             closeTicketsList.append(item["TicketSRN"])
             if logClosedTicketIDs is True:
                ticketlog.write(item["TicketSRN"] + "\n")

         elif closeInactiveTickets and item["resource"]["active"] == False:
            self.logger.debug("Closing tickets on INACTIVE resources. ticketSRN: " + item["TicketSRN"] )
            ticketCount += 1
            closeTicketsList.append(item["TicketSRN"])
            if logClosedTicketIDs is True:
               ticketlog.write(item["TicketSRN"] + "\n")

         elif closeActiveTickets and item["resource"]["active"] == True:
            self.logger.debug("Closing tickets on ACTIVE resources. ticketSRN:  " + item["TicketSRN"] )
            ticketCount += 1
            closeTicketsList.append(item["TicketSRN"])
            if logClosedTicketIDs is True:
               ticketlog.write(item["TicketSRN"] + "\n")

         if len(closeTicketsList) == int(maxClosePerRequest):
            self.logger.info("closing " + str(len(closeTicketsList)) + " tickets. " )
            self.logger.debug("tickets: " + str(closeTicketsList))
            if ticketComment is not None:
               ticketAddCommentResponse = self.addCommentToTickets( closeTicketsList, ticketComment, userSrn, testonly)
               self.logger.debug("AddCommentResponse: " + str(ticketAddCommentResponse))
            ticketcloseresponse = self.closeTickets(closeTicketsList, testonly)
            self.logger.info("CloseTicketResponse: " + str(ticketcloseresponse))
            ticketcloseresponse=""
            closeTicketsList = []
            time.sleep(1)

      if len(closeTicketsList) > 0:
         self.logger.info("closing " + str(len(closeTicketsList)) )
         self.logger.debug("tickets: " + str(closeTicketsList))
         if ticketComment is not None:
            ticketAddCommentResponse = self.addCommentToTickets(closeTicketsList, ticketComment, userSrn, testonly)
            self.logger.debug("AddCommentResponse: " + str(ticketAddCommentResponse) )
         ticketcloseresponse = self.closeTickets(closeTicketsList, testonly)
         self.logger.info("CloseTicketResponse: " + str(ticketcloseresponse) )

      if logClosedTicketIDs is True:
         ticketlog.close()

      self.logger.info("Complete. closed " + str(ticketCount) + " tickets ")



HANDLER=None

# def handle(event, context):
def handle(myargv):
   global HANDLER
   if not HANDLER:
      HANDLER = TicketHandler()
   HANDLER.main(myargv)

if __name__ == "__main__":
   handle(sys.argv[1:])



