from sonrai_api import api
import json
import sys
import logging
import os

#########
# important variables
# set with environment variables or if not available use the default value
#########
create_test_mode = os.environ.get('CREATE_TEST_MODE', False)
update_test_mode = os.environ.get('UPDATE_TEST_MODE', False)
max_sl_add_per_run = os.environ.get('MAX_PER_RUN', 5)
max_sl_total = os.environ.get('MAX_TOTAL', 200)

##########
# setup logging
##########
logger = logging.getLogger("swimlane_maint")
# Create the Logger for use with all modules
# https://docs.python.org/3/library/logging.html#logrecord-objects
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] -- %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Constants from config
try:
    with open('sonrai_api/config.json') as json_file:
        config = json.load(json_file)
except json.decoder.JSONDecodeError:
    logging.error("Unable to parse the config.json file")
    exit(255)
except FileNotFoundError:
    logging.error("Unable to find the config.json file")
    exit(254)

# Set level according to the config file.
try:
    # if it is configured in the config.json
    level = logging.getLevelName(config['script-log-level'])
except:
    # else set it to INFO
    level = "INFO"
logger.setLevel(level)


def get_swimlanes(gql_filter):
    logger.debug("Swimlane filter: {}".format(gql_filter))
    # query for swimlane details based on filter that is passed in and just return the individual items, not the whole json blob
    swimlane_query = ('''
    query swimlanes {{ Swimlanes (where: {filter} ) {{
        count items (limit:1000) {{ srn title tags resourceIds accounts }} }} }}
    '''.format(filter=gql_filter))
    swimlane_results = api.execute_query(swimlane_query)
    return swimlane_results


def query_resource_type(gql_filter, sl_template):
    # query resources based on filter
    resource_query = ('''
        query resources {{ {resource_type} (where: {filter}) {{
            count items {{ srn {return_field} app_tag_name: tagSet @regex(match:"{app_tag_name}(.*)", replace:"$1") }} }} }}
    '''.format(filter=gql_filter, resource_type=sl_template['search_resource_type'], return_field=sl_template['search_return_field'], app_tag_name=sl_template['app_tag_name'].replace('*', '')))
    logger.debug("Query for resource tags:\n{}".format(resource_query))
    resource_results = api.execute_query(resource_query)
    logger.debug("Results from resource tags query:\n{}".format(resource_results))
    return resource_results


def get_tagSet_values(sl_template):
    # build the filter based on the templates tags
    env_filter = []
    for env_tag in sl_template['env_tag_name'].split(','):
        for env_type in sl_template['env_type'].split(','):
            logger.debug("Environments from templates: {}:{}".format(env_tag, env_type))
            env_filter.append(env_tag + ":" + env_type)
    
    query_filter = ('''
    {{
    active: {{ value:true }}
    cloudType: {{ op:EQ value: "{cloud_type}" }}
    and: [
        {{ tagSet: {{op:IN_LIST values: {env} }} }}
        {{ tagSet: {{op:CONTAINS value: "{app}" caseSensitive:false }} }}
      ]
    }}'''.format(cloud_type=sl_template['cloud_type'], app=sl_template['app_tag_name'].replace('*', ''), env=env_filter))
    query_filter = query_filter.replace("'", '"')
    query_results = query_resource_type(query_filter, sl_template)
    app_tagset_list = []
    for app_tag_value in query_results['data'][sl_template['search_resource_type']]['items']:
        # get uniq app tag values
        if app_tag_value['app_tag_name'][0] not in app_tagset_list:
            app_tagset_list.append(app_tag_value['app_tag_name'][0])
    return app_tagset_list, env_filter


