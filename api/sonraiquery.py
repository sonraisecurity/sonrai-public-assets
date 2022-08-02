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
from sonrai import SonraiApi

class SonraiQuery:

    def __init__(self):
        self.savedQueryName = None
        self.queryFileName = None
        self.queryName = "DefaultAPIQuery"
        self.queryVariables = "{}"
        self.outputMode="blob"

        try:
            opts, args = getopt.getopt(sys.argv[1:],'blhdq:f:n:v:', ["blob","linebyline", "help", "debug", "query=", "file=", "name=", "vars="])
        except getopt.GetoptError as err:
            print(err)
            self.print_usage()
            sys.exit()

        # get the command line options mapped
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                self.print_usage()
                sys.exit()
            elif opt in ("-b", "--blob"):
                self.outputMode = "blob"
            # elif opt in ("-c", "--csv"):
            #     self.outputMode = "csv"
            if opt in ("-l", "--linebyline"):
                self.outputMode = "lbl"
            elif opt in ("-d", "--debug"):
                self.logger.basicConfig(stream=sys.stderr, level=logging.DEBUG)
            elif opt in ("-q", "--query"):
                self.savedQueryName = arg
            elif opt in ("-f", "--file"):
                self.queryFileName = arg
            elif opt in ("-n", "--name"):
                self.queryName = arg
            elif opt in ("-v", "--vars"):
                self.queryVariables = arg
            # else:
                # assert False, "unhandled error"

        self.loglevel=os.environ.get("LOGLEVEL", "INFO")
        self.logger=logging.getLogger("sonraiquery.py")
        self.logger.setLevel(self.loglevel)
        self.logger.info("logging level: " + self.loglevel)

        logging.basicConfig(level=self.loglevel,
                            format="%(asctime)s:%(name)s:%(funcName)s:%(levelname)s: %(message)s"
                            )

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
        print("   ./sonraiquery.py [--debug] [--query NAME] [--file FILENAME] [--vars {VARS}]")
        print("   ./sonraiquery.py --help")
        print("")
        print(" Options:")
        print("   -h, --help                  Show this message.")
        print("   -d, --debug                 Enable debugging.")
        print("   -b, --blob                  Print the output in raw format (DEFAULT)")
        print("   -l, --linebyline            Print each json data.items entry on it's own line.")
        print("   -q <name>, --query <name>   Execute the saved query named <name>.")
        print("   -f <file>, --file <file>    Execute the query contained in <file>.")
        print("   -n <queryName>, --name <queryName>    Provide a query name of <queryName>.")
        print("   -v <vars>, --vars <vars>    Use the JSON string passed as <vars> as the GraphQL query variables.")
        print("                               Typically used with -f/--file when that GraphQL query requires variables.")
        print("")
        print(" Environment variables:")
        print("   TOKEN                   Sonrai API auth token")
        print("   LOGLEVEL                ERROR, INFO, DEBUG - INFO is enabled by default")
        print("")


    def main (self):
        # setup an API client
        self.client = SonraiApi(self.queryName, self.savedQueryName, self.queryFileName, self.queryVariables, self.outputMode)
        # execute the query passed in either the savedQueryNAme or the queryFileName
        results = self.client.executeQuery()
        # display results
        print (results)


HANDLER=None

# def handle(event, context):
def handle(myargv):
    global HANDLER
    if not HANDLER:
        HANDLER = SonraiQuery()
    HANDLER.main()

if __name__ == "__main__":
    handle(sys.argv[1:])