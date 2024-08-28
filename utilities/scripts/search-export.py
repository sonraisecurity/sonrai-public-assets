import argparse
import json
import sys
import time
from sonrai_api import api, logger


def read_graphql_from_file(q_file):
    # build the search for the graphQL file provided
    logger.debug("Reading Query from {}".format(q_file))
    try:
        with open(q_file, 'r') as file:
            query_from_file = file.read().strip()
            file.close()
    except Exception as e:
        logger.error("An error occurred while reading the file: {}".format(e))
        sys.exit(100)
    logger.debug("Querying using the following query: \n {}".format(query_from_file))
    return query_from_file


def run_query(query_to_run):
    logger.info("Running Query")
    # This is used to loop the results [results_per_cycle] at a time until they are all captured
    offset = 0
    limit = results_per_cycle
    my_retries = 0
    total_count = None
    running_count = 0
    results = {}
    top_key = None
    while total_count is None or running_count < total_count:
        # looping through up to [results_per_cycle] at a time
        query_vars = json.dumps({"limit": limit, "offset": offset})
        logger.debug("querying {} results, offset: {}".format(limit, offset))
        success = False
        
        while not success:
            try:
                data = api.execute_query(query_to_run, query_vars)
                if 'errors' in data:
                    # check to see if there are any errors in the results, if so stop processing
                    logger.error("Invalid query {}".format(data))
                    logger.error("Validate query before proceeding")
                    sys.exit(104)
                
                if results == {}:
                    # this is the first query, so no value in results, just copying the data value into results
                    results = data.copy()
                    top_key = list(data['data'].keys())[0]
                    current_count = len(data['data'][top_key]['items'])
                    total_count = data['data'][top_key]['count']
                else:
                    # this is all subsequent passes, where we are extending the results with the data
                    results['data'][top_key]['items'].extend(data['data'][top_key]['items'])
                    current_count = len(data['data'][top_key]['items'])
                
                running_count += current_count
                logger.debug("adding {} {} records to the results ( {} / {} )".format(current_count, top_key, running_count, total_count))
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
        if running_count < total_count:
            offset += limit
    
    logger.info("Total number of results from query: {}".format(running_count))
    return results


def export_to_file(data):
    # export data
    # export to JSON (default)
    logger.info("Exporting result to JSON file: {}".format(args.file))
    json_object = json.dumps(data, indent=4)
    with open(args.file, "w") as outfile:
        outfile.write(json_object)
            
            
# main
# Create the parser
parser = argparse.ArgumentParser(description='This script will take an advance search and export to a file')
# Add the command line options
parser.add_argument('-q', '--query', type=str, required=True, help='File containing graphQL query advanced search')
parser.add_argument('-l', '--limit', type=int, default=1000, help='The limit of results to be pulled with each pass. DEFAULT = 1000')
parser.add_argument('-f', '--file', type=str, metavar="FILE", required=True, help='Export results to <FILE>. Default format is JSON')
# Parse the command line options
args = parser.parse_args()

# set the number of results to pull with each pass
results_per_cycle = args.limit

# load query from file
query = read_graphql_from_file(args.query)

# gather the list of results based on the filter
response = run_query(query)

# save results from finding query
export_to_file(response)
