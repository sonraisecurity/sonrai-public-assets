import argparse
import json
import sys
import time
# import pandas as pd
import urllib.parse
import datetime
from datetime import timedelta, date
from urllib.parse import urlparse, parse_qs
from sonrai_api import api, logger

def build_graphql(url, q_file):
    # build the search for the SRNs based on either a graphql file or ticket screen URL
    logger.debug("Building Query")
    if q_file:
        # get the query from the specified file
        logger.debug("Using {} file to get query".format(q_file))
        try:
            with open(q_file, 'r') as file:
                query_from_file = file.read().strip()
                file.close()
        except Exception as e:
            print(f"An error occurred while reading the file: {e}")
            sys.exit(1)
        return query_from_file
    
    elif url:
        # from the URL parse out the filters and build the query
        logger.debug("Using URL {} to build the query".format(url))
        query_from_url = parse_url(url)
        return query_from_url
    
    else:
        logger.error("No valid query provided, either provide URL or query file")
        args.print_help()


def parse_url(url):
    # build a query based on values from a URL string
    decoded_url = urllib.parse.unquote(url)
    parsed_url = urlparse(decoded_url)
    query_params = parse_qs(parsed_url.query)
    
    where_clause = None
    for key in query_params:
        values = ""
        # q_filter = ""
        
        if key == "dateType":
            # build the date filter based on dateType and other fields
            if "endDate" in query_params and "startDate" in query_params:
                # build BETWEEN filter
                logger.debug("Using start date {} and end date {}".format(query_params["startDate"][0], query_params["endDate"][0]))
                q_filter = (' ' + query_params[key][0] + ': {op:BETWEEN, values:["' + query_params["startDate"][0] + '", "' + query_params["endDate"][0] + '"]}')
            elif "relativeDate" in query_params:
                offset_in_seconds = int((24 * 60 * 60 * float(query_params['relativeDate'][0])))
                current_time = datetime.datetime.utcnow()
                end_date = current_time.isoformat() + 'Z'
                current_time_minus_offset = current_time - datetime.timedelta(seconds=offset_in_seconds)
                start_date = current_time_minus_offset.isoformat() + 'Z'
                logger.debug("Using start date {} and end date {}".format(start_date, end_date))
                q_filter = (' ' + query_params[key][0] + ': {op:BETWEEN, values:["' + start_date + '", "' + end_date + '"]}')
            else:
                logger.error("invalid date filter can not proceed")
                sys.exit(1)
        elif key == "endDate" or key == "startDate" or key == "relativeDate":
            # we dealt with the dates in the dataType block above
            continue
        elif key == "sortDirection" or key == "sortColumn":
            # we don't need to worry about sorting, so ignoring
            continue
        elif key == "pageIndex":
            # we don't need to worry about the pageIndex, so ignoring
            continue
        else:
            # get all the values for a key and build IN_LIST filter
            for value in query_params[key]:
                values += '"' + value + '" '
            q_filter = (' ' + key + ': {op:IN_LIST, values:[' + values + ']}')
        
        if where_clause is None:
            # create the where clause
            where_clause = q_filter
        else:
            # add to the where clause
            where_clause += q_filter
    
    if args.export:
        # getting most of the same fields the UI grabs for an export
        full_query = '''
            query Tickets ($limit: Long, $offset: Long) { Tickets (where: { ''' + where_clause + ''' } )
            { globalCount count items (limit:$limit offset:$offset ''' + includeRisk + ''') {
                resourceName
                severityNumeric
                title
                policy{alertingLevelNumeric}
                ticketType
                firstSeen
                lastSeen
                createdBy
                account
                assignedTo
                createdDate
                transitionedBy
                transitionDate
                lastModified
                status
                swimlanes{title}
                swimlaneSRNs
                srn
            } } }
        '''
    else:
        # only need the SRN of the tickets for all actions except export
        full_query = '''
        query Tickets ($limit: Long, $offset: Long) { Tickets (where: { ''' + where_clause + ''' } )
             { globalCount count items (limit:$limit offset:$offset ''' + includeRisk + ''') {srn} } }
        '''
    logger.debug("URL Query Filter = {}".format(full_query))
    return full_query


