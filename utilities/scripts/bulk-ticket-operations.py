import argparse
import json
import sys
import time
import pandas as pd
import urllib.parse
import datetime
import re
from datetime import timedelta, date
from urllib.parse import urlparse, parse_qs
from sonrai_api import api, logger


def build_graphql(q_file):
    # build the search for the SRNs based on either a graphql file or ticket screen URL
    logger.debug("Building Query")
    # get the query from the specified file
    logger.debug("Using {} file to get query".format(q_file))
    try:
        with open(q_file, 'r') as file:
            query_from_file = file.read().strip()
        file.close()
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        sys.exit(100)
    return query_from_file


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
        sys.exit(103)
    
    return user_srn


def assign_findings(user_email, query):
    # this will assign findings based on the query provided to 'user_email'
    # translate user_email into user_srn
    user_srn = get_user_srn(user_email)
    
    where_clause_str = extract_where_clause(query)
    
    # this mutation works for NEW, CLOSED, RISK_ACCEPTED but not snooze will have to adjust below for snoozing
    finding_status_mutation = """mutation reassignListFinding {
    ReassignListFindings (input: {where: [where] assignee:"[user]" } ) {
            ackMessage
            taskId
            taskSize
        }
    }"""
    
    # replace the values in the mutation
    finding_status_mutation = finding_status_mutation.replace("[where]", where_clause_str)
    finding_status_mutation = finding_status_mutation.replace("[user]", user_srn)
    
    mutation_var = "{}"
    results = api.execute_query(finding_status_mutation, mutation_var)
    if 'errors' in results:
        # something went wrong, dump the error and exit
        logger.error("ERROR:{}".format(results))
        sys.exit(110)
    logger.debug(results)
    
    logger.info("ReassignListFindings: {}".format(results['data']['ReassignListFindings']['ackMessage']))
    

def calculate_snooze_until(snooze_days):
    snooze_date = date.today() + timedelta(days=snooze_days)
    logger.debug("Snooze Until date set to {}".format(snooze_date))
    return snooze_date


def extract_where_clause(query):
    # use this to extract the "where" clause from the query
    start_token = "where:"
    stack = []
    start_index = query.find(start_token)

    if start_index == -1:
        return "No 'where' clause found"

    start_index += len(start_token)
    in_where_clause = False
    where_clause = ""

    for i, char in enumerate(query[start_index:], start=start_index):
        if char == '{':
            stack.append(char)
            in_where_clause = True
        elif char == '}':
            stack.pop()
        if in_where_clause:
            where_clause += char
        if in_where_clause and not stack:
            break

    return where_clause.strip() if where_clause else "No 'where' clause found"
    

def update_finding_status(action, comment, query, data, snooze_days=None):
    # this will change status of findings and add a comment
    # possible actions and the new Status
    # ReopenListFindings = 'NEW'
    # CloseListFindings = 'CLOSED'
    # SnoozeListFindings = 'SNOOZED'
    # AcceptRiskListFindings = 'RISK_ACCEPTED'
    
    # get the where clause out of the query
    where_clause_str = extract_where_clause(query)
    
    # this mutation works for NEW, CLOSED, RISK_ACCEPTED but not snooze will have to adjust below for snoozing
    finding_status_mutation = """mutation update_finding_status {
    [action] (input: {where: [where] comment:"[comment]" } ) {
            ackMessage
            taskId
            taskSize
      }
    }"""
    
    # calculate the `snoozeUntil` date for SnoozeFindings
    if action == 'SnoozeListFindings':
        snooze_date = calculate_snooze_until(snooze_days)
        finding_status_mutation = """mutation update_finding_status {
        [action] (input: {where: [where] comment:"[comment]" } snoozedUntil:"[snoozedUntil]" ) {
                ackMessage
                taskId
                taskSize
          }
        }"""
        # replace the snooze date in the mutation
        finding_status_mutation = finding_status_mutation.replace("[snoozedUntil]", str(snooze_date) )


    # replace the values in the mutation
    finding_status_mutation = finding_status_mutation.replace("[action]", action)
    finding_status_mutation = finding_status_mutation.replace("[where]", where_clause_str)
    finding_status_mutation = finding_status_mutation.replace("[comment]", comment)
    
    mutation_var = "{}"
    results = api.execute_query(finding_status_mutation, mutation_var)
    if 'errors' in results:
        # something went wrong, dump the error and exit
        logger.error("ERROR:{}".format(results))
        sys.exit(110)
    logger.debug(results)
    
    logger.info("{}: {}".format(action, results['data'][action]['ackMessage']))


