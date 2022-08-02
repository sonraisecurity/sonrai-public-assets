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
import re
import getopt
from sonrai import SonraiApi

class TicketQuery:

    def __init__(self):
        self.savedQueryName = None
        self.queryFileName = None # not required, just a placeholder
        self.framework = None
        self.swimlane = None
        self.environment = None
        self.sevCat = None
        self.dateRange = None
        self.maxTickets = 10000
        self.statuses = ['NEW','CLOSED','RISK_ACCEPTED','SNOOZED']
        self.severityList = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL']
        self.environmentList = ['Sensitive Data','Production','Staging','Development','Sandbox']
        self.queryName = "DefaultAPIQuery"
        self.queryVariables = "{}"
        self.outputMode="blob"

        self.loglevel = os.environ.get("LOGLEVEL", "INFO")
        self.logger = logging.getLogger("sonraiquery.py")
        self.logger.setLevel(self.loglevel)
        self.logger.info("logging level: " + self.loglevel)

        try:
            opts, args = getopt.getopt(sys.argv[1:],'hf:s:c:e:r:m:', ["help", "framework=", "swimlane=", "sevcategory=", "environment=", "daterange=", "maxresults="])
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
                self.framework = arg
            elif opt in ("-s", "--swimlane"):
                self.swimlane = arg
            elif opt in ("-c", "--sevcategory"):
                self.sevCat = arg.upper()
                if self.sevCat not in self.severityList:
                    print('Invalid environment: "{}", must be one of the following values: {} '.format(self.sevCat,self.severityList))
                    exit(0)
            elif opt in ("-e", "--environment"):
                self.environment = arg
                if self.environment not in self.environmentList:
                    print ('Invalid environment: "{}", must be one of the following values: {} '.format(self.environment, self.environmentList))
                    exit (0)
            elif opt in ("-r", "--daterange"):
                self.dateRange = arg
                if not re.match("\d{4}\-\d{2}\-\d{2}:\d{4}\-\d{2}\-\d{2}", self.dateRange):
                    print ("Date range format wrong")
                    self.print_usage()
                    sys.exit(1)
                (self.startDate, self.endDate) = self.dateRange.split(":")
            elif opt in ("-m", "--maxresults"):
                self.maxTickets = arg
            # else:
                # assert False, "unhandled error"

            if self.dateRange is None:
                print ("Must include a date range")
                self.print_usage()
                sys.exit (1)




    def print_usage(self):
        print("")
        print(" Usage:  ")
        print("   ./sonrai-ticket-report.py --daterange <daterange> [--framework <framework>] [--swimlane <swimlane>] [--sevcategory <severity>] [--environment <environment>]")
        print("   ./sonrai-ticket-report.py --help")
        print("")
        print(" Options:")
        print("   -h, --help                  Show this message.")
        print("   -r <startDate:endDate>, --daterange <startDate:endDate>    REQUIRED Provide the <startDate:endDate> to report. Format is yyyy-mm-dd:yyyy-mm-dd")
        print("                              eg: 2021-08-01:2021-08-31")
        print("   -m <integer>, --maxTickets <integer>    Report on the maximum number of tickets.")
        print("   -f <framework name>, --framework <framework name>    Execute the script against <framework name>.")
        print("   -s <swimlane name>, --swimlane <swimlane name>    Execute the script against <swimlane name>.")
        print("   -c <severity>, --sevcategory <severity>    Provide the severity Type to filter on.")
        print("                              <severity> = [critical|high|medium|low|informational]")
        print("   -e <environment>, --environment <environment>    Provide the <environment> to report.")
        print("                              <environment> = [Sensitive Data|Production|Staging|Development|Sandbox]")
        print("")
        print(" Environment variables:")
        print("   TOKEN                   Sonrai API auth token")
        #print("   LOGLEVEL                ERROR, INFO, DEBUG - INFO is enabled by default")
        print("")

    def querySwimlaneBuilder (self, swName):
        query  = 'query swimlaneSRN {Swimlanes (where: {'
        query += '    title: {op: EQ value:"' + swName + '"}'
        query += '})'
        query += ' {count items { srn }}}'
        return query

    def queryFrameworkBuilder (self, fwName):
        query  = 'query frameworkSRN {ControlFrameworks (where: {'
        query += '    title: {op: EQ value:"' + fwName + '"}'
        query += '})'
        query += ' {count items { srn }}}'
        return query

    def queryBuilder (self, status, slSRN, fwSRN):
        #build the query based on the filters passed in
        query  = 'query getTickets{Tickets '
        query += '(where: {' #open the where brackets
        query += ' status: {op:EQ value:"' + status + '"}'

        if status == "NEW":
            query += 'createdDate: {op:BETWEEN values:["' + self.startDate + '", "' + self.endDate + '"] } '
            orderby = 'orderBy: {createdDate: {order: ASC } }'
        elif status == "RISK_ACCEPTED" or status == "SNOOZED":
            query += 'transitionDate: {op:BETWEEN values:["' + self.startDate + '", "' + self.endDate + '"] } '
            orderby = 'orderBy: {transitionDate: {order: ASC } }'
        else:
            # OLD tickets (aka closed)
            query += 'lastModified: {op:BETWEEN values:["' + self.startDate + '", "' + self.endDate + '"] } '
            orderby = 'orderBy: {lastModified: {order: ASC } }'

        if slSRN is not None:
            query += 'swimlaneSrns: {op:EQ value:"' + slSRN +'"} '

        if fwSRN is not None:
            query += 'controlFrameworkSrn: {op:EQ value:"' + fwSRN +'"} '

        if self.environment is not None:
            query += 'environment: {op:EQ value:"' + self.environment + '" } '

        if self.sevCat is not None:
            query += 'severityCategory: {op:EQ value:"' + self.sevCat + '" } '

        query += ' }) ' # close the where brackets
        query += ' {count, items(limit: ' + str(self.maxTickets) + ', ' + orderby + ') {'
        query += 'createdDate, lastModified, transitionDate'
        query += '}}}'

        return query

    def processTickets (self, status, tickets):
        if tickets['data']['Tickets']['count'] == 0:
            return 0

        if status == "NEW":
            filter = 'createdDate'
        elif status == "RISK_ACCEPTED" or status == "SNOOZED":
            filter = 'transitionDate'
        else:
            filter = 'lastModified'

        ticketCounter= {}
        self.ticketCounter[status] = {}
        items = tickets['data']['Tickets']['items']
        for ticket in items:
            #print (ticket)
            date = ticket[filter]
            datePattern = re.compile('^\d{4}\-\d{2}\-\d{2}')
            formattedDate = datePattern.findall(date)[0]
            if formattedDate in ticketCounter:
                ticketCounter[formattedDate] += 1
                self.ticketCounter[status][formattedDate] += 1
            else:
                ticketCounter[formattedDate] = 1
                self.ticketCounter[status][formattedDate] = 1

        return tickets

    def printSummary(self):
        (sYear, sMonth, sDay) = self.startDate.split("-")
        (eYear, eMonth, eDay) = self.endDate.split("-")
        startDate = datetime.date(int(sYear) , int(sMonth) , int(sDay) )
        endDate = datetime.date(int(eYear) , int(eMonth) , int(eDay) )
        delta = datetime.timedelta(days=1)

        print ("Date, ", end="")
        for status in self.statuses:
            print (status + ", ", end="")
        print ()
        while startDate <= endDate:
            print ('"'+str(startDate) + '",', end='')
            for status in self.statuses:
                if status in self.ticketCounter:
                    if str(startDate) in self.ticketCounter[status]:
                        print (str(self.ticketCounter[status][str(startDate)]) + ', ', end='')
                    else:
                        print ('0, ', end='')
                else:
                    print('0, ', end='')
            startDate += delta
            print ()


    def main (self):
        # setup an API client
        self.client = SonraiApi(self.queryName, self.savedQueryName, self.queryFileName, self.queryVariables, self.outputMode)
        # execute the query passed in either the savedQueryNAme or the queryFileName

        swimlaneSRN = None
        if self.swimlane is not None:
            self.swimlaneQuery = self.querySwimlaneBuilder(self.swimlane)
            rSwimlaneSRN = self.client.executeQuery(self.swimlaneQuery)
            if rSwimlaneSRN['data']['Swimlanes']['count'] != 0:
                swimlaneSRN = rSwimlaneSRN['data']['Swimlanes']['items'][0]['srn']
            else:
                print ('ERROR: invalid Swimlane Name: "{}"'.format(self.swimlane))
                exit (0)


        frameworkSRN = None
        if self.framework is not None:
            self.frameworkQuery = self.queryFrameworkBuilder(self.framework)
            rFrameworkSRN = self.client.executeQuery(self.frameworkQuery)
            if rFrameworkSRN['data']['ControlFrameworks']['count'] != 0:
                frameworkSRN = rFrameworkSRN['data']['ControlFrameworks']['items'][0]['srn']
            else:
                print ('ERROR: invalid Framework Name: "{}"'.format(self.framework))
                exit (0)

        self.ticketCounter = {}

        # perform searches for each status type and build the formatted output
        for status in self.statuses:
            self.ticketQuery = self.queryBuilder(status, swimlaneSRN, frameworkSRN)
            results = self.client.executeQuery(self.ticketQuery)
            if int(results['data']['Tickets']['count']) >= int(self.maxTickets):
                sys.stderr.write('Maximum number({}) of {} tickets reached\n'.format( self.maxTickets, status))
            summary = self.processTickets(status, results)

        # print out filters:
        print ("Searches used the following filters:")
        if swimlaneSRN is not None:
            print ('swimlaneName: "{}" swimlaneSRN: "{}" '.format(self.swimlane, swimlaneSRN))

        if frameworkSRN is not None:
            print ('frameworkName: "{}" framworkSRN: "{}" '.format(self.framework, frameworkSRN))

        if self.environment is not None:
            print ('environment: "{}"'.format(self.environment))

        if self.sevCat is not None:
            print ('severity: "{}"'.format(self.sevCat))

        # print out the summary of the data
        print () # add blank line between preamble and CSV data
        self.printSummary()

HANDLER=None

# def handle(event, context):
def handle(myargv):
    global HANDLER
    if not HANDLER:
        HANDLER = TicketQuery()
    HANDLER.main()

if __name__ == "__main__":
    handle(sys.argv[1:])