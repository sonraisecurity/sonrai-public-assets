#!/usr/local/bin/python3
import os
import sys
import argparse
import logging
import json
import sonrai

class IdentityType:
   def __init__(self):
      pass

   def get_type_gcp_group(self, gcp_group):
      variables = json.dumps( {"group_name": gcp_group  })
      query_gcp_group = '''
             query getGCPGroupSRN($group_name: String) {
               Groups(
                 where: {
                   srn: {op: CONTAINS value: $group_name caseSensitive: false }
                   type: { op: EQ, value: GCPGoogleGroup } 
                }
                ) {
                count
                items {
                  srn
                  resourceId
                }
              }
            }  
      '''
      QUERY_NAME = "GCP GROUP QUERY"
      return variables, query_gcp_group, QUERY_NAME

   def get_type_gcp_user(self, gcp_user):
      variables = json.dumps( {"user_name": gcp_user  })
      query_gcp_user = '''
         query getGCPUserSRN ($user_name: String) {
           Users(
             where: {
               active: { op: EQ, value: true }
               type: { op: EQ, value: GCPUser } 
               userName: {op:EQ, value: $user_name}
             }
           ) 
           {
             count
             items {
               srn
               resourceId
             }
           }
         }
      '''
      QUERY_NAME = "GCP USER QUERY"
      return variables, query_gcp_user, QUERY_NAME

   def get_type_azure_ad_user(self, filter):
      tenant_id, ad_user = filter.split(":")
      variables = json.dumps( {"ad_user_name": ad_user, "tenant": tenant_id  })
      query_azure_ad_user = '''
      query getADUsersrn ($ad_user_name: String, $tenant: String) {
         Users(
           where: {
             active: { op: EQ, value: true }
             type: { op: EQ, value: ActiveDirectoryUser }
             userName: {op:EQ, value:$ad_user_name}
             account: {op:EQ, value:$tenant}
           }
         ) {
           count
           items {
             srn
             resourceId
           }
         }
       }
      '''
      QUERY_NAME = "AZURE AD USER QUERY"
      return variables, query_azure_ad_user, QUERY_NAME

   def get_type_azure_sp(self, filter_string):
      tenant_id, azure_app_id = filter_string.split(":")
      variables = json.dumps( {"app_id": azure_app_id, "tenant_id": tenant_id})
      query_azure_sp = '''
      query getAzureSP ($tenant_id: String, $app_id: String ) 
         {
           Users(
             where: {
               active: { op: EQ, value: true }
               type: { op: EQ, value: ServicePrincipal }
               account: {op:EQ, value:$tenant_id}
               metadata: {op:CONTAINS, value:$app_id}
             }	
           ) {
             count
             items {
		       resourceId
               srn
             }
           }
         }
      '''
      QUERY_NAME = "AZURE SERVICE PRINCIPAL"
      return variables, query_azure_sp, QUERY_NAME


   def get_type_azure_group(self, groupName):
      variables = json.dumps({"groupName": groupName})

      query_azure_group = '''
            query getAzureGroup($groupName: String) {
              Groups (
                where: {
                  name: {op: EQ value: $groupName  caseSensitive: false }
                  type: { op: EQ, value: ActiveDirectoryGroup } 
               }
               ) {
               count
               items {
                 srn
                 resourceId
               }
             }
           }  
      '''
      QUERY_NAME = "AZURE GROUP QUERY"
      return variables, query_azure_group, QUERY_NAME


   def get_type_aws_user(self, arn):
      variables = json.dumps({"arn": arn })
      query_aws_user = '''
         query getAWSUserSrn($arn: String) {
            Users(
              where: {
                active: { op: EQ, value: true }
                type: { op: EQ, value: User }
                resourceId: { op: EQ, value: $arn }
              }
            ) {
              count
              items {
                srn
                resourceId
              }
            }
          }
      '''
      QUERY_NAME = "AWS USER QUERY"
      return variables, query_aws_user, QUERY_NAME

   def get_type_aws_role(self, arn):
      variables = json.dumps({"arn": arn})

      query_aws_role = '''
            query getRoleSRN($arn: String) {
              Roles(
                where: {
                  resourceId: {op: EQ value: $arn caseSensitive: false }
                  type: { op: EQ, value: Role } 
               }
               ) {
               count
               items {
                 srn
                 resourceId
               }
             }
           }  
      '''
      QUERY_NAME = "AWS ROLE QUERY"
      return variables, query_aws_role, QUERY_NAME

   def get_identity_type(self, type, filter_value):
      get_type = f"get_type_{type}"
      if hasattr(self, get_type) and callable( getattr(self, get_type)):
         func = getattr(self, get_type)
         variables, query_identity_type, QUERY_NAME = func(filter_value)

         POST_FIELDS = {"query": query_identity_type, "variables": variables}
         POST_FIELDS = json.dumps(POST_FIELDS)

         logging.info("Querying identity type {} for name {}".format(type, filter_value) )
         return QUERY_NAME, POST_FIELDS