def query_findings(query):
    logger.info("Querying Findings")
    # This is used to loop the findings [findings_per_cycle] at a time until they are all captured
    offset = 0
    limit = findings_per_cycle
    total = 0
    my_retries = 0
    count = None
    results = {}
    display_count = True
    while count is None or count == findings_per_cycle:
        # looping through up to [findings_per_cycle] at a time
        query_vars = json.dumps({"limit": limit, "offset": offset})
        logger.debug("querying {} findings, offset: {}".format(limit, offset))
        success = False
        
        while not success:
            try:
                data = api.execute_query(query, query_vars)
                if 'errors' in data:
                    # check to see if there are any errors in the results, if so stop processing
                    logger.error("Invalid query {}".format(data))
                    logger.error("Validate query before proceeding")
                    sys.exit(104)
                count = data['data']['ListFindings']['pageCount']
                globalCount = str(data['data']['ListFindings']['totalCount'])
                if display_count:
                    logger.info("Total results matching query: {}".format(globalCount))
                    display_count = False  # only need to display this once
                
                if results == {}:
                    # this is the first query, so no value in results, just copying the data value into results
                    results = data.copy()
                else:
                    # this is all subsequent passes, where we are extending the results with the data
                    results['data']['ListFindings']['items'].extend(data['data']['ListFindings']['items'])
                    results['data']['ListFindings']['pageCount'] += count
                
                logger.debug("adding " + str(count) + " findings to the results (" + str(results['data']['ListFindings']['pageCount']) + "/" + globalCount + ")")
                # logger.debug("success=True")
                success = True
            
            except Exception as e:
                logger.debug(Exception)
                logger.debug(e)
                my_retries += 1
                if my_retries == 10:
                    # abandon ship
                    raise SonraiAPIException("max retries (10) hit - giving up")
                
                logger.debug("error, waiting 60 seconds and then retry - " + str(my_retries))
                time.sleep(60)
        
        # upon successful query, reset retries & increment the offset
        my_retries = 0
        if count == limit:
            offset += limit
    
    logger.info("Total number of results from query: {}".format(results['data']['ListFindings']['pageCount']))
    return results


def export_to_file(data, query):
    # export data
    if args.csv:
        # export as CSV
        export_to_csv(data, query)
    else:
        # export to JSON (default)
        logger.info("Exporting result to JSON file: {}".format(args.export))
        json_object = json.dumps(data, indent=4)
        with open(args.export, "w") as outfile:
            outfile.write(json_object)


def export_to_csv(data, query):
    # save the output to CSV
    logger.info("Exporting result to CSV file: {}".format(args.export))
    json_object = json.dumps(data['data']['ListFindings']['items'])
    df = pd.read_json(json_object)
    df.to_csv(args.export, encoding='utf-8', index=False)
    
    