def add_comment_to_tickets(data, comment):
    # find the current user's srn (aka the user of the token)
    logger.info("Adding Comments to tickets")
    sonrai_current_users = '{SonraiCurrentUsers {items {srn}}}'
    user_response = api.execute_query(sonrai_current_users)
    user_srn = user_response['data']['SonraiCurrentUsers']['items'][0]['srn']
    logger.debug("Comment User SRN = {}".format(user_srn))
    bulk_comment_mutation = '''mutation CreateTicketCommentBulk($requests: [CreateTicketCommentRequestInput]) {
  CreateTicketCommentBulk(input: {requests: $requests}) {
    results {
      ticketComment {
        srn
      }
      success
      error
    }
  }
}'''
    counter = 0
    total_count = 0
    ticket_var = {"requests": []}

    # find the last ticket's srn, so we know when we are done the loop, and we can execute the mutation one last time
    last_ticket_srn = data['data']['Tickets']['items'][-1]['srn']
    global_count = data['data']['Tickets']['globalCount']
    for ticket in data['data']['Tickets']['items']:
        # walk through all tickets
        if counter == 0:
            # re-init the variable after each [tickets_per_cycle] tickets
            logger.debug("Preparing {} tickets to add comment".format(tickets_per_cycle))
            ticket_var = {"requests": []}
        new_item = {"ticketSrn": ticket['srn'], "createdBy": user_srn, "body": comment}
        ticket_var['requests'].append(new_item)
        counter += 1
        total_count += 1
        if counter == tickets_per_cycle or last_ticket_srn == ticket['srn']:
            # we have [tickets_per_cycle] tickets or have reached the last ticket, time to reset the counter and then add comments to the ones already processed
            results = api.execute_query(bulk_comment_mutation, ticket_var)
            logger.debug("Added comments to tickets {} / {}".format(total_count, global_count))
            counter = 0

    logger.info("Comments were added to {} total tickets".format(total_count))
    
    
def get_user_srn(email):
    # routine to translate email address to srn
    sonrai_users_query = '''{SonraiUsers {count items {email srn}}}'''
    user_list = api.execute_query(sonrai_users_query)
    user_srn = None
    for user in user_list['data']['SonraiUsers']['items']:
        if user['email'] == email:
            user_srn = user['srn']
            break
    
    if user_srn is None:
        # if we didn't find a valid email address then exit because we can't assign to anyone
        logger.error("email address {} not found in SonraiUsers".format(email))
        sys.exit(1)
        
    return user_srn


def assign_tickets(user_email, data):
    # this will assign tickets based on the query provided to 'user_email'
    # translate user_email into user_srn
    user_srn = get_user_srn(user_email)
    
    assign_tickets_mutation = '''
    mutation AssignTicketBulk($requests: [AssignTicketRequestInput]) {
  AssignTicketBulk(input: {requests: $requests}) {
    results {
      ticketSrn
      success
      error
    }
  }
}
'''
    counter = 0
    total_count = 0
    ticket_var = {"requests": []}
    
    # find the last ticket's srn so we know when we are done the loop and we can execute the mutation one last time
    last_ticket_srn = data['data']['Tickets']['items'][-1]['srn']

    for ticket in data['data']['Tickets']['items']:
        # walk through all tickets
        if counter == 0:
            # re-init the variable after each [tickets_per_cycle] tickets
            ticket_var = {"requests": []}
        new_item = {"ticketSrn": ticket['srn'], "userSrn": user_srn}
        ticket_var['requests'].append(new_item)
        counter += 1
        total_count += 1
        if counter == tickets_per_cycle or last_ticket_srn == ticket['srn']:
            # we have [tickets_per_cycle] tickets or have reached the last ticket, time to reset the counter and then add comments to the ones already processed
            counter = 0
            results = api.execute_query(assign_tickets_mutation, ticket_var)
            logger.debug("results of assigning tickets {}".format(results))
    logger.info("Assigned {} tickets to {} ({})".format(total_count, user_email, user_srn))
    

def calculate_snooze_until(snooze_days):
    snooze_date = date.today() + timedelta(days=snooze_days)
    logger.debug("Snooze Until date set to {}".format(snooze_date))
    return snooze_date


