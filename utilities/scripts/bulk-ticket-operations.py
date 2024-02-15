import argparse
import json
import sys
import time
import pandas as pd
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
            sys.exit(100)
        return query_from_file
    
    elif url:
        # from the URL parse out the filters and build the query
        logger.debug("Using URL {} to build the query".format(url))
        query_from_url = parse_url(url)
        return query_from_url
    
    else:
        logger.error("No valid query provided, either provide URL or query file")
        args.print_help()


def build_values(parameters):
    values = ""
    for value in parameters:
        values += '"' + value + '" '
    return values


def query_schema():
    # this sub is for pulling own all the fields in the ListFindings endpoint so we can figure out what type the fields are
    # and then can figure out the appropriate operator to use
    query_schema = '''
    query t {
  __type(name: "ListFindings") {
    name
    fields {
      name
      type {
        ofType {
          name
          fields {
            name
            type {
              kind
              }
           
          }
        }
      }
    }
  }
}
    '''
    results_schema = api.execute_query(query_schema)
    
    field_list = {}
    for field in results_schema['data']['__type']['fields'][0]['type']['ofType']['fields']:
        field_list[field['name']] = field['type']['kind']
        
    # need to add a special type of freetext queries since they use a different operator
    field_list['freeText'] = 'special'
    return field_list


def get_updated_mapping(key):
    # certain URL fields are no longer in use for the ListFindings endpoint.
    # Will remap here
    if key == "controlFrameworkSrn":
        # controlFrameworkSrn is the old URL key still in use and needs to be mapped to the frameworkSrns field
        updated_key = 'frameworkSrns'
    elif key == "swimlaneSrns":
        # controlFrameworkSrn is the old URL key still in use and needs to be mapped to the frameworkSrns field
        updated_key = 'swimlanes'
    elif "ticket" in key:
        # "ticket" keyword fields are the old endpoint fields still in use with the URL and needs to be mapped to the "finding" keyword fields with the new endpoint
        updated_key = key.replace('ticket', 'finding')
    elif key == "controlPolicyMetaType":
        updated_key = 'metaType'
    elif key == "environment":
        updated_key = 'environments'
    elif key == "securityArea":
        updated_key = 'securityAreas'
    elif key == "objectiveSrn":
        updated_key = 'objectiveSrns'
    elif key == "resourceSRN":
        updated_key = 'resourceSrn'
    elif key == "assignedTo":
        updated_key = 'assignee'
    elif key == "transitionedBy":
        updated_key = 'lastTransitionedBy'
    elif key == "standardSrn":
        updated_key = 'standardSrns'
    elif key == "standardFamilySrn":
        updated_key = 'standardFamilySrns'
    elif key == "standardControlSrn":
        updated_key = 'standardControlSrns'
    elif key == "freetext":
        updated_key = 'freeText'
    else:
        # nothing matches so no need to remap
        updated_key = key
        
    return updated_key


def get_operator(field_type):
    # return the type of operator required for based on the field type
    if field_type == "LIST":
        op = "ARRAY_CONTAINS"
    elif field_type == "SCALAR":
        op = "IN_LIST"
    elif field_type == "special":
        op = "ARRAY_CONTAINS_LIKE"
    else:
        # something went wrong error out
        logger.error("field type of {} is not a valid option for building a search".format(field_type))
        sys.exit(101)
    return op

    
def parse_url(url):
    # build a query based on values from a URL string
    decoded_url = urllib.parse.unquote(url)
    parsed_url = urlparse(decoded_url)
    query_params = parse_qs(parsed_url.query)
    field_types = query_schema()
    
    where_clause = None
    for key in query_params:
        # walk through each url key to see if we need to do any special changes to it.
        
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
                sys.exit(102)
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
            values = build_values(query_params[key])
            updated_key = get_updated_mapping(key)
            op = get_operator(field_types[updated_key])
            if op == "ARRAY_CONTAINS_LIKE":
                # need to use 'value' instead of 'values' for the ARRAY_CONTAINS_LIKE operator
                q_filter = (' {key} : {{ op:{operator}, value:{value} }}'.format(key=updated_key, operator=op, value=values))
            else:
                # all other operators are ok with the 'values' keyword
                q_filter = (' {key} : {{ op:{operator}, values:[ {value} ]}}'.format(key=updated_key, operator=op, value=values))

        if where_clause is None:
            # create the where clause
            where_clause = q_filter
        else:
            # add to the where clause
            where_clause += q_filter
    
    if args.export:
        # getting most of the same fields the UI grabs for an export
        full_query = '''
            query ListFindings ($limit: Long, $offset: Long) { ListFindings (where: { ''' + where_clause + ''' } )
            { totalCount pageCount items (limit:$limit offset:$offset ) {
                resourceName
                severityNumeric
                findingKeyName
                findingType
                firstSeen
                lastSeen
                createdBy
                account
                assignee
                createdAt
                lastTransitionedBy
                lastTransitionedAt
                lastModifiedAt
                status
                swimlanes
                resourceSwimlanes
                operationalizedSwimlanes
                srn
            } } }
        '''
    else:
        # only need the SRN of the findings for all actions except export
        full_query = '''
        query ListFindings ($limit: Long, $offset: Long) { ListFindings (where: { ''' + where_clause + ''' } )
             { totalCount pageCount items (limit:$limit offset:$offset) {srn} } }
        '''
    logger.debug("URL Query Filter = {}".format(full_query))
    return full_query