def convert_framework_srns_to_titles(data):
    # do a lookup of the frameworks srns and add the title
    # do a lookup of all swimlanes
    logger.info("Converting frameworkSrns to Control Framework Names")
    framework_query = ''' query framework { ControlFrameworks { items { srn title } } }'''
    framework_json = api.execute_query(framework_query)
    framework_list = {}
    for framework_obj in framework_json['data']['ControlFrameworks']['items']:
        # build a dict of all the swimlanes srn to title
        framework_list[framework_obj['srn']] = framework_obj['title']
    # this is a list of the different types of swimlanes fields found in an export
    i = 0  # initialize the counter
    for finding in data['data']['ListFindings']['items']:
        # process each finding we have
        if 'frameworkSrns' in finding:
            # if it exists continue
            if finding['frameworkSrns'] is None:
                # if it is None skip it.
                continue
            # if this swimlane type exists with real swimlanes add the equivalent with Name appended
            data['data']['ListFindings']['items'][i]['frameworkNames'] = []
        else:
            # it doesn't exist, try the next swimlane type
            continue
        try:
            # putting in handling for swimlane fields that might be empty
            for fw in finding['frameworkSrns']:
                # add the swimlane name to the array
                if fw not in framework_list:
                    # old deleted swimlane, replace name with "Deleted Swimlane"
                    data['data']['ListFindings']['items'][i]['frameworkNames'].append("Deleted Framework")
                else:
                    data['data']['ListFindings']['items'][i]['frameworkNames'].append(framework_list[fw])
        except Exception as e:
            # empty swimlane field, nothing to do
            logger.debug("framework field doesn't exist, nothing to worry about:" + str(e))
            pass
        i += 1  # increment the pointer
    return data


def get_sonrai_user_details():
    # do a lookup of the sonrai users details
    logger.info("Getting Sonrai User information")
    sonrai_user_query = '''query sonrai_users { SonraiUsers  { items { srn name email } } }'''
    sonrai_user_json = api.execute_query(sonrai_user_query)
    user_name_list = {}
    user_email_list = {}
    for user_obj in sonrai_user_json['data']['SonraiUsers']['items']:
        # build a dicts of all users, mapping srn to name and srn to email
        user_name_list[user_obj['srn']] = user_obj['name']
        user_email_list[user_obj['srn']] = user_obj['email']
    
    return user_name_list, user_email_list


def convert_assignee_srns_to_names(data, user_name_list, user_email_list):
    # if a finding has an assignee, add the user's email and name
    logger.info("Converting assignee srns to emails and names")
    i = 0 # initialize the counter
    for finding in data['data']['ListFindings']['items']:
        # process each finding we have
        if "assignee" in finding:
            # if there is an assignee field exists, add name and email
            if finding['assignee'] is None:
                # No Assignee, setting to None
                data['data']['ListFindings']['items'][i]['assignee_name'] = finding['assignee']
                data['data']['ListFindings']['items'][i]['assignee_email'] = finding['assignee']
            else:
                # if this swimlane type exists with real swimlanes add the equivalent with Name appended
                data['data']['ListFindings']['items'][i]['assignee_name'] = user_name_list[finding['assignee']]
                data['data']['ListFindings']['items'][i]['assignee_email'] = user_email_list[finding['assignee']]
            
        i += 1  # increment the pointer
    return data