def update_ticket_status(action, data, snooze_days=None):
    # this will change status of tickets
    # possible actions and the new Status
    # ReopenTickets = 'NEW'
    # CloseTickets = 'CLOSED'
    # SnoozeTickets = 'SNOOZED'
    # AcceptRiskTickets = 'RISK_ACCEPTED'
    
    # this mutation works for NEW, CLOSED, RISK_ACCEPTED but not snooze will have to adjust below for snoozing
    ticket_status_mutation = """mutation update_ticket_status($srns: [String]) {
    [action] (input: {srns: $srns}) {
    successCount
    failureCount
  }
}"""
    
    snooze_date = None
    # calculate the `snoozeUntil` date for SnoozeTickets
    if action == 'SnoozeTickets':
        snooze_date = calculate_snooze_until(snooze_days)
        snooze_json = {'snoozedUntil': str(snooze_date)}
        ticket_status_mutation = """mutation update_ticket_status($srns: [String], $snoozedUntil: DateTime) {
        [action] (input: {srns: $srns}, snoozedUntil: $snoozedUntil) {
        successCount
        failureCount
      }
    }"""

    ticket_status_mutation = ticket_status_mutation.replace("[action]", action)
    counter = 0
    total_count = 0
    ticket_var = {"srns": []}
    if snooze_date is not None:
        # for snoozed tickets we need to add the snoozeUntil value to the json
        ticket_var.update(snooze_json)
    
    # find the last ticket's srn so we know when we are done the loop and we can execute the mutation one last time
    last_ticket_srn = data['data']['Tickets']['items'][-1]['srn']
    
    for ticket in data['data']['Tickets']['items']:
        # walk through all tickets
        if counter == 0:
            # re-init the variable after each [tickets_per_cycle] tickets
            ticket_var = {"srns": []}
            if snooze_date is not None:
                # for snoozed tickets we need to add the snoozeUntil value to the json
                ticket_var.update(snooze_json)
        ticket_var['srns'].append(ticket['srn'])
        counter += 1
        total_count += 1
        if counter == tickets_per_cycle or last_ticket_srn == ticket['srn']:
            # we have [tickets_per_cycle] tickets or have reached the last ticket, time to reset the counter and then add comments to the ones already processed
            counter = 0
            results = api.execute_query(ticket_status_mutation, ticket_var)
            logger.debug(results)
            
    logger.info("Performed action {} on {} tickets".format(action, total_count))
    

def query_tickets(query):
    # This is used to loop the tickets [tickets_per_cycle] at a time until they are all captured
    offset = 0
    limit = tickets_per_cycle
    total = 0
    myretries = 0
    count = None
    results = {}
    while count is None or count == tickets_per_cycle:
        # looping through up to [tickets_per_cycle] at a time
        query_vars = json.dumps({"limit": limit, "offset": offset})
        logger.debug("querying {} tickets, offset: {}".format(limit, offset))
        success = False
        
        while success == False:
            try:
                data = api.execute_query(query, query_vars)
                if 'errors' in data:
                    # check to see if there are any errors in the results, if so stop processing
                    logger.error("Invalid query {}".format(data))
                    logger.error("Validate query before proceeding")
                    sys.exit(1)
                count = data['data']['Tickets']['count']
                globalCount = str(data['data']['Tickets']['globalCount'])
                
                if results == {}:
                    # this is the first query, so no value in results, just copying the data value into results
                    results = data.copy()
                else:
                    # this is all subsequent passes, where we are extending the results with the data
                    results['data']['Tickets']['items'].extend(data['data']['Tickets']['items'])
                    results['data']['Tickets']['count'] += count
                
                logger.debug("adding " + str(count) + " tickets to the results (" + str(results['data']['Tickets']['count']) + "/" + globalCount + ")")
                # logger.debug("success=True")
                success = True
            
            except Exception as e:
                logger.debug(Exception)
                logger.debug(e)
                myretries += 1
                if myretries == 10:
                    # abandon ship
                    raise SonraiAPIException("max retries (10) hit - giving up")
                
                logger.debug("error, waiting 60 seconds and then retry - " + str(myretries))
                time.sleep(60)
            
        # upon successful query, reset retries & increment the offset
        myretries = 0
        if count == limit:
            offset += limit
    
    logger.info("Total number of results from query: {}".format(results['data']['Tickets']['count']))
    return results


def export_to_file(data, query):
    # export data
    if args.csv:
        # export as CSV
        export_to_csv(data, query)
    else:
        json_object = json.dumps(data, indent=4)
        with open(args.export, "w") as outfile:
            outfile.write(json_object)
            
            
def get_fields(parent_key, dic, depth):
    # print(dic)
    print("depth:" + str(depth))
    fields = []
    if depth == 0:
        return "NoNewKeys"
    for key in dic:
        print("key:"+key)
        new_key = parent_key + '.' + key
        if isinstance(dic[key], dict):
            new_fields = (get_fields(new_key, dic[key], depth-1))
            print("new_fields:" + str(new_fields))
            if new_fields == "NoNewKeys":
                pass
            else:
                for f in new_fields:
                    fields.append(f)
        else:
            fields.append(new_key)
    # print(fields)
    return fields
    
            