class mapping():

   def __init__(self):
      global URL

      self.nocheckcertificate = False
      self.logger=logging.getLogger("gcp-groups-aws-roles-mapping.py")
      #self.loglevel=os.environ.get("LOGLEVEL", "ERROR")
      self.loglevel=os.environ.get("LOGLEVEL", "INFO")
      logging.basicConfig(level=self.loglevel,
                          format="%(asctime)s:%(name)s:%(funcName)s:%(levelname)s: %(message)s"
                          )
      parser = argparse.ArgumentParser()
      parser.add_argument('-f', help='F = name of the file containing the mappings', required=False, default=False )
      parser.add_argument('--reset', help='--reset = clear all existing name sonrai-identity-mappings before setting new ones', required=False, action='store_true')
      args = parser.parse_args()
      self.filename = args.f
      self.resetMappings = args.reset

   def tag_clean_up (self, tag_key):
      # find the existing tags
      query_find_tags = ('query findTags{Tags (where: {key: {value:"' + tag_key + '"}})' +
          '{ count items { '+
           ' srn ' +
           ' tagsEntity {items {srn}} '+
         '}}}')
      QUERY_NAME = "Find Tags QUERY"
      POST_FIELDS = {"query": query_find_tags}
      POST_FIELDS = json.dumps(POST_FIELDS)
      all_tags = self.sonrai.SonraiGraphQLQuery(self.ApiURL, POST_FIELDS, QUERY_NAME, self.apitoken)

      # if there are existing tags, then we need to detach them from the resources and then delete them
      if all_tags['data']['Tags']['count'] > 0:
         logging.info ("preparing to delete old tags")

         logging.info("Deleting {} tags ".format(all_tags['data']['Tags']['count']))
         cnt = 1

         for tag in all_tags['data']['Tags']['items']:
            # delete_tag_string += ' DeleteTag( srn: "' + tag['srn'] + '" )'
            mutation_delete_tags = 'mutation deleteTags { DeleteTag ( srn: "' + tag['srn'] + '" ) } '
            # delete_tag_string += ' DeleteTag( srn: "' + tag['srn'] + '" )'
            QUERY_NAME = "DeleteTag"
            POST_FIELDS = {"query": mutation_delete_tags}
            POST_FIELDS = json.dumps(POST_FIELDS)
            tags = self.sonrai.SonraiGraphQLQuery(self.ApiURL, POST_FIELDS, QUERY_NAME, self.apitoken)
            if cnt % 50:
               print('.', end='', flush=True)
            else:
               print(str(cnt), end='', flush=True)

            cnt +=1
         print(" done")


   def addTag(self, resourcesrn, tag_key, tag_value):
      variables = json.dumps( {"srn": resourcesrn, "key":tag_key, "value": tag_value  })

      add_tag_mutation = '''
         mutation addKey($srn: ID, $key: String, $value: String) {
            AddTag( value: 
               { key: $key, 
                 value: $value, 
                 tagsEntity: {add: [$srn] }
                 }) 
               {srn key value}
            }
           '''
      QUERY_NAME = "ADD TAG TO RESOURCE"
      POST_FIELDS = {"query": add_tag_mutation, "variables": variables }
      POST_FIELDS = json.dumps(POST_FIELDS)

      self.addTagJSON =self.sonrai.SonraiGraphQLQuery(self.ApiURL,POST_FIELDS,QUERY_NAME,self.apitoken)
      return self.addTagJSON

   def getCount (self, identity):
      for identity_type in identity['data']:
         count = identity['data'][identity_type]['count']
         return count

   def getSRN (self, identity):
      for identity_type in identity['data']:
         srn = identity['data'][identity_type]['items'][0]['srn']
         return srn

   def getResourceId (self, identity):
      for identity_type in identity['data']:
         resourceId = identity['data'][identity_type]['items'][0]['resourceId']
         return resourceId

   def main(self,argv):
      # __init__(self=)
      source = IdentityType()
      target = IdentityType()

      tag_key = "sonrai-identity-mapping"
      # find api token, api server, setup client connection
      self.ENV_TOKEN = os.environ.get("TOKEN",None)
      self.sonrai = sonrai.SonraiApi()
      self.apitoken = self.sonrai.getToken()
      self.ApiURL = self.sonrai.getGraphQLUrl(self.apitoken)

      if self.nocheckcertificate is True:
         self.sonrai.verify(False)

      # reset if flagged
      if self.resetMappings is True:
         self.logger.info("clearing existing mappings")
         self.tag_clean_up(tag_key)

      # set new mappings if file included
      if self.filename != False:
         file_handle = open(self.filename, "r")

         for line in file_handle:
            # iterate over each line of the file
            error = False
            line = line.rstrip()
            if line.startswith("#"):
               #skip lines with comments
               continue
            if line.count(",") != 3:
               # skip ill formed lines
               self.logger.error("Invalid CSV line: {}".format(line))
               continue
            # pull out the gcp group and aws role mapping
            source_identity_type, source_identity, target_identity_type, target_identity = line.split(',')
            # get the source details
            QUERY_NAME, POST_FIELDS = source.get_identity_type(source_identity_type, source_identity)

            source_blob = self.sonrai.SonraiGraphQLQuery(self.ApiURL, POST_FIELDS, QUERY_NAME, self.apitoken)
            json.dumps(source_blob)
            source_count = self.getCount(source_blob)

            # error handing around the source identity
            if source_count == 0:
               self.logger.error('{} not found: {}'.format(source_identity_type, source_identity) )
               error = True
            elif source_count > 1:
               self.logger.error('Too many {} matches for: {}'.format(source_identity_type, source_identity))
               error = True

            # get the target details
            QUERY_NAME, POST_FIELDS = target.get_identity_type(target_identity_type, target_identity)

            target_blob = self.sonrai.SonraiGraphQLQuery(self.ApiURL, POST_FIELDS, QUERY_NAME, self.apitoken)
            target_count = self.getCount(target_blob)

            # error handing around the target identity
            if target_count == 0:
               self.logger.error('{} not found: {}'.format(target_identity_type, target_identity) )
               error = True
            elif target_count > 1:
               self.logger.error('Too many {} matches for: {}'.format(target_identity_type, target_identity))
               error = True

            # add the Tag to both resources
            if not error:
               source_srn = self.getSRN(source_blob)
               target_srn = self.getSRN(target_blob)

               # build the tag value based on the target's resourceId
               target_resourceId = self.getResourceId(target_blob)
               tag_value = target_resourceId

               self.logger.info("Adding key " + tag_key + " = " + tag_value + " to group and role")
               self.addTag(source_srn, tag_key, tag_value)
               self.addTag(target_srn, tag_key, tag_value)

         # end if filename

HANDLER=None

# def handle(event, context):
def handle(myargv):
   global HANDLER
   if not HANDLER:
      HANDLER = mapping()
   HANDLER.main(myargv)

if __name__ == "__main__":
   handle(sys.argv[1:])