def create_swimlane(new_sl, app_value, title):
    # build out the different swimlane fields
    description = ('''Swimlane created from swimlane template {title} for all application with tags of {app_key}:{app_value} and environments of {env_value}'''.
                   format(title=new_sl['title'], app_key=new_sl['app_tag_name'].split(":", 1)[0], app_value=app_value, env_value=new_sl['sonrai_env']))
    
    # build out the mutation and variable
    mutation_create_swimlane = ('''mutation createSwimlane($swimlane: SwimlaneCreator!) { CreateSwimlane(value: $swimlane) {
        description label title srn defaultImportance createdBy sid preventionEnabled lastModified createdDate name accounts names resourceIds tags resourceId } }''')
    variable_create_swimlane = ('''
    {{"swimlane":
        {{
         "title":"{t}",
         "description":"{desc}",
         "defaultImportance":{dI},
         "names":[],
         "resourceIds": [],
         "tags": [],
         "accounts": [],
         "preventionEnabled":false,
         "environments":["{sonrai_env}"]
        }}
    }}'''.format(t=title, desc=description, sonrai_env=new_sl['sonrai_env'], dI=new_sl['default_importance'])).replace("'", '"')
    
    logger.debug("Create Swimlane mutation: {}".format(mutation_create_swimlane))
    logger.debug("Create Swimlane Variable: {}".format(variable_create_swimlane))
    
    # run the mutation to create the swimlane
    create_swimlane_response = api.execute_query(mutation_create_swimlane, variable_create_swimlane)
    return create_swimlane_response


def resource_query_builder(sl_template, app, env_filter):
    # build the fields needed to update the swimlane
    cloud_type = sl_template['cloud_type']
    app_key_value_pair = sl_template['app_tag_name'].split(":", 1)[0] + ":" + app
    search_type = sl_template['swimlane_filter_type'][0]
    search_key = sl_template['search_resource_type']
    return_value = sl_template['search_return_field']
    
    # build the filters for the query
    query_filter = ('''
    {{
    active: {{ value:true }}
    cloudType: {{ op:EQ value: "{cloud_type}" }}
    and: [
        {{ tagSet: {{op:IN_LIST values: {env} }} }}
        {{ tagSet: {{op:EQ value: "{app}" caseSensitive:false }} }}
      ]
    }}'''.format(cloud_type=cloud_type, app=app_key_value_pair, env=env_filter))
    query_filter = query_filter.replace("'", '"')
    logger.debug("Resource Query Filter: {}".format(query_filter))
    
    # build the query
    query_resources = ('''
        query resource {{ {search_key} (where: {filter} ) {{ items {{ {return_value} }} }} }}
    '''.format(search_key=search_key, filter=query_filter, return_value=return_value))
    logger.debug("Resource Query: {}".format(query_resources))

    return search_type, search_key, return_value, query_resources