def export_to_csv(data, query):
    # save the output to CSV
    # this needs to be worked on
    # print(data)
    # fields = get_fields('data.Tickets.items', data['data']['Tickets']['items'][0], 3)
    # print(fields)
    logger.error("This option is not complete at this time, export to JSON is the only option available")
    

# Create the parser
parser = argparse.ArgumentParser(description='')
query_method = parser.add_mutually_exclusive_group(required=True)

# Add the command line options
query_method.add_argument('-f', '--file', type=str, help='File containing graphQL query for tickets')
query_method.add_argument('-u', '--url', type=str, help='UI URL to ticket screen with the query to run. Must be a quoted string')
parser.add_argument('-l', '--limit', type=int, default=1000, help='The limit of tickets to be pulled with each pass. DEFAULT = 1000')
parser.add_argument('--findings', '--includeRisk', action="store_true", help=argparse.SUPPRESS)
parser.add_argument('-m', '--message', type=str, help='Message or comment to add to ticket(s). Must be a quoted string. A comment is required for all actions except --export')
parser.add_argument('-a', '--assign', metavar='EMAIL', help='Assign ticket(s) to user with <EMAIL>')
parser.add_argument('-c', '--close', action='store_true', default=None, help='Close ticket(s) from search')
parser.add_argument('-o', '--open', action='store_true', default=None, help='Re-Open ticket(s) from the search')
parser.add_argument('-r', '--risk_accept', action='store_true', default=None, help='Risk Accept ticket(s) from search')
parser.add_argument('-s', '--snooze', type=int, metavar="TIME", help='Snooze ticket(s) from search for <TIME> days')
parser.add_argument('-e', '--export', type=str, metavar="FILE", help='Export ticket(s) to JSON <FILE>')
parser.add_argument('--csv', action="store_true", help=argparse.SUPPRESS)
# parser.add_argument('--csv', action="store_true", help='Override default JSON file format to be CSV format')

# Parse the command line options
args = parser.parse_args()

# determine the number of actions other than comment (aka message)
num_of_actions = sum([args.assign is not None, args.close is not None, args.risk_accept is not None,
                      args.snooze is not None, args.export is not None, args.open is not None])

if num_of_actions == 0 and args.message is None:
    print("please provide at least one action")
    parser.print_help()
    sys.exit(1)
elif num_of_actions > 1:
    print("too many actions provided, please one only action at a time")
    parser.print_help()
    sys.exit(1)

# determine if the action is NOT an export or assign user, in which case we need a comment
if not (args.export or args.assign) and args.message is None:
    # need to provide a comment before proceeding
    print("Action requires a comment before proceeding")
    parser.print_help()
    sys.exit(1)

#set the number of tickets to pull with each pass
tickets_per_cycle = args.limit

#set the includeRisk to false by default (aka: findings)
includeRisk = 'includeRisk:false'
if args.findings:
    # set to true to include the risk findings
    includeRisk = 'includeRisk:true'

ticket_query = build_graphql(args.url, args.file)

# gather the list of tickets based on the filter
response = query_tickets(ticket_query)

# check to see if there are no tickets found and exit if that is the case.
if response['data']['Tickets']['count'] == 0:
    logger.info("No tickets found with query, no action will be performed")
    sys.exit(0)
    
# we have tickets so perform the necessary action
if args.assign:
    # assign tickets from query
    assign_tickets(args.assign, response)
elif args.close:
    # close tickets from query
    add_comment_to_tickets(response, args.message)
    update_ticket_status("CloseTickets", response)
elif args.open:
    # open tickets from query
    add_comment_to_tickets(response, args.message)
    update_ticket_status("ReopenTickets", response)
elif args.risk_accept:
    # risk accept tickets from query
    add_comment_to_tickets(response, args.message)
    update_ticket_status("AcceptRiskTickets", response)
elif args.snooze:
    # snooze tickets from query
    add_comment_to_tickets(response, args.message)
    update_ticket_status("SnoozeTickets", response, args.snooze)
elif args.export:
    # save results from ticket query
    export_to_file(response, ticket_query)
elif args.message:
    # add comment/message to tickets from query
    add_comment_to_tickets(response, args.message)
else:
    # something went wrong
    print("error: No valid operation provided")
    parser.print_help()
    sys.exit(1)
