# utilities/sonrai.py
#
# This python library file provides basic classes for use with other
# pythons scripts to query the Sonrai GraphQL API.  For examples
# check the Sonrai knowledge base for Sonrai API

# For more information on the GraphQL query format, open the
# search UI at https://app.sonraisecurity.com/, select "Search" then click "Advanced Search".
# In the Advanced Search area, the "Docs" section on the right can provide additional
# query documentation

# In addition, you can also choose to create a saved search with all the filters you wish,
# and then query that search from the script using the "ExecuteSavedQuery" function.

# Dependencies:
# This script requires Python 3, as well as the requests and pyjwt libraries.
# The libraries can be installed by running:
#   pip3 install requests pyjwt
#   (OR)
#   pip3 install -r requirements.txt

# Environment Variables:
# TOKEN:   Authentication token for the GraphQL server
# TOKENSTORE: Directory in which to store the refreshed auth token
# TOKENFILE:  Filename to use to store the refreshed auth token
# LOGLEVEL:       Set to True if you would like debugging messages

import sys
import logging
import os
import time
import json
import requests
import jwt
from os import path

class SonraiApi:

    def __init__(self, queryName = "SonraiAPILibrary", savedQueryName = None, queryFileName = None, queryVariables = "{}", outputMode = "blob"):
        global TOKENSTORE, TOKENFILE, TOKEN_DEFAULT_LENGTH, ENV_TOKEN, APISERVER, URL

        self.api_raw_response = None
        self.api_parsed_response = None
        self.outputMode = outputMode

        APISERVER = os.environ.get("APISERVER",None)
        ENV_TOKEN = os.environ.get("TOKEN",None)
        TOKENSTORE = os.environ.get("SONRAI_API_TOKENSTORE","/tmp/sonrai")
        TOKENFILE = os.environ.get("SONRAI_API_TOKENFILE","token")
        TOKEN_DEFAULT_LENGTH_SEC = os.environ.get("TOKEN_DEFAULT_LENGTH_SEC",7200)
        self.token_default_length_sec = TOKEN_DEFAULT_LENGTH_SEC
        self.loglevel=os.environ.get("LOGLEVEL", "ERROR")
        self.logger=logging.getLogger("sonrai.py")
        self.logger.setLevel(self.loglevel)
        self.logger.info("logging level: " + self.loglevel)
        self.proxyserver = os.environ.get('PROXYSERVER', None)
        self.checkcertificate = True
        self.audience="crc-graphql-server.sonraisecurity.com"
        self.jwtoptions = {"verify_iat":True, "verify_nbf":True, "verify_exp":True, "verify_iss":True, "verify_aud":True, "verify_signature":False}


        # minimum refresh window is 1800 seconds (30m)
        token_refresh_threshold = int(os.environ.get("TOKENREFRESHTHRESHOLDSEC", 1800))
        if token_refresh_threshold < 1800:
            token_refresh_threshold = 1800
        elif token_refresh_threshold > 2592000:
            token_refresh_threshold = 2592000

        self.TOKEN_REFRESH_THRESHOLD_SEC = token_refresh_threshold

        # minimum required length is 7200 for api tokens
        tokenrenewlength = int(os.environ.get("TOKENRENEWLENGTH",86400))
        if tokenrenewlength < 7200:
            tokenrenewlength = 7200
        if tokenrenewlength > 2592000:
            tokenrenewlength = 2592000

        self.TOKENRENEWLENGTH = tokenrenewlength

        # Query - get 200 highest severity tickets (default sort is by severity)
        self.CRC_COMMAND = "query SonraiAPITicketsDefaultQuery { Tickets { items (limit: 200) { srn, createdDate, resourceName, policy { title }, severityNumeric, severityCategory}}}"

        if savedQueryName is not None:
            self.CRC_COMMAND = 'query RunQuery { ExecuteSavedQuery { Query (name: "' + savedQueryName + '" overrideVariables: true) }}'

        if queryFileName is not None:
            queryToRun = self.parseQueryFile(queryFileName)
            self.CRC_COMMAND = queryToRun

        if queryName is not None:
            self.QUERY_NAME = queryName

        if queryVariables is not None:
            self.queryVariables = queryVariables

        #  Check to see if the arg passed to -v/--vars is valid JSON
        if self.queryVariables != "{}":
            try:
                json.loads(self.queryVariables)
            except Exception as e:
                self.logger.error("Argument passed to as variable is not valid JSON.")
                self.logger.error("Example of valid JSON on the command line would be: '{\"key\": \"value\"}'")
                exit()

    def verify(self, verify=True):
            self.checkcertificate = verify

    #################### def ####################
    # SonraiGraphQLQuery - Call the GraphQL API and return the response.

    def SonraiGraphQLQuery(self,varServer,varQuery,varQueryName,token):
        varHeaders = self.buildAuthHeader(token, varQueryName)
        # varHeaders['Cache=Control'] = 'no-cache'
        self.sonraiquery = requests.session()

        if self.checkcertificate is False:
            self.sonraiquery.verify = False
            self.logger.debug("ssl verification disabled")

        if self.proxyserver:
            self.proxy = {
                "http": self.proxyserver,
                "https": self.proxyserver
            }
            self.logger.debug("using proxy server: " + self.proxyserver)
        else:
            self.proxy = None


        # adding up to 10 retries
        retries=0
        complete=False

        while retries < 10 and complete is False:
            try:
                myResponse=self.sonraiquery.post(varServer, data=varQuery, headers=varHeaders, proxies=self.proxy, timeout=120)

            except requests.exceptions.ConnectionError:
                self.logger.error("*** CONNECTION ERROR to: " + varServer + " - retrying? ")
                if self.loglevel == "DEBUG":
                    print("r")
                retries += 1
                time.sleep(5)

            except requests.exceptions.SSLError:
                self.logger.error("*** SSL Certificate verification failed for: " + varServer + " - self signed detected? ")
                if self.loglevel == "DEBUG":
                    print("r")
                retries += 1
                time.sleep(5)

            except requests.exceptions.ProxyError:
                self.logger.error("*** Proxy Unreachable: " + str(self.proxyserver) )
                if self.loglevel == "DEBUG":
                    print("r")
                retries += 1
                time.sleep(5)

            except requests.exceptions.Timeout:
                self.logger.error("*** Request timeout. Wait a few minutes & try your query again. If the error continues, contact sonrai support")
                if self.loglevel == "DEBUG":
                    print("r")
                retries += 1
                time.sleep(5)

            except requests.exceptions.RequestException:
                self.logger.error("*** Request error. Wait a few minutes & try your query again. If the error continues, contact sonrai support")
                self.logger.error("*** Message: " + json.dumps(myResponse))
                if self.loglevel == "DEBUG":
                    print("r")
                retries += 1
                time.sleep(5)

            else:
                complete=True

            if retries == 10 and complete is False:
                print("failed after {} retries, aborting".format(retries))
                sys.exit(255)



        self.logger.debug("status code: " +  str(myResponse.status_code) + " / server: " + varServer )

        if myResponse.status_code in (404,403,402):
            self.logger.error("*** AUTHENTICATION FAILED ***")
            self.logger.error("" + str(myResponse.status_code) + " error - please check your server setting: " + varServer )
            sys.exit(10)
        if myResponse.status_code == 401:
            self.logger.error("*** API AUTHENTICATION FAILED ***")
            self.logger.debug("Token used: "+token)
            self.logger.error("API token expired, please get a new one from the Advanced Search UI.")
            sys.exit(9)
        elif myResponse.status_code == 500:
            self.logger.error("Error returned " )
            self.logger.error(str(myResponse.json()))
            # adding sleep, to see if the graphql server can recover
            time.sleep(9)
            # removing exit - should only abort on a non-recoverable error, like failed auth
            # sys.exit(8)
        elif "Unexpected exception while fetching Grpc data" in str(myResponse.json()):
            self.logger.error("GPRC error message received:")
            self.logger.error("This occurs if the query size limit is reached.")
            self.logger.error("Try limiting your query with additional filters & try again.")
            self.logger.error(json.dumps(myResponse.json()))
            # removing exit - should only abort on a non-recoverable error, like failed auth
            # sys.exit(7)


        myResponse=myResponse.json()
        return myResponse
    ##  end SonraiGraphQLQuery

    # buildAuthHeader - Return the API authorization header.

    def buildAuthHeader(self, token, varQueryName):
        return {"authorization": "Bearer " + token, "Content-type": "application/json", "query-name": varQueryName, "Cache-Control": "no-cache"}

    ## end buildAuthHeader

    #################### def ####################
    def storeToken(self, token):

        self.logger.debug("storing token at " + os.path.join(TOKENSTORE,TOKENFILE))
        if not (os.path.exists(TOKENSTORE)):
            os.mkdir(TOKENSTORE)
        with open(os.path.join(TOKENSTORE,TOKENFILE),"w") as tokendest:
            tokendest.write(token)
            tokendest.close()
    ## end storeToken

    # tokenExpiring - Check if token is near expiration and return true/false.
    def tokenExpiring(self, token):

        self.logger.debug("checking token expiration")

        # Decode token, parse expiration date, and calculate time remaining
        token_expiry = jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience ).get('exp',0)
        current_time = time.time()
        remaining = token_expiry - current_time
        self.logger.debug("expiry:"+str(token_expiry) + " || current: "+str(int(current_time)) + " || remaining: "+str(int(remaining))+"s")

        # If token is near expiration, return true.  Otherwise false.
        if remaining < 0:
            self.logger.debug("token has expired, cannot be renewed - ("+str(int(remaining))+"s ago)")
            return True
        elif remaining < 21600:
            # if less than 6 hours remaining, attempt to renew
            self.logger.debug("token near expiration ("+str(int(remaining))+"s)... needs updating")
            return True
        else:
            self.logger.debug("token not near expiration")
            return False

    ## end tokenExpiring


    def tokenExpired(self, token):

        self.logger.debug("checking if token expired")

        # Decode token, parse expiration date, and calculate time remaining
        token_expiry = jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience ).get('exp',0)
        current_time = time.time()
        remaining = token_expiry - current_time
        # self.logger.debug("expiry:"+str(token_expiry) + " || current: "+str(int(current_time)) + " || remaining: "+str(int(remaining))+"s")

        # If token is near expiration, return true.  Otherwise false.
        if remaining < 0:
            self.logger.debug("token has expired, cannot be renewed - ("+str(int(remaining))+"s ago)")
            return True


    # renewToken - Call the renew token API and store it for future use.
    def renewLegacyToken(self, token):
        # Call the renew token API
        self.logger.debug("calling renew token api")

        createapitokenquery = '''
                mutation sonrai_lambda_integration_createtoken_v2 { 
                    GenerateSonraiUserToken (input: {
                        expiresIn: ''' + str(self.TOKENRENEWLENGTH) + '''
                        name: "sonrai_api_client_tokenrenewal"
                    }) 
                    { token }
                }
            '''



        QUERY_NAME = "SonraiAPIClient_TokenRenew"
        POST_FIELDS = {"query": createapitokenquery, "variables": "{}"}
        POST_FIELDS = json.dumps(POST_FIELDS)

        NewTokenJson=self.SonraiGraphQLQuery(URL,POST_FIELDS,QUERY_NAME,token)

        newToken=NewTokenJson['data']['GenerateSonraiUserToken']['token']
        self.logger.info("retreived updated token")
        self.logger.debug("new token: " + newToken)
        self.logger.info("storing updated token.")
        self.storeToken(newToken)

        # Return the new token
        return newToken

    ## end renewToken

    # renewToken - Call the renew token API and store it for future use.
    def renewToken(self, token):
        # Call the renew token API
        self.logger.debug("calling renew token api")

        CRC_COMMAND = '''mutation createToken {
                        GenerateSonraiUserToken (input:{ expiresIn: ''' + str(self.token_default_length_sec) + ''' name: "pythonAPIToken" }) {
                         expireAt token } } '''
        QUERY_NAME = "SonraiAPIClient_TokenRenew"
        POST_FIELDS = {"query": CRC_COMMAND, "variables": "{}"}
        POST_FIELDS = json.dumps(POST_FIELDS)

        NewTokenJson = self.SonraiGraphQLQuery(URL, POST_FIELDS, QUERY_NAME,
                                               token)

        #newToken = NewTokenJson['data']['renewApiToken']['token']
        newToken = NewTokenJson['data']['GenerateSonraiUserToken']['token']
        self.logger.info("retreived updated token")
        self.logger.debug("new token: " + newToken)
        self.logger.info("storing updated token.")
        self.storeToken(newToken)

        # Return the new token
        return newToken

    ## end renewToken



    # validToken - Check if token is a valid JWT token by trying to decode it.
    def validToken(self, token):
        if token == None or token == "":
            return False
        else:
            # token_expiry = jwt.decode(token,verify=False).get('exp',0)
            self.getAudience(token)
            token_expiry = jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience ).get('exp',0)
            self.setGraphQLUrl(token)
            self.logger.debug("expires: " + str(token_expiry))
            # try:
            jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience ).get('exp',0)
            if self.tokenExpiring(token) is False:
                return True
            else:
                if self.tokenExpired(token):
                    self.logger.debug("token already expired")
                    return False
                else:
                    self.logger.debug("renewing existing token ")
                    self.renewToken(token)
                    return True

        # except Exception as e:
            # self.logger.debug("try jwt.decode failed")
            # self.logger.debug(token)
            # self.logger.debug("cannot decode token, invalid token")
            # return False


    def getGraphQLUrl(self, token):

        if APISERVER is None:
            self.logger.debug("Pulling API server from token")
            decoded_token = jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience )
            org = decoded_token['https://sonraisecurity.com/org']
            env = decoded_token['https://sonraisecurity.com/env']
            domain = ".sonraisecurity.com"
            if env == 'stage':
                domain = '.s.sonraisecurity.com'
            elif env == 'dev':
                domain = '.de.sonraisecurity.com'

            s = org + domain
        else:
            self.logger.debug("Pulling API server from env:APISERVER")
            s = APISERVER

        URL = "https://"+s+"/graphql"
        self.logger.debug("API server: " + URL)
        return URL

    def tokenOrg(self,token):
        decoded_token = jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience)
        org = decoded_token['https://sonraisecurity.com/org']
        return org

    def getAudience(self, token):
        jwtoptions = {"verify_iat":True, "verify_nbf":True, "verify_exp":True, "verify_iss":True, "verify_aud":False, "verify_signature":False}
        decoded_token = jwt.decode(token, options=jwtoptions, algorithms=["RS256"] )
        self.audience = decoded_token['aud']

    # setGraphQLUrl - Sets the GraphQL API URL to use, based on API token or APISERVER env var.
    def setGraphQLUrl(self, token):
        global URL

        if APISERVER is None:
            self.logger.debug("Pulling API server from token")
            decoded_token = jwt.decode(token, options=self.jwtoptions, algorithms=["RS256"], audience=self.audience )
            org = decoded_token['https://sonraisecurity.com/org']
            env = decoded_token['https://sonraisecurity.com/env']
            domain = ".sonraisecurity.com"
            if env == 'stage':
                domain = '.s.sonraisecurity.com'
            elif env == 'dev':
                domain = '.de.sonraisecurity.com'

            s = org + domain
        else:
            self.logger.debug("Pulling API server from env:APISERVER")
            s = APISERVER

        URL = "https://"+s+"/graphql"
        self.logger.debug("API server: " + URL)

    ## end getGraphQLUrl

    # getToken - Check for env and file system tokens, renewing if necessary.  Returns token to use.
    def getToken(self):

        # Check for token in token store file.
        self.logger.debug("checking for filesystem token")
        tokenCheck=path.exists(os.path.join(TOKENSTORE,TOKENFILE))

        # check local token
        if tokenCheck is True:
            self.logger.debug("filesystem token found: " + TOKENSTORE + "/" + TOKENFILE)
            with open(os.path.join(TOKENSTORE,TOKENFILE),"r") as tokensource:
                token_fromfile = tokensource.read().strip()
                tokensource.close()

            # check valid local token
            if self.validToken(token_fromfile):
                self.logger.debug("using valid filesystem token")
                self.setGraphQLUrl(token_fromfile)
                return token_fromfile
            else:
                self.logger.debug("filesystem token invalid")

        token_fromenv = ENV_TOKEN
        self.logger.debug("checking env token")

        if self.validToken(token_fromenv):
            self.logger.debug("using valid env token")
            self.logger.debug("storing environment token to disk")
            # Store the new token
            self.storeToken(token_fromenv)
            self.setGraphQLUrl(token_fromenv)
            return token_fromenv

        else:
            self.logger.error("no valid tokens found in ENV or on disk.")
            self.logger.error("retrieve token from sonrai advanced search at: https://app.sonraisecurity.com/App/GraphExplorer")
            sys.exit(253)



    ## end getToken

    # parseQueryFile - Read GraphQL query from file and return it.
    def parseQueryFile(self, filename):
        self.logger.debug("PARSING QUERY FILE " + filename)
        with open(filename,"r") as querysource:
            query_fromfile = querysource.read().strip()
            querysource.close()
        return query_fromfile


    def linebylineCSV (self, outputBlob):
        for key in outputBlob:
            if key == "count":
                continue
            elif key != "items":
                results = self.linebylineCSV(outputBlob[key])
            else:
                csvRecords = ""
                csvHeader = ""
                count = 0
                for item in outputBlob[key]:
                    recordString = ""
                    for recordKey in item:
                        if count == 0:
                            csvHeader += str(recordKey) + ", "
                        recordString += str(item[recordKey]) + ", "
                    csvRecords += recordString + "\n"
                    count += 1

                csv = csvHeader + "\n" + csvRecords
                results = csv

        return results

    def linebylineJSON (self, outputBlob):
        for key in outputBlob:
            if key == "count":
                continue
            elif key != "items":
                results = self.linebylineJSON(outputBlob[key])
            else:
                results = (json.dumps(outputBlob, indent=4, sort_keys=True) + "\n")
        return results

    def executeQuery(self, query=None, variables=None):
        if query is None:
            query = self.CRC_COMMAND

        if variables is None:
            variables = self.queryVariables

        POST_FIELDS = {"query": query, "variables": variables}
        POST_FIELDS = json.dumps(POST_FIELDS)
        CurrentToken = self.getToken()
        self.logger.debug("USING TOKEN: " + str(CurrentToken))
        queryName = self.QUERY_NAME
        self.logger.info("Using queryName of " + str(queryName))
        cdc_response = self.SonraiGraphQLQuery(URL,POST_FIELDS,queryName,CurrentToken)

        #self.api_raw_response = cdc_response
        if self.outputMode == "blob":
            #self.api_parsed_response = json.dumps(cdc_response['data'], indent=4, sort_keys=True)
            self.api_parsed_response = cdc_response
        elif self.outputMode == "lbl":
            # return just the first 'items' in the JSON
            self.api_parsed_response = self.linebylineJSON(cdc_response['data'])
        # elif self.outputMode == "csv":
        # This second needs work
        #     self.api_parsed_response = self.linebylineCSV(cdc_response['data'])
        return self.api_parsed_response

    ################### end def ####################