def update_swimlane(srn, sl_template, app, env_filter):
    #  update swimlanes from the details of the previous section
    logger.info('Querying Swimlane {} for tags'.format(srn))
    
    # Swimlane update search
    sus_results = api.execute_query('''
    query swimlane {{
      Swimlanes ( where: {{
        description: {{ op: CONTAINS value:"SonraiSwimlaneTemplate" }}
        srn: {{ op: EQ value: "{srn}" }}
    }} )
      {{
        count
        items(limit: -1) {{
          title
          srn
          tags
          accounts
          resourceIds
        }}
      }}
    }}
    '''.format(srn=srn))
    
    try:
        # check to see if we get a swimlane back
        item = sus_results['data']['Swimlanes']['items'][0]
    except IndexError:
        # do not have a valid swimlane built by script. Will not update this swimlane
        logger.warning("Swimlane {} does not have 'SonraiSwimlaneTemplate' in description field, it will NOT be updated".format(srn))
        return
        
    
    # Iterate through each swimlane
    # for item in sus_results['data']['Swimlanes']['items']:
    # Dictionary for update
    # Keys: R = Resource IDs, A = Accounts, N = Names, T = Tags
    updates = {"R": [], "A": [], "N": [], "T": []}
        
    # Dictionary for swimlane
    # Keys: R = Resource IDs, A = Accounts, N = Names, T = Tags
    swimlane = {"R": [], "A": [], "N": [], "T": []}
        
    # Dictionary for resources(R), accounts(A), etc. to be added
    add = {"R": [], "A": [], "N": [], "T": []}
        
    # Dictionary for resources(R), accounts(A), etc. to be removed
    remove = {"R": [], "A": [], "N": [], "T": []}
        
    # store the swimlane accounts
    if item.get('accounts'):
        # Create a list to store these
        accountList = list()
        for account in item['accounts']:
            accountList.append(account)
            
        # add the temp list into the swimlane dict
        if accountList:
            swimlane['A'] = accountList
        
    # store the swimlane resources
    if item.get('resourceIds'):
        # Create a list to store these
        resourceList = list()
        for resource in item['resourceIds']:
            resourceList.append(resource)
        
        # add the temp list into the swimlane dict
        if resourceList:
            swimlane['R'] = resourceList
    
    # build the query used to update the swimlane
    search_type, search_group, return_value, query = resource_query_builder(sl_template, app, env_filter)
    
    # Execute the search
    logger.info("Running search for {resource} to update swimlane {swimlane}".format(resource=search_group, swimlane=item['title']))
    search_results = api.execute_query(query)
    try:
        for row in search_results['data'][search_group]['items']:
            tempR = list(updates[search_type])
            if search_type == 'R':
                tempR.append('*' + row[return_value] + '*')
            else:
                tempR.append(row[return_value])
            
            # Remove duplicates: list->set->list
            updates[search_type] = list(set(tempR))
    
    except KeyError:
        logger.error("Invalid Search or Search_Group in tag: {search_keys}:{search}".format(search_keys=data[0], search=data[1]))

    # create the REMOVE and ADD arrays and update the swimlane
    for key in updates:
        if updates[key]:
            add[key] = list(set(updates[key]) - set(swimlane[key]))
            remove[key] = list(set(swimlane[key]) - set(updates[key]))
    
    for key in swimlane:
        if swimlane[key]:
            add[key] = list(set(updates[key]) - set(swimlane[key]))
            remove[key] = list(set(swimlane[key]) - set(updates[key]))
        
    # Build the mutations
    # Resources
    add_resourceIds = str(add['R']).replace("'", '"')
    remove_resourceIds = str(remove['R']).replace("'", '"')
    resource = '{{ resourceIds: {{ add: {add}, remove: {remove} }}'.format(add=add_resourceIds, remove=remove_resourceIds)
        
    # Accounts
    add_accounts = str(add['A']).replace("'", '"')
    remove_accounts = str(remove['A']).replace("'", '"')
    accounts = ' accounts: {{ add: {add}, remove: {remove} }} }}'.format(add=add_accounts, remove=remove_accounts)
        
    swimlane_mutation = 'mutation updateSwimlane {{ UpdateSwimlane(srn: "{srn}", value: {resource} {accounts} ) {{ srn }}}}'.format(srn=item['srn'], resource=resource, accounts=accounts)
        
    if len(add_resourceIds) > 2 or len(remove_resourceIds) > 2 or len(add_accounts) > 2 or len(remove_accounts) > 2:
        logger.info("Preparing to Update Swimlane: " + item['title'])
        api.execute_query(swimlane_mutation)
        
        # build comment for ticket
        comment = "Swimlane Update: {}".format(item['title'])
        
        if len(add_resourceIds) > 2:
            comment += " Adding Resource Ids: {}".format(add_resourceIds)
        if len(remove_resourceIds) > 2:
            comment += " Removing Resource Ids: {}".format(remove_resourceIds)
        if len(add_accounts) > 2:
            comment += " Adding Accounts: {}".format(add_accounts)
        if len(remove_accounts) > 2:
            comment += " Removing Accounts: {}".format(remove_accounts)
        
        comment = comment.replace('"', "'")
        logger.info(comment)
    else:
        logger.info("Nothing to do for Swimlane: " + item['title'])


