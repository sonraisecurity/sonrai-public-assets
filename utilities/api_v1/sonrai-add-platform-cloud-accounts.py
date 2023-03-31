#!/usr/local/bin/python3
import os
import sys
import getopt
import logging
import re
import json
import time
from sonrai import SonraiApi


# build the required arguments for the script
def current_milli_time():
    return str(round(time.time() * 1000))


class AddHandler:

    def __init__(self):

        # graphql required variables
        self.client = None
        self.savedQueryName = None
        self.queryFileName = None
        self.queryName = "AddAccountsScript"
        self.queryVariables = "{}"
        self.outputMode = "blob"
        self.nocheckcertificate = False
        self.array_of_items = None

        # logging variables
        self.logger = logging.getLogger("add-platform-cloud-accounts.py")
        self.loglevel = os.environ.get("LOGLEVEL", "INFO")
        logging.basicConfig(level=self.loglevel, format="%(asctime)s:%(name)s:%(funcName)s:%(levelname)s: %(message)s")

        # processing variables
        self.number_to_add_per_pass = 10  # default to adding only 10 at a time.
        self.file = None  #
        self.aws_arn = False
        self.role_name = None
        self.bot_role_name = None
        self.scan_role_name = None
        self.tenant_id = None
        self.collector_srn = None
        
        self.subscription_pattern = re.compile("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        self.account_num_pattern = re.compile("^[0-9]{12}$")
        self.account_arn_pattern = re.compile("^arn:aws:iam::[0-9]{12}:role/[^, ]*$")
        self.project_pattern = re.compile("^[a-zA-Z][-a-zA-Z0-9]{4,28}[a-zA-Z0-9]$")

        self.cloud_subtypes = {'aws': 'accounts', 'azure': 'subscriptions', 'gcp': 'projects'}
        self.key = {'aws': 'accountNumber', 'azure': 'subscriptionId', 'gcp': 'resourceId'}

        try:
            opts, args = getopt.getopt(sys.argv[1:], 'c:df:hn:t:', ["arn", "collector_srn=", "scan_role_name=", "bot_role_name=", "debug", "file=", "help", "role_name=", "cloud_type=", "tenant_id="])
        except getopt.GetoptError as err:
            print(err)
            self.print_usage()
            sys.exit()

        # get the command line options mapped
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                self.print_usage()
                sys.exit()
            elif opt in ("-c", "--collector_srn"):
                self.collector_srn = arg
            elif opt in ("-f", "--file"):
                self.file = arg
            elif opt in ("-d", "--debug"):
                self.logger.setLevel("DEBUG")
            elif opt in ("-t", "--type"):
                self.cloud_type = arg.lower()
                if self.cloud_type not in self.cloud_subtypes:
                    self.logger.error("Invalid cloud type")
                    self.print_usage()
                    sys.exit()
            elif opt in "--tenant_id":
                self.tenant_id = arg
            elif opt in "--arn":
                self.aws_arn = True
            elif opt in "--role_name":
                self.role_name = arg
            elif opt in "--bot_role_name":
                self.bot_role_name = arg
            elif opt in "--scan_role_name":
                self.scan_role_name = arg
            elif opt in "-n":
                try:
                    self.number_to_add_per_pass = int(arg)
                except:
                    # Not a valid number
                    self.logger.error("The -n option requires a number value")
                    self.print_usage()
                    sys.exit()
                if self.number_to_add_per_pass < 1 or self.number_to_add_per_pass > 100:
                    self.logger.error("Maximum to add at one time is 100")
                    self.print_usage()
                    sys.exit()

        # check to see if we have a file to process
        if self.collector_srn is None:
            self.logger.error("No Collector SRN specified")
            self.print_usage()
            sys.exit()

        if self.file is None:
            self.logger.error("No File specified")
            self.print_usage()
            sys.exit()

        if self.cloud_type == 'azure':
            # check to make certain there is a valid tenant ID
            if self.tenant_id is None:
                self.logger.error("Tenant Id must be specified with a cloud type of azure")
                self.print_usage()
                sys.exit()
            elif not self.subscription_pattern.match((self.tenant_id)):
                self.logger.error("Tenant Id is not a valid format")

        if self.cloud_type == 'aws':
            # check to make certain there is a valid role arn
            if self.role_name is None and self.aws_arn is False:
                self.logger.error("One of Role Name or ARN option must be specified with a cloud type of aws")
                self.print_usage()
                sys.exit()
            elif self.role_name is not None and self.aws_arn is True:
                self.logger.error("Only one of Role Name or ARN option must be specified with a cloud type of aws")
                self.print_usage()
                sys.exit()

    def validate_collector_srn(self):
        query_validate_srn = '''
       query platformAccounts ($srn: String) {
       PlatformAccounts  
       ( where:  { srn: {op:EQ value: $srn} }  ) {
          count
          items {
            name
            srn
        }
       }
       }'''
        variable = json.dumps({"srn": self.collector_srn})

        results_collector = self.client.executeQuery(query_validate_srn, variable)

        if results_collector['data']['PlatformAccounts']['count'] != 1:
            # invalid Collector, error and exit
            self.logger.error("{} doesn't exist in tenant".format(self.collector_srn))
            sys.exit()

    def load_file(self):
        file_obj = open(self.file, "r", encoding='utf-8-sig')
        self.array_of_items = file_obj.read().splitlines()
        # remove duplicates
        self.array_of_items = list(dict.fromkeys(self.array_of_items))
        file_obj.close()

    def mutation_builder(self, counter, cloud_account):
        mutation = None
        if self.cloud_type == 'gcp':
            # pattern match the cloud_account
            if self.project_pattern.match(cloud_account):
                # build the GCP mutation
                mutation = (' gcp' + str(counter) + ': CreatePlatformcloudaccount( ' +
                            ' value: { containedByAccount: { ' +
                            ' add: "' + self.collector_srn + '"  }' +
                            ' cloudType: "gcp" ' +
                            ' blob: { '
                            ' resourceType: "project" ' +
                            ' resourceId: "' + cloud_account + '" ' +
                            ' runDateTime: ' + current_milli_time() +
                            ' } } ) { srn } ')

        elif self.cloud_type == 'aws' and self.aws_arn is False:
            # AWS ARN builder part 1
            # build the AWS mutation based on the role names
            if self.account_num_pattern.match(cloud_account):
                role_arn = ("arn:aws:iam::" + str(cloud_account) + ":role/" + self.role_name)
                if self.bot_role_name is not None:
                    # if there is a botRole build the ARN
                    bot_role_arn = ("arn:aws:iam::" + str(cloud_account) + ":role/" + self.bot_role_name)
                else:
                    bot_role_arn = None
                if self.scan_role_name is not None:
                    # if there is a botRole build the ARN
                    scan_role_arn = ("arn:aws:iam::" + str(cloud_account) + ":role/" + self.scan_role_name)
                else:
                    scan_role_arn = None

                mutation = ('  aws' + str(counter) + ': CreatePlatformcloudaccount( ' +
                            'value: { ' +
                            'containedByAccount: { ' +
                            'add: "' + self.collector_srn + '" ' +
                            ' } '
                            'cloudType: "aws" ' +
                            'blob: { ' +
                            'accountNumber: "' + cloud_account + '" ' +
                            'roleArn: "' + role_arn + '" ')
                if bot_role_arn is not None:
                    # if there is a bot role, add to the mutation string
                    mutation += 'botRoleArn: "' + bot_role_arn + '" '

                if scan_role_arn is not None:
                    # if there is a bot role, add to the mutation string
                    mutation += 'scanRoleArn: "' + scan_role_arn + '" '

                    # close off mutation string
                mutation += ('runDateTime: ' + current_milli_time() +
                             '} } ) { srn }')
        elif self.cloud_type == 'aws' and self.aws_arn is True:
            # AWS ARN builder part 2
            # build the AWS mutation based on arns in the file
            try:
                if " " in cloud_account:
                    self.logger.error("Failed to parse line {}, string contains spaces, only use commas (,) as delimiters".format(self.cloud_subtypes[self.cloud_type], self.file))
                    return None
                (role_arn, bot_role_arn, scan_role_arn) = cloud_account.split(",")
            except ValueError:
                # not a properly formatted line
                self.logger.error("Failed to parse line {}, in correct number of fields specified".format(self.cloud_subtypes[self.cloud_type], self.file))
                return None
            if self.account_arn_pattern.match(role_arn):
                #valid arn format continue

                (field1, field2, field3, field4, account_num, field5) = role_arn.split(":")
                mutation = ('  aws' + str(counter) + ': CreatePlatformcloudaccount( ' +
                            'value: { ' +
                            'containedByAccount: { ' +
                            'add: "' + self.collector_srn + '" ' +
                            ' } '
                            'cloudType: "aws" ' +
                            'blob: { ' +
                            'accountNumber: "' + account_num + '" ' +
                            'roleArn: "' + role_arn + '" ')

                if self.account_arn_pattern.match(bot_role_arn):
                    # if there is a valid bot role, add to the mutation string
                    mutation += 'botRoleArn: "' + bot_role_arn + '" '
                elif bot_role_arn is not None:
                    # we allow blank roles
                    pass
                else:
                    # invalid bot role, time return nothing and skip entire role of CSV file
                    return None

                if self.account_arn_pattern.match(scan_role_arn):
                    # if there is a valid scan role, add to the mutation string
                    mutation += 'scanRoleArn: "' + scan_role_arn + '" '
                elif scan_role_arn is not None:
                    # we allow blank roles
                    pass
                else:
                    # invalid scan role, time return nothing and skip entire role of CSV file
                    return None
    
                    # close off mutation string
                mutation += ('runDateTime: ' + current_milli_time() +
                             '} } ) { srn }')

        elif self.cloud_type == 'azure':
            if self.subscription_pattern.match(cloud_account):
                #valid subscription format
                # build the azure mutation string
                mutation = ('  sub' + str(counter) + ': CreatePlatformcloudaccount( ' +
                            'value: { ' +
                            'containedByAccount: { ' +
                            'add: "' + self.collector_srn + '" ' +
                            ' } '
                            'cloudType: "azure" ' +
                            'blob: { ' +
                            'subscriptionId: "' + cloud_account + '" ' +
                            'tenantId: "' + self.tenant_id + '" ' +
                            'runDateTime: ' + current_milli_time() +
                            '} } ) { srn }')

        return mutation

    def add_to_collector(self):
        # process the self.items_to_add
        item_num_counter = 0
        while item_num_counter < len(self.array_of_items):
            # walk through the array_of_items
            inner_counter = 0
            # start mutation
            mutation = "mutation addToCollector {"
            platform_cloud_account_string = ""
            pca_to_be_added = []
            while inner_counter < self.number_to_add_per_pass and item_num_counter < len(self.array_of_items):
                # walk through the array_of_items, but only number_to_add_per_pass at a time
                # build the "CreatePlatformCloudAccount" block for each project
                temp_mutation = self.mutation_builder(inner_counter, self.array_of_items[item_num_counter])
                if temp_mutation is None:
                    self.logger.warning("warn: Invalid cloud account format {}. Skipping this record".format(self.array_of_items[item_num_counter]))
                    inner_counter += 1
                    item_num_counter += 1
                    continue
                    
                platform_cloud_account_string += temp_mutation
                pca_to_be_added.append(self.array_of_items[item_num_counter])
                # increase counters
                inner_counter += 1
                item_num_counter += 1

            mutation += platform_cloud_account_string + ' } '
            variables = {}
            if platform_cloud_account_string == "":
                # No new valid accounts/projects, etc to add, break out of loop
                break
            add_results = self.client.executeQuery(mutation, variables)
            if 'errors' in add_results:
                self.logger.warning("Error hit while trying to add the following {} {}".format(self.cloud_subtypes[self.cloud_type], pca_to_be_added))
                self.logger.warning("Will continue adding")
                # self.logger.error("Error adding {} between lines {} and {} of {}.".format(self.cloud_types[self.cloud_type],item_num_counter-self.number_to_add_per_pass+1, item_num_counter, self.file))
                # self.logger.error("Validate that those {} are not already added to collector".format(self.cloud_types[self.cloud_type]))
                # self.logger.error("To continue rerun from line {} to end of {}".format(item_num_counter+1, self.file))
                self.logger.debug("graphQL ERROR\n" + str(add_results))
                # will keep trying
                # sys.exit(0)
            elif 'data' in add_results:
                self.logger.info("Successfully added the following {} {}".format(self.cloud_subtypes[self.cloud_type], pca_to_be_added))

    def verify_platform_cloud_accounts(self):
        query_pca = ('''query platformAccounts
            ($srn: String) 
            {
              PlatformAccounts
               (where: { srn: { op: EQ, value: $srn } }) 
              {
                items {
                  name
                  srn
                  containsCloudAccount { count items (limit: 10000) {srn  blob}}
                }
              }
            }
            ''')
        variable = json.dumps({"srn": self.collector_srn})
    
        results_collector = self.client.executeQuery(query_pca, variable)
    
        failed_to_add = []
    
        for add_item in self.array_of_items:
            successfully_added = False
            for current_item in results_collector['data']['PlatformAccounts']['items'][0]['containsCloudAccount']['items']:
                if current_item['blob'][self.key[self.cloud_type]] == add_item:
                    # this check works for most of the file formats but not the ARN check
                    successfully_added = True
                    break
                elif current_item['blob'][self.key[self.cloud_type]] in add_item:
                    # this check is for ARN formatted files
                    successfully_added = True
                    break

            if not successfully_added:
                self.logger.debug("{} doesn't appear to have been added to collector".format(add_item))
                failed_to_add.append(add_item)
            else:
                self.logger.debug("{} successfully added".format(add_item))
    
        if len(failed_to_add) > 0:
            error_file_name = self.file + ".error"
            error_file = open(error_file_name, 'w')
            for item in failed_to_add:
                error_file.write(item+"\n")
            self.logger.error("Failed to add {}, check {}.error for ones that did not add properly".format(self.cloud_subtypes[self.cloud_type], self.file))
            error_file.close()

    def print_usage(self):
        print("")
        print(" Usage:  ")
        print("   ./sonrai-add-platform-cloud-accounts.py --collector_srn <srn> --file <filename> --type <cloud_type> [-n <#>] ")
        print("   ./sonrai-add-platform-cloud-account.py --help [-t <cloud_type>]")
        print("")
        print(" Options:")
        print("   -h, --help                             Show this message.")
        print("                                          if you include the cloud type with the help option you get more details on those options.")
        print("   -c <srn>, --collector_srn <srn>        The Collector's SRN to add all the cloud accounts/projects/subscriptions")
        print("   -f <filename>, --file <filename>               File with the cloud accounts/projects/subscriptions to add.")
        print("   -n <1-100>                             Number between 1 and 100 for the number of items to add in one batch. Defaults to 10.")
        print("   -t <cloud_type>, --type <cloud_type>   One of aws|azure|gcp for the type of accounts to add")
        print("")
        print("   Cloud specific Options:")
        print("")
        print("   AWS: (One of --arn or --role_name but be specified)")
        print("       --arn                               File contains role ARNs in this format: collector_role_arn,bot_role_arn,scan_role_arn")
        print("                        OR")
        print("       --role_name                         File contains account numbers only, this is the name of the role in all accounts")
        print("       --bot_role_name                     File contains account numbers only, this is the name of the bot role in all accounts")
        print("       --scan_role_name                    File contains account numbers only, this is the name of the scan role in all accounts")
        print("")
        print("   Azure:")
        print("       --tenant_id                         This is the tenant ID for all subscriptions in the file")
        print("")
        print("   GCP:")
        print("       No cloud specific options")
        print("")
        print("   -d, --debug                      Turn on debug mode for more detailed logging")
        print(" Environment variables:")
        print("   TOKEN                   Sonrai API auth token")
        print("")

    def main(self):
        # setup an API client
        self.client = SonraiApi(self.queryName, self.savedQueryName, self.queryFileName, self.queryVariables, self.outputMode)

        # check to make certain we've received a valid SRN for the PlatformAccount
        self.validate_collector_srn()

        # add all items from file into an array
        self.load_file()

        # Add items to the collector
        self.add_to_collector()

        # Verify platform cloud accounts have been added
        self.verify_platform_cloud_accounts()


# def handle(event, context):
HANDLER = None


def handle(myargv):
    global HANDLER
    if not HANDLER:
        HANDLER = AddHandler()
    HANDLER.main()


if __name__ == "__main__":
    handle(sys.argv[1:])
