## closetickets.py 


#### command line parameters:

    Usage: closetickets.py [options]
     example:
       closetickets.py -g -i
        closes tickets from global swimlane, where the resource is currently inactive,
        starting with the 50 most recent tickets

    -h                   - help
    -f <ticketkeySRN>    - close tickets where ticketKey ControlPolicySRN or ControlFrameworkSRN
    -m <number>          - retrieve <number> maximum tickets from sonrai api
    -a                   - close tickets where resourcs are active
    -i                   - close tickets where resoures are inactive (deleted from cloud)
                         one or both of -a or -i are required
    -all-swimlanes       - close tickets on any swimlane - overrides -g and -s                    
    -g                   - close tickets in Global swimlane.  overrides -s [swimlane] option
    -r <resourceSRN>     - close tickets for resource <resourceSRN>
    -s <swimlaneSRN>     - close tickets in swimlane <swimlaneSRN>
                         one of -g or -s <swimlane> is required
    -l </path/filename>  - log closed ticket SRNs to file </path/filename>
    -n <hours>           - close tickets with lastModified time NEWER than <hours> hours ago.
    -o <hours>           - close tickets with lastModified time OLDER than <hours> hours ago.
                         only ONE of -n or -o is permitted
    -c "<comment>"       - add momment to ticket before closing. Comment must be in quotation marks
    -u <userSRN>         - SRN of user adding comment. Used in conjunction with the -c option.
                           Must be same user as the user that created the token

    --no-check-certificate  - disable ssl verification to sonrai api (ie, ssl interception proxy) 
    --testonly           - do not close tickets, test only
    --maxclose-per-request
                         - maximum number of tickets to close per request. default:50
    --printquery         - print out graphql query
    --severityUpper      - close tickets BELOW severity of N.  Default: 100
    --severityLower      - close tickets ABOVE severity of N.  Default: 0 


     view closetickets_README.md for additional information  
  
#### environment variables
##### required:
    TOKEN = token
    token use to connect to Sonrai.  Ticket is stored in /tmp/sonrai/token 
    by default and used for subsequent queries until it expires.
  
    Note: If a token exists in /tmp/sonrai/token, that token is 
    used instead. Delete this cached token to use the environment variable 
    instead.

 ##### optional
    
    LOGLEVEL = [INFO,WARN,ERROR(default),DEBUG]  
    changes log level output

    APISERVER = [sonraiserveraddress]  
    graphql server name, ie "integra.sonraisecurity.com", defaults
    to the server name included in your token. 

    PROXYSERVER=[http://proxyserver:port]
    python.requests connection to Sonrai API server uses the specified
    proxy

    TOKENSTORE = [path]
    override default location of "/tmp/sonrai" for storing api token.  
    May be required when using python in windows

    TOKENFILE = [filename]
    override default filename of "token" for storing API token
    
    TOKENREFRESHTHRESHOLDSEC=n
    remaining time left in existing token before requesting a new one. 
    default 1800seconds (30 minutes)
    
    TOKENRENEWLENGTH=n
    default time period to request new token for.  
    default 86400 seconds (1 day)


#### Troubleshooting & Tips

* GRPC errors 

>INFO:api:{"errors": [{"message": "Exception while fetching data (/Tickets) : 
> Unexpected exception while fetching Grpc data.", "locations": [{"line": 4, 
> "column": 18}], "path": ["Tickets"], "extensions": {"classification": 
> "DataFetchingException"}}], "data": {"Tickets": null}}

If you receive this error, the query size results are too large, usually
caused by a -m NNNN value that's requesting too many results for the
backend platform to return.  Try a smaller result set, such as 3000-4000.


* number of results is smaller than your request  
> ip-192-168-10-29:api dwight$ ./closetickets_inactiveresources.py -s "srn:integra::Swimlane/45647dq4-af73-tyui-957c-4576456ghjlh" -m 3000
> INFO:api:[init] logging level: INFO
> INFO:api:[main] finding up to 3000 tickets for swimlane srn:integra::Swimlane/45647dq4-af73-tyui-957c-4576456ghjlh
> INFO:api:[queryTickets] calling api for tickets in srn:integra::Swimlane/45647dq4-af73-tyui-957c-4576456ghjlh
> INFO:api:[main] tickets found: 172

If the number of results found is smaller than the max you requested,
then no newer results are available.  You can hit this scenario when
reducing the # of max results because of the GPRC errors above, and repeatedly
making queries to ensure all tickets are reviewed & updated as required.

* token expired, even after updating env variable TOKEN 
> INFO:api:[SonraiGraphQLQuery] *** API AUTHENTICATION FAILED *** 
> INFO:api:[SonraiGraphQLQuery] Token has probably expired, you need to get a new one from the Advanced Search UI.