# main
# get count of all swimlanes:
swimlanes_all = get_swimlanes('{ }')
total_count = swimlanes_all['data']['Swimlanes']['count']
new_sl_added_count = 0
# get all the swimlane templates
logger.info("Searching for templated swimlanes")
swimlanes_templates = get_swimlanes('{{title: {{op:CONTAINS value:"{title}"}} }}'.format(title="~Sonrai"))
# loop through each template
for sl in swimlanes_templates['data']['Swimlanes']['items']:
    template_count = 0
    
    logger.info("Processing template {}".format(sl['title']))
    for tag in sl['tags']:
        # this section of code moves the tags into the upper leave sl dict as their own key
        # split on first '='
        (tag_key, tag_value) = tag.split("=")
        
        if "app_tag_name" in tag_key:
            # app_tag_name needs the trailing asterisk, not deleting it.
            sl[tag_key] = tag_value
        else:
            # all other tags do not need the leading or trailing asterisk, so deleting the '*'.
            tag_key = tag_key[1:]
            tag_value = tag_value[:-1]
            sl[tag_key] = tag_value
    
    # now that they have been moved, we can delete the 'tags' key from the sl dict
    del sl['tags']
    
    # see if we have a tag called max_per_template and set the maximum swimlanes for this particular template otherwise just set the max to the sl max
    if 'max_per_template' in sl:
        template_max = sl['max_per_template']
    else:
        template_max = max_sl_total
    
    # get values from template to prepare to make new swimlanes if necessary
    app_tag_list, envs = get_tagSet_values(sl)
    logger.info("Found {} unique application tags".format(len(app_tag_list)))
    
    # get the current swimlanes from the swimlane prefix
    logger.info("Gathering existing swimlanes that match template with prefix of {prefix} and environment of {env}".format(prefix=sl['swimlane_prefix'], env=sl['sonrai_env']))
    swimlanes_existing = get_swimlanes('{{ and: [ {{title: {{op:CONTAINS value:"{prefix}" }} }} {{ title: {{op:CONTAINS value:"{env}" }} }} ] }}'.format(prefix=sl['swimlane_prefix'], env=sl['sonrai_env']))
    logger.info("Found {} swimlanes with prefix {}".format(swimlanes_existing['data']['Swimlanes']['count'], sl['swimlane_prefix']))
    logger.debug("Existing templated swimlanes: {}".format(swimlanes_existing))
    
    # for each app type, create if new and/or update
    for app in app_tag_list:
        app = str(app).lower() # convert app name to lower case to make swimlanes case insensitive
        swimlane_name = "{prefix}_{app_name}_{env_name}".format(prefix=sl['swimlane_prefix'], app_name=app, env_name=sl['sonrai_env'])
        found = 0
        existing_swimlane_srn = None
        new_swimlane_srn = None
        for existing in swimlanes_existing['data']['Swimlanes']['items']:
            if swimlane_name == str(existing['title']).lower():
                found = 1
                existing_swimlane_srn = existing['srn']
                break
            else:
                continue
        
        if found:
            # Do nothing, it already exists
            logger.debug("Swimlane already exists: {}".format(swimlane_name))
        else:
            # Create Swimlane
            logger.info("New Swimlane to create: {}".format(swimlane_name))
            if create_test_mode is False:
                # We are cleared to create swimlane
                # check to see if we are at any limits
                if (total_count + new_sl_added_count) >= max_sl_total:
                    # too many swimlanes total stopping now:
                    logger.error("Maximum number of swimlanes reached")
                    exit(100)
                elif new_sl_added_count >= max_sl_add_per_run:
                    logger.warning("Maximum number of swimlanes added with this run of the script")
                    exit(99)
                elif template_count >= template_max:
                    logger.warning("Maximum number of swimlanes processed for this template proceeding with next template")
                    break
                else:
                    response_new_swimlane = create_swimlane(sl, app, swimlane_name)
                    new_swimlane_srn = response_new_swimlane['data']['CreateSwimlane']['srn']
                    template_count += 1
                    new_sl_added_count += 1
            else:
                # we are in test mode, do not create the swimlane
                logger.info("Test mode, not creating swimlane {}".format(swimlane_name))
                
        # update swimlanes if not in test mode
        if update_test_mode is False:
            # update swimlanes
            if new_swimlane_srn is not None:
                update_swimlane(new_swimlane_srn, sl, app, envs)
            elif existing_swimlane_srn is not None:
                update_swimlane(existing_swimlane_srn, sl, app, envs)
            else:
                logger.error("No swimlane SRN available, nothing to update")
