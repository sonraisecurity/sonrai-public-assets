#!/usr/bin/env python3

import csv
import argparse
import json
import logging
from sonrai_api import api, logger
from collections import defaultdict

CLOUD_HIERARCHY_QUERY = """
query getCloudHierarchyList($filters: CloudHierarchyFilter) {
  CloudHierarchyList(where: $filters) {
    items (orderBy: {scope:{order:ASC}}) {
      scope
      scopeFriendlyName
      entryType
      resourceId
      cloudType
      owners {
        email
      }
    }
  }
}
"""

GET_ROOT_SCOPE_QUERY = """
query getRootScope($filters: CloudHierarchyFilter) {
  CloudHierarchyList(where: $filters) {
    items {
      scope
      rootScope
      resourceId
      entryType
    }
  }
}
"""

LIST_SCOPE_OWNERS = """
query getScopeOwners($filters: ScopeOwnerFilter) {
  ScopeOwners(where: $filters) {
    items {
      email
    }
  }
}
"""

LIST_RESOURCE_SUMMARIES = """
query getUserName($filters: ResourceSummariesFilter) {
  ListResourceSummaries(where: $filters) {
    items {
      resourceId
      name
    }
  }
}
"""

CREATE_SCOPE_OWNER = """
mutation createScopeOwner($input: ScopeOwnerInput!) {
  CreateScopeOwner(input: $input) {
    owner {
      id
      name
      email
      sonraiUserId
    }
  }
}
"""

ASSIGN_SCOPE_OWNERS = """
mutation assignScopeOwners($input: AssignScopeOwnersInput) {
  AssignScopeOwners(input: $input) {
    success
    error
  }
}
"""

SONRAI_USERS_QUERY = """
query getSonraiUsers {
  SonraiUsers {
    items {
      email
    }
  }
}
"""

def get_root_scope(management_account_id):
    filters = {
        "entryType": {"op": "EQ", "value": "managementAccount"},
        "resourceId": {"op": "EQ", "value": management_account_id}
    }
    resp = api.execute_query(GET_ROOT_SCOPE_QUERY, variables=json.dumps({"filters": filters}))
    items = resp['data']['CloudHierarchyList']['items']
    if not items:
        logger.error(f"Invalid management account ID: {management_account_id}. No root scope found.")
        return None
    return items[0]['rootScope']

def export_hierarchy(cloud_type, output_file, management_account_id):
    logger.info(f"Exporting hierarchy for cloud type: {cloud_type} and management account ID: {management_account_id}")
    root_scope = get_root_scope(management_account_id)
    if not root_scope:
        logger.error("Export aborted: could not resolve root scope.")
        return
    filters = {
        "entryType": {"op": "NEQ", "value": "managementAccount"},
        "active": {"op": "EQ", "value": True},
        "cloudType": {"op": "EQ", "value": cloud_type},
        "scope": {"op": "STARTS_WITH", "value": root_scope}
    }
    resp = api.execute_query(CLOUD_HIERARCHY_QUERY, variables=json.dumps({"filters": filters}))

    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["scope", "scopeFriendlyName", "entryType", "resourceId", "owners"])
        for item in resp['data']['CloudHierarchyList']['items']:
            owners = ",".join([o['email'] for o in (item.get('owners') or []) if o.get('email')])
            writer.writerow([
                item['scope'], item['scopeFriendlyName'], item['entryType'],
                item['resourceId'], owners
            ])

def import_owners(input_file, dry_run=False):
    logger.info(f"Importing owners from {input_file} (dry run: {dry_run})")
    scope_owners_map = defaultdict(list)
    emails_needed = set()

    with open(input_file, newline='') as csvfile:
        # Read first line to check if it's a header
        first_line = csvfile.readline()
        csvfile.seek(0)
        
        # Check if first line looks like headers (contains 'scope' and 'owners')
        first_line_values = first_line.strip().split(',')
        has_headers = 'scope' in first_line_values and 'owners' in first_line_values
        
        if has_headers:
            reader = csv.DictReader(csvfile)
        else:
            # No headers, treat first line as data
            reader = csv.DictReader(csvfile, fieldnames=['scope', 'owners'])
        
        for row in reader:
            scope = row['scope'].strip()
            for email in row['owners'].split(','):
                email = email.strip()
                if email:
                    scope_owners_map[scope].append(email)
                    emails_needed.add(email)

    logger.info(f"Fetching existing Sonrai users")
    resp = api.execute_query(SONRAI_USERS_QUERY)
    existing_users = set(item['email'] for item in resp['data']['SonraiUsers']['items'])

    emails_to_create = emails_needed - existing_users
    logger.info(f"Need to create {len(emails_to_create)} users")

    # Find names for emails to create using LIST_RESOURCE_SUMMARIES
    email_name_map = {}
    email_list = list(emails_to_create)
    for i in range(0, len(email_list), 20):
        batch = email_list[i:i+20]
        arn_patterns = [f"%/{email}" for email in batch]
        variables = {"filters": {"resourceId": {"op": "LIKE", "values": arn_patterns}}}
        resp = api.execute_query(LIST_RESOURCE_SUMMARIES, variables=json.dumps(variables))
        for item in resp['data']['ListResourceSummaries']['items']:
            resource_id = item['resourceId']
            email_from_id = resource_id.split('/')[-1]
            if '@' in email_from_id:
                email_name_map[email_from_id] = item.get('name')
            else:
                logger.warning(f"Unexpected resourceId format: {resource_id}")

    for email in emails_to_create:
        name = email_name_map.get(email) or email.split('@')[0]
        if dry_run:
            logger.info(f"[DRY RUN] Would create user: {email} with name: {name}")
        else:
            logger.info(f"Creating user: {email} with name: {name}")
            api.execute_query(CREATE_SCOPE_OWNER, variables=json.dumps({"input": {"email": email, "name": name}}))

    for scope, owners in scope_owners_map.items():
        owner_objs = [{"email": email} for email in owners]
        if dry_run:
            logger.info(f"[DRY RUN] Would assign owners {owners} to scope {scope}")
        else:
            payload = {
                "input": {
                    "scope": scope,
                    "overrideChildScopes": False,
                    "owners": owner_objs
                }
            }
            result = api.execute_query(ASSIGN_SCOPE_OWNERS, variables=json.dumps(payload))
            if not result['data']['AssignScopeOwners']['success']:
              logger.error(f"Failed assigning owners to {scope}: {result['data']['AssignScopeOwners']['error']}")
            else:
              logger.info(f"Successfully assigned owners {owners} to {scope}")
                

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-e", "--export", action="store_true", help="Export cloud hierarchy to CSV")
    group.add_argument("-i", "--import", dest="import_owners_flag", action="store_true", help="Import owners from CSV")
    parser.add_argument("--file", required=True, help="Path to input or output CSV file")
    # temporarily commenting out until GCP is available
    # parser.add_argument("-c", "--cloud-type", required=False, help="Cloud type (aws, azure, gcp) for export")
    parser.add_argument("-m", "--management-account-id", required=False, help="Management account ID for export")
    parser.add_argument("--dry-run", action="store_true", help="Dry run import without making changes")
    args = parser.parse_args()
    
    # temporarily hard-coding cloud_type to aws
    args.cloud_type = "aws"

    if args.export:
        if not args.cloud_type or not args.management_account_id:
            parser.error("--cloud-type and --management-account-id are required for export mode")
        export_hierarchy(args.cloud_type, args.file, args.management_account_id)
    elif args.import_owners_flag:
        import_owners(args.file, dry_run=args.dry_run)