By default the sonrai.py module will check the on disk API token to see if
it has expired (/tmp/sonrai/token).  Get a new token from the advanced search
in Sonrai, and update the file, or delete it & reset your TOKEN environment
variable.     


#### Example Run outputs
    ip-192-168-10-29:api dwight$ ./closetickets.py -l /tmp/closetickets.txt -g  -m 1 -f "srn:integra::ControlFramework/6edf1db7-f636-42dc-9f3e-aff238446e18" -i
    2020-12-22 20:01:43,187:sonrai.py:__init__:INFO: logging level: DEBUG
    2020-12-22 20:01:43,187:sonrai.py:getToken:DEBUG: checking for filesystem token
    2020-12-22 20:01:43,187:sonrai.py:getToken:DEBUG: filesystem token found: /tmp/sonrai/token
    2020-12-22 20:01:43,188:sonrai.py:setGraphQLUrl:DEBUG: Pulling API server from token
    2020-12-22 20:01:43,188:sonrai.py:setGraphQLUrl:DEBUG: API server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:43,188:sonrai.py:validToken:DEBUG: expires: 1608766550
    2020-12-22 20:01:43,188:sonrai.py:tokenExpiring:DEBUG: checking token expiration
    2020-12-22 20:01:43,188:sonrai.py:tokenExpiring:DEBUG: expiry:1608766550 || current: 1608681703 || remaining: 84846s
    2020-12-22 20:01:43,188:sonrai.py:tokenExpiring:DEBUG: token not near expiration
    2020-12-22 20:01:43,188:sonrai.py:getToken:DEBUG: using valid filesystem token
    2020-12-22 20:01:43,188:sonrai.py:setGraphQLUrl:DEBUG: Pulling API server from token
    2020-12-22 20:01:43,188:sonrai.py:setGraphQLUrl:DEBUG: API server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:43,188:sonrai.py:getGraphQLUrl:DEBUG: Pulling API server from token
    2020-12-22 20:01:43,189:sonrai.py:getGraphQLUrl:DEBUG: API server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:43,189:closetickets.py:main:INFO: Closing tickets in Global swimlane
    2020-12-22 20:01:43,189:closetickets.py:main:INFO: Finding up to 1 tickets for swimlane srn:integra::Swimlane/Global
    2020-12-22 20:01:43,189:closetickets.py:queryTickets:DEBUG: Checking for tickets where:
    2020-12-22 20:01:43,189:closetickets.py:queryTickets:DEBUG:  - lastModified timestamp is  0 hours ago
    2020-12-22 20:01:43,189:closetickets.py:queryTickets:DEBUG:    (LT=older, GT=newer) (ticket.lastModified  1608681703 / 2020-12-22 20:01:43 -0400)
    2020-12-22 20:01:43,189:closetickets.py:queryTickets:DEBUG:  - ticketKey is srn:integra::ControlFramework/6edf1db7-f636-42dc-9f3e-aff238446e18
    2020-12-22 20:01:43,189:closetickets.py:queryTickets:DEBUG:    control policy SRN or control framework SRN
    variables:{"swimlanesrns": "srn:integra::Swimlane/Global", "limit": "1", "lastModifiedFilters": {"lastModified": {"op": "LT", "value": 1608681703}}, "ticketKeyFilter": {"ticketKey": {"value": "srn:integra::ControlFramework/6edf1db7-f636-42dc-9f3e-aff238446e18"}}}
    2020-12-22 20:01:43,189:closetickets.py:queryTickets:INFO: calling api for tickets in srn:integra::Swimlane/Global
    2020-12-22 20:01:43,276:urllib3.connectionpool:_new_conn:DEBUG: Starting new HTTPS connection (1): integra.sonraisecurity.com:443
    2020-12-22 20:01:43,510:urllib3.connectionpool:_make_request:DEBUG: https://integra.sonraisecurity.com:443 "POST /graphql HTTP/1.1" 200 188
    2020-12-22 20:01:43,510:sonrai.py:SonraiGraphQLQuery:DEBUG: status code: 200 / server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:43,511:closetickets.py:main:INFO: Open tickets found: 1
    2020-12-22 20:01:43,511:closetickets.py:main:INFO: Ticket srn logging enabled
    2020-12-22 20:01:43,511:closetickets.py:main:INFO: Complete. closed 0 tickets
    ip-192-168-10-29:api dwight$ ./closetickets.py -l /tmp/closetickets.txt -g  -m 1 -f "srn:integra::ControlFramework/6edf1db7-f636-42dc-9f3e-aff238446e18" -i -a
    2020-12-22 20:01:58,443:sonrai.py:__init__:INFO: logging level: DEBUG
    2020-12-22 20:01:58,443:sonrai.py:getToken:DEBUG: checking for filesystem token
    2020-12-22 20:01:58,443:sonrai.py:getToken:DEBUG: filesystem token found: /tmp/sonrai/token
    2020-12-22 20:01:58,444:sonrai.py:setGraphQLUrl:DEBUG: Pulling API server from token
    2020-12-22 20:01:58,444:sonrai.py:setGraphQLUrl:DEBUG: API server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:58,444:sonrai.py:validToken:DEBUG: expires: 1608766550
    2020-12-22 20:01:58,444:sonrai.py:tokenExpiring:DEBUG: checking token expiration
    2020-12-22 20:01:58,444:sonrai.py:tokenExpiring:DEBUG: expiry:1608766550 || current: 1608681718 || remaining: 84831s
    2020-12-22 20:01:58,444:sonrai.py:tokenExpiring:DEBUG: token not near expiration
    2020-12-22 20:01:58,444:sonrai.py:getToken:DEBUG: using valid filesystem token
    2020-12-22 20:01:58,444:sonrai.py:setGraphQLUrl:DEBUG: Pulling API server from token
    2020-12-22 20:01:58,444:sonrai.py:setGraphQLUrl:DEBUG: API server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:58,444:sonrai.py:getGraphQLUrl:DEBUG: Pulling API server from token
    2020-12-22 20:01:58,445:sonrai.py:getGraphQLUrl:DEBUG: API server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:58,445:closetickets.py:main:INFO: Closing tickets in Global swimlane
    2020-12-22 20:01:58,445:closetickets.py:main:INFO: Finding up to 1 tickets for swimlane srn:integra::Swimlane/Global
    2020-12-22 20:01:58,445:closetickets.py:queryTickets:DEBUG: Checking for tickets where:
    2020-12-22 20:01:58,445:closetickets.py:queryTickets:DEBUG:  - lastModified timestamp is  0 hours ago
    2020-12-22 20:01:58,445:closetickets.py:queryTickets:DEBUG:    (LT=older, GT=newer) (ticket.lastModified  1608681718 / 2020-12-22 20:01:58 -0400)
    2020-12-22 20:01:58,445:closetickets.py:queryTickets:DEBUG:  - ticketKey is srn:integra::ControlFramework/6edf1db7-f636-42dc-9f3e-aff238446e18
    2020-12-22 20:01:58,445:closetickets.py:queryTickets:DEBUG:    control policy SRN or control framework SRN
    variables:{"swimlanesrns": "srn:integra::Swimlane/Global", "limit": "1", "lastModifiedFilters": {"lastModified": {"op": "LT", "value": 1608681718}}, "ticketKeyFilter": {"ticketKey": {"value": "srn:integra::ControlFramework/6edf1db7-f636-42dc-9f3e-aff238446e18"}}}
    2020-12-22 20:01:58,445:closetickets.py:queryTickets:INFO: calling api for tickets in srn:integra::Swimlane/Global
    2020-12-22 20:01:58,501:urllib3.connectionpool:_new_conn:DEBUG: Starting new HTTPS connection (1): integra.sonraisecurity.com:443
    2020-12-22 20:01:58,737:urllib3.connectionpool:_make_request:DEBUG: https://integra.sonraisecurity.com:443 "POST /graphql HTTP/1.1" 200 188
    2020-12-22 20:01:58,738:sonrai.py:SonraiGraphQLQuery:DEBUG: status code: 200 / server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:58,738:closetickets.py:main:INFO: Open tickets found: 1
    2020-12-22 20:01:58,738:closetickets.py:main:INFO: Ticket srn logging enabled
    2020-12-22 20:01:58,739:closetickets.py:main:DEBUG: closing tickets on ACTIVE and INACTIVE resources.  ticketSRN: srn:integra::Ticket/7b9fdbec-e565-40e5-937c-f588369cebbd
    2020-12-22 20:01:58,739:closetickets.py:main:INFO: closing 1 tickets: ['srn:integra::Ticket/7b9fdbec-e565-40e5-937c-f588369cebbd']
    2020-12-22 20:01:58,739:closetickets.py:closeTickets:DEBUG:  calling api to close 1 tickets
    2020-12-22 20:01:58,745:urllib3.connectionpool:_new_conn:DEBUG: Starting new HTTPS connection (1): integra.sonraisecurity.com:443
    2020-12-22 20:01:58,963:urllib3.connectionpool:_make_request:DEBUG: https://integra.sonraisecurity.com:443 "POST /graphql HTTP/1.1" 200 73
    2020-12-22 20:01:58,963:sonrai.py:SonraiGraphQLQuery:DEBUG: status code: 200 / server: https://integra.sonraisecurity.com/graphql
    2020-12-22 20:01:58,963:closetickets.py:main:INFO: CloseTicketResponse: {'data': {'CloseTickets': {'successCount': 1, 'failureCount': 0}}}
    2020-12-22 20:01:58,970:closetickets.py:main:INFO: Complete. closed 1 tickets
    ip-192-168-10-29:api dwight$