def convert_swimlane_srns_to_names(data):
    # do a lookup of all swimlanes
    logger.info("Converting all swimlane field srns to swimlane titles")
    swimlane_query = ''' query swimlanes { Swimlanes { items { srn title } } }'''
    swimlanes_json = api.execute_query(swimlane_query)
    swimlane_list = {}
    for swimlane_obj in swimlanes_json['data']['Swimlanes']['items']:
        # build a dict of all the swimlanes srn to title
        swimlane_list[swimlane_obj['srn']] = swimlane_obj['title']
    # this is a list of the different types of swimlanes fields found in an export
    swimlane_field_types = ['swimlanes', 'operationalizedSwimlanes', 'resourceSwimlanes']
    i = 0  # initialize the counter
    for finding in data['data']['ListFindings']['items']:
        # process each finding we have
        for sw_type in swimlane_field_types:
            # loop through each swimlane type
            if sw_type in finding:
                # if it exists continue
                if finding[sw_type] is None:
                    # if it is None skip it.
                    continue
                # if this swimlane type exists with real swimlanes add the equivalent with Name appended
                data['data']['ListFindings']['items'][i][sw_type + 'Names'] = []
            else:
                # it doesn't exist, try the next swimlane type
                continue
            try:
                # putting in handling for swimlane fields that might be empty
                for sw in finding[sw_type]:
                    # add the swimlane name to the array
                    if sw not in swimlane_list:
                        # old deleted swimlane, replace name with "Deleted Swimlane"
                        data['data']['ListFindings']['items'][i][sw_type + 'Names'].append("Deleted Swimlane")
                    else:
                        data['data']['ListFindings']['items'][i][sw_type + 'Names'].append(swimlane_list[sw])
            except Exception as e:
                # empty swimlane field, nothing to do
                logger.debug("Swimlane field doesn't exist, nothing to worry about:" + str(e))
                pass
        i += 1  # increment the pointer
    return data


def dump_finding_comments(data, user_name_list, user_email_list):
    # grab all finding comments. This can be slow.
    logger.info("Getting comments for all {} findings".format(data['data']['ListFindings']['totalCount']))
    query_list_comments = '''query ListComments($srn: String) {
        ListCommentsForFinding(where: { findingSrn: { op: EQ, value: $srn } }){
          items{
            body
            timestamp
            createdBy
          }
        }
      }
    '''
    i = 0  # initialize the counter as a pointer
    for finding in data['data']['ListFindings']['items']:
        # get the comments for each Finding
        var_list_comments = json.dumps({"srn":finding['srn']})
        logger.debug("Getting comments for {} ".format(finding['srn']))
        comments = api.execute_query(query_list_comments, var_list_comments)
        j = 0 # counter for pointer to emails
        if comments['data']['ListCommentsForFinding']['items'] is not None:
            for obj in comments['data']['ListCommentsForFinding']['items']:
                if obj['createdBy'] is None or obj['createdBy'] not in user_name_list:
                    # handle the cases where a comment is nameless or user was deleted
                    continue
                comments['data']['ListCommentsForFinding']['items'][j]['createBy_name'] = user_name_list[obj['createdBy']]
                comments['data']['ListCommentsForFinding']['items'][j]['createBy_email'] = user_email_list[obj['createdBy']]
                j += 1
        
        data['data']['ListFindings']['items'][i]['Comments'] = comments['data']['ListCommentsForFinding']['items']
        i += 1
        
    return data


# Create the parser
parser = argparse.ArgumentParser(description='')

# Add the command line options
parser.add_argument('-f', '--file', type=str, help='File containing graphQL query for findings')
parser.add_argument('-l', '--limit', type=int, default=1000, help='The limit of findings to be pulled with each pass. DEFAULT = 1000')
parser.add_argument('-m', '--message', type=str, help='Message or comment to add to finding(s). Must be a quoted string. A comment is required for all actions except --export')
parser.add_argument('-a', '--assign', metavar='EMAIL', help='Assign finding(s) to user with <EMAIL>')
parser.add_argument('-c', '--close', action='store_true', default=None, help='Close finding(s) from search')
parser.add_argument('-o', '--open', action='store_true', default=None, help='Re-Open finding(s) from the search')
parser.add_argument('-r', '--risk_accept', action='store_true', default=None, help='Risk Accept finding(s) from search')
parser.add_argument('-s', '--snooze', type=int, metavar="TIME", help='Snooze finding(s) from search for <TIME> days')
parser.add_argument('-e', '--export', type=str, metavar="FILE", help='Export finding(s) to <FILE>. Default format is JSON')
parser.add_argument('--name_lookup', action='store_true', default=False, help='Convert all Swimlane SRNs, Framework SRNs, Assignee SRNs to equivalent names')
parser.add_argument('--list_comments', action='store_true', default=False, help='For each ticket or finding, grab the associated comments')
parser.add_argument('--csv', action="store_true", help='Used with -e option to export findings in csv format')
# parser.add_argument('--csv', action="store_true", help='Override default JSON file format to be CSV format')