def add_comment_to_findings(data, comment):
    # find the current user's srn (aka the user of the token)
    logger.info("Adding Comments to findings")
    sonrai_current_users = '{SonraiCurrentUsers {items {srn}}}'
    user_response = api.execute_query(sonrai_current_users)
    user_srn = user_response['data']['SonraiCurrentUsers']['items'][0]['srn']
    logger.debug("Comment User SRN = {}".format(user_srn))
    bulk_comment_mutation = '''mutation CreateFindingComment($requests: [CommentInput]) {
  CreateFindingComments(input: {comments: $requests}) { successCount } }'''
    counter = 0
    total_count = 0
    finding_var = {"requests": []}

    # find the last finding's srn, so we know when we are done the loop, and we can execute the mutation one last time
    last_finding_srn = data['data']['ListFindings']['items'][-1]['srn']
    global_count = data['data']['ListFindings']['totalCount']
    for finding in data['data']['ListFindings']['items']:
        # walk through all findings
        if counter == 0:
            # re-init the variable after each [findings_per_cycle] findings
            logger.debug("Preparing {} findings to add comment".format(findings_per_cycle))
            finding_var = {"requests": []}
        new_item = {"findingSrn": finding['srn'], "createdBy": user_srn, "body": comment}
        finding_var['requests'].append(new_item)
        counter += 1
        total_count += 1
        if counter == findings_per_cycle or last_finding_srn == finding['srn']:
            # we have [findings_per_cycle] findings or have reached the last findings, time to reset the counter and then add comments to the ones already processed
            results = api.execute_query(bulk_comment_mutation, finding_var)
            logger.debug("Added comments to findings {} / {}".format(total_count, global_count))
            counter = 0

    logger.info("Comments were added to {} total findings".format(total_count))
    
    
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


def assign_findings(user_email, data):
    # this will assign findings based on the query provided to 'user_email'
    # translate user_email into user_srn
    user_srn = get_user_srn(user_email)
    
    assign_findings_mutation = '''
    mutation AssignFindingBulk($requests: [AssignFindingRequestInput]) {
  AssignFindingBulk(input: {requests: $requests}) {
    results {
      findingSrn
      success
      error
    }
  }
}
'''
    counter = 0
    total_count = 0
    finding_var = {"requests": []}
    
    # find the last findings's srn so we know when we are done the loop and we can execute the mutation one last time
    last_finding_srn = data['data']['ListFindings']['items'][-1]['srn']

    for finding in data['data']['ListFindings']['items']:
        # walk through all findings
        if counter == 0:
            # re-init the variable after each [findings_per_cycle] findings
            finding_var = {"requests": []}
        new_item = {"findingSrn": finding['srn'], "userSrn": user_srn}
        finding_var['requests'].append(new_item)
        counter += 1
        total_count += 1
        if counter == findings_per_cycle or last_finding_srn == finding['srn']:
            # we have [findings_per_cycle] findings or have reached the last finding, time to reset the counter and then add comments to the ones already processed
            counter = 0
            results = api.execute_query(assign_findings_mutation, finding_var)
            logger.debug("results of assigning findings {}".format(results))
    logger.info("Assigned {} findings to {} ({})".format(total_count, user_email, user_srn))
    

def calculate_snooze_until(snooze_days):
    snooze_date = date.today() + timedelta(days=snooze_days)
    logger.debug("Snooze Until date set to {}".format(snooze_date))
    return snooze_date


