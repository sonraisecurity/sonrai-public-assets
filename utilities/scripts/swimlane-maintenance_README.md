# swimlane-maintenance.py

## Introduction

The `swimlane-maintenance.py` script is used to create and update Sonrai swimlanes based on tags added to your cloud resources.

## Prerequisites

### Script requirements
- python version 3 and above
- hosting location - such as linux VM or similar environment
- **sonrai_api** - a folder created and hosted in same directory as this script, which contains the sonrai api python library available at https://github.com/sonraisecurity/sonrai-public-assets/tree/main/utilities/sonrai_api
- **sonrai api token** - token from a user with at least `Data Viewer / All Swimlanes` and `Swimlane Creator` permission.  Instructions for creating tokens available at https://docs.sonraisecurity.com/api/sonrai-graphql-api#user-api-keys
- **orgs tagging scheme** - the tagging convention used by your organization to identify individual applications and environments 


### Sonrai platform requirements
- **swimlane template** - a template consisting of a swimlane prefixed with **~SonraiSwimlaneTemplate_** and defined **Tag Filters** (accounts (AWS Accounts or GCP Projects) or resource IDs (Azure resource groups or subscriptions)) 

## Description

This script allows you to create [and update] your Sonrai swimlane configuration based on a tagging scheme in use by your organization. It takes an environment tag, and an application type tag to *create* the swimlanes, then uses the cloud data already collected by Sonrai, to *search for and populate* the swimlane filters for resources in your cloud [monitored by Sonrai] that have those tag combinations

## How it works

To begin, a swimlane template is required (ref: requirements for the Sonrai platform above). The script looks for one or more templated swimlanes to build out the actual swimlanes to be used for your environment within the Sonrai platform. 

1. Leveraging the tags on the swimlane template, the script will:
a) run a search to find all the unique application codes/ids within your cloud environment
b) create swimlanes for your Sonrai tenant that are named with a prefix, an application code or id, and the environment

2. After the swimlanes are created, the script will then run a search to populate the applicable Accounts or Resource ID filters

## Configuration

The following are the tags used to build out your swimlanes within the Sonrai platform:

### Tags/values within your cloud

| Tag key      | tag value(s)             | description                                                                                                                                                                       |
|--------------|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| app_tag_name | application code or id   | This is the unique tag key for your applications in your clouds <br/><br/> example:<br/> `app_tag_name=app_id:*`                                                                  |
| env_tag_name | << environment key >>    | This is the unique tag key used to identify the environments in your clouds (can be a comma separator list of tags keys)  <br/><br/> example: <br/>`env_tag_name=env,environment` |
| env_type     | << environment values >> | This is the environment on which the swimlanes will be based (comma separated list of environments) <br/><br/> example: <br/>`env_type=prod,production,Production`                |

### Tags/values within the Sonrai platform

| Tag key              | tag value(s)                                                                   | description                                                                                                                                                                         |
|----------------------|--------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| swimlane_prefix      | << prefix >>                                                                   | The prefix used for naming all the swimlanes that are created from this template <br/><br/> example: <br/>`swimlane_prefix:azure`                                                   |
| sonrai_env           | Sensitive Data  <br/> Production <br/> Staging <br/> Development <br/> Sandbox | The environment used by Sonrai when building your swimlane <br/><br/> example: <br/>`sonrai_env:Production`                                                                         |
| swimlane_filter_type | Accounts <br/> ResourceIds                                                     | The account/resource id on which the swimlane is to be built<br/><br/> example: <br/>`swimlane_filter_type:ResourceIds`                                                             |
| cloud_type           | aws, azure, or gcp                                                             | The cloud type where these resources reside <br/><br/> example: <br/>`cloud_type:azure`                                                                                             |
| default_importance   | 0-10                                                                           | The value used for the importance of the swimlane<br/><br/> example: <br/>`default_importance:9`                                                                                    |
| search_resource_type | << resources to search for >>                                                  | This is the same value as the top-level card in the search builder<br/><br/> example: <br/>`search_resource_type:ResourceGroups`                                                    |
| search_return_field  | << field in search >>                                                          | This is the field with the values to input for the swimlane configuration (the `account` field or the `resourceId` field) <br/><br/> example: <br/>`search_return_field:resourceId` |

#### Sample configuration

##### AWS related Swimlane
![image (7)](https://github.com/sonraisecurity/sonrai-public-assets/assets/106173154/8b217311-c5b4-4500-a352-824d24500fb9)

##### Azure related Swimlane based on Resource Groups
![image (8)](https://github.com/sonraisecurity/sonrai-public-assets/assets/106173154/e1b2719a-bec0-4d72-8c13-90b3c4bb71bf)

## Usage

No special arguments required.

To run the script, open a shell and execute:

```
% python3 swimlane-maintenance.py 
```