# Parse the command line options
args = parser.parse_args()

# verify inputs for valid data
# file name pattern
file_pattern = '([a-zA-Z]:\\|\/)?([\w\s][\/])*([\w\s]\.\w+)?'
if args.file and not re.search(file_pattern, args.file):
    logger.error("Not a valid filename {}".format(args.file))
    sys.exit(200)

if args.limit and args.limit > 10000:
    logger.error("Limit of {} is not in a valid range of 1-10000.".format(args.limit))
    sys.exit(202)

message_pattern = "[a-zA-Z0-9 .,?!]{1,1000}"
if args.message and not re.search(message_pattern, args.message):
    logger.error("Not a valid comment string {}".format(args.message))
    sys.exit(203)

if args.snooze and args.snooze > 10000:
    logger.error("Snooze value of {} is not in a valid range of 1-10000.".format(args.snooze))
    sys.exit(204)

email_pattern = "([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+"
if args.assign and not re.search(email_pattern, args.assign):
    logger.error("The email address is not a valid pattern {}".format(args.assign))
    sys.exit(205)

if args.export and not re.search(file_pattern, args.export):
    logger.error("Not a valid filename {}".format(args.export))
    sys.exit(200)

# determine the number of actions other than comment (aka message)
num_of_actions = sum([args.assign is not None, args.close is not None, args.risk_accept is not None,
                      args.snooze is not None, args.export is not None, args.open is not None])

if num_of_actions == 0 and args.message is None:
    print("please provide at least one action")
    parser.print_help()
    sys.exit(105)
elif num_of_actions > 1:
    print("too many actions provided, please one only action at a time")
    parser.print_help()
    sys.exit(106)

# determine if the action is NOT an export or assign user, in which case we need a comment
if not (args.export or args.assign) and args.message is None:
    # need to provide a comment before proceeding
    print("Action requires a comment before proceeding")
    parser.print_help()
    sys.exit(107)

# set the number of findings to pull with each pass
findings_per_cycle = args.limit

finding_query = build_graphql(args.file)

# gather the list of findings based on the filter
response = query_findings(finding_query)

# check to see if there are no findings found and exit if that is the case.
if response['data']['ListFindings']['pageCount'] == 0:
    logger.info("No findings found with query, no action will be performed")
    sys.exit(0)
    
user_names = user_emails = None
if args.name_lookup or args.list_comments:
    (user_names, user_emails) = get_sonrai_user_details()

if args.name_lookup:
    # we need to convert the swimlane SRNs to Names
    response = convert_swimlane_srns_to_names(response)
    response = convert_framework_srns_to_titles(response)
    response = convert_assignee_srns_to_names(response, user_names, user_emails)

if args.list_comments:
    # look up the comments on the findings/tickets and add to the response blob
    response = dump_finding_comments(response, user_names, user_emails)

# we have findings so perform the necessary action
if args.assign:
    # assign findings from query
    assign_findings(args.assign, finding_query)
elif args.close:
    # close findings from query
    update_finding_status("CloseListFindings", args.message, finding_query, response)
elif args.open:
    # open findings from query
    update_finding_status("ReopenListFindings", args.message, finding_query, response)
elif args.risk_accept:
    # risk accept findings from query
    update_finding_status("RiskAcceptListFindings",args.message, finding_query, response)
elif args.snooze:
    # snooze findings from query
    update_finding_status("SnoozeListFindings", args.message, finding_query, response, args.snooze)
elif args.export:
    # save results from finding query
    export_to_file(response, finding_query)
else:
    # something went wrong
    print("error: No valid operation provided")
    parser.print_help()
    sys.exit(108)