def update_finding_status(action, data, snooze_days=None):
    # this will change status of findings
    # possible actions and the new Status
    # ReopenFindings = 'NEW'
    # CloseFindings = 'CLOSED'
    # SnoozeFindings = 'SNOOZED'
    # AcceptRiskFindings = 'RISK_ACCEPTED'
    
    # this mutation works for NEW, CLOSED, RISK_ACCEPTED but not snooze will have to adjust below for snoozing
    finding_status_mutation = """mutation update_finding_status($srns: [String]) {
    [action] (input: {srns: $srns}) {
    successCount
    failureCount
  }
}"""
    
    snooze_date = None
    snooze_json = {}
    # calculate the `snoozeUntil` date for SnoozeFindings
    if action == 'SnoozeFindings':
        snooze_date = calculate_snooze_until(snooze_days)
        snooze_json = {'snoozedUntil': str(snooze_date)}
        finding_status_mutation = """mutation update_finding_status($srns: [String], $snoozedUntil: DateTime) {
        [action] (input: {srns: $srns}, snoozedUntil: $snoozedUntil) {
        successCount
        failureCount
      }
    }"""

    finding_status_mutation = finding_status_mutation.replace("[action]", action)
    counter = 0
    total_count = 0
    finding_var = {"srns": []}
    if snooze_date is not None:
        # for snoozed findings we need to add the snoozeUntil value to the json
        finding_var.update(snooze_json)
    
    # find the last finding's srn so we know when we are done the loop and we can execute the mutation one last time
    last_finding_srn = data['data']['ListFindings']['items'][-1]['srn']
    
    for finding in data['data']['ListFindings']['items']:
        # walk through all findings
        if counter == 0:
            # re-init the variable after each [findings_per_cycle] findings
            
            finding_var = {"srns": []}
            if snooze_date is not None:
                # for snoozed findings we need to add the snoozeUntil value to the json
                finding_var.update(snooze_json)
    
        finding_var['srns'].append(finding['srn'])
        counter += 1
        total_count += 1
        if counter == findings_per_cycle or last_finding_srn == finding['srn']:
            # we have [findings_per_cycle] findings or have reached the last finding, time to reset the counter and then add comments to the ones already processed
            counter = 0
            results = api.execute_query(finding_status_mutation, finding_var)
            logger.debug(results)
            
    logger.info("Performed action {} on {} findings".format(action, total_count))
    

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
    logger.info("Exporting result to CSV file: {}".format(args.export))
    json_object = json.dumps(data['data']['ListFindings']['items'])
    df = pd.read_json(json_object)
    df.to_csv(args.export, encoding='utf-8', index=False)
    
    
def convert_swimlane_srns_to_names(data):
    # do a lookup of all swimlanes
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
    

# Create the parser
parser = argparse.ArgumentParser(description='')
query_method = parser.add_mutually_exclusive_group(required=True)

# Add the command line options
query_method.add_argument('-f', '--file', type=str, help='File containing graphQL query for findings')
query_method.add_argument('-u', '--url', type=str, help='UI URL to ticket screen with the query to run. Must be a quoted string')
parser.add_argument('-l', '--limit', type=int, default=1000, help='The limit of findings to be pulled with each pass. DEFAULT = 1000')
parser.add_argument('-m', '--message', type=str, help='Message or comment to add to finding(s). Must be a quoted string. A comment is required for all actions except --export')
parser.add_argument('-a', '--assign', metavar='EMAIL', help='Assign finding(s) to user with <EMAIL>')
parser.add_argument('-c', '--close', action='store_true', default=None, help='Close finding(s) from search')
parser.add_argument('-o', '--open', action='store_true', default=None, help='Re-Open finding(s) from the search')
parser.add_argument('-r', '--risk_accept', action='store_true', default=None, help='Risk Accept finding(s) from search')
parser.add_argument('-s', '--snooze', type=int, metavar="TIME", help='Snooze finding(s) from search for <TIME> days')
parser.add_argument('-e', '--export', type=str, metavar="FILE", help='Export finding(s) to <FILE>. Default format is JSON')
parser.add_argument('--swimlane_lookup', action='store_true', default=False, help='Convert all Swimlane SRNs to Swimlane names')
parser.add_argument('--csv', action="store_true", help='Used with -e option to export findings in csv format')
# parser.add_argument('--csv', action="store_true", help='Override default JSON file format to be CSV format')

# Parse the command line options
args = parser.parse_args()

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

finding_query = build_graphql(args.url, args.file)

# gather the list of findings based on the filter
response = query_findings(finding_query)

# check to see if there are no findings found and exit if that is the case.
if response['data']['ListFindings']['pageCount'] == 0:
    logger.info("No findings found with query, no action will be performed")
    sys.exit(0)
    
if args.swimlane_lookup:
    # we need to convert the swimlane SRNs to Names
    response = convert_swimlane_srns_to_names(response)
    
# we have findings so perform the necessary action
if args.assign:
    # assign findings from query
    assign_findings(args.assign, response)
elif args.close:
    # close findings from query
    add_comment_to_findings(response, args.message)
    update_finding_status("CloseFindings", response)
elif args.open:
    # open findings from query
    add_comment_to_findings(response, args.message)
    update_finding_status("ReopenFindings", response)
elif args.risk_accept:
    # risk accept findings from query
    add_comment_to_findings(response, args.message)
    update_finding_status("AcceptRiskFindings", response)
elif args.snooze:
    # snooze findings from query
    add_comment_to_findings(response, args.message)
    update_finding_status("SnoozeFindings", response, args.snooze)
elif args.export:
    # save results from finding query
    export_to_file(response, finding_query)
elif args.message:
    # add comment/message to findings from query
    add_comment_to_findings(response, args.message)
else:
    # something went wrong
    print("error: No valid operation provided")
    parser.print_help()
    sys.exit(108)
