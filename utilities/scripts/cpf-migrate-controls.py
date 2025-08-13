#!/usr/bin/env python3
import argparse
import json
import sys
import os
from sonrai_api import api, logger

# Set up verbose logging
#logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_scope(account_id):
    """Returns the scope string for a given AWS account"""
    query = """
    query getCloudHierarchyList($filters: CloudHierarchyFilter) {
      CloudHierarchyList(where: $filters) {
        items {
          resourceId
          scope
        }
      }
    }
    """
    variables = json.dumps({
        'filters': {
            'purpleEnabled': {'op': 'EQ', 'value': True},
            'entryType': {'op': 'NEQ', 'value': 'managementAccount'},
            'active': {'op': 'EQ', 'value': True}
        }
    })

    response = api.execute_query(query, variables)
    for item in response['data']['CloudHierarchyList']['items']:
        if item['resourceId'] == account_id:
            return item['scope']

    logger.error("Scope not found for account {}".format(account_id))
    return None

def get_controls_by_status(scope):
    """Retrieves services by status (Disabled or Protected)"""
    query = """
    query getCloudServices($filters: CloudServiceFilter) {
      CloudServices(where: $filters) {
        items(orderBy: {sensitivePermissionCount: {order: DESC}}) {
          name
          status {
            status
          }
          controlKey
        }
      }
    }
    """
    variables = json.dumps({ 'filters': { 'scope': { 'value': scope, 'op': 'EQ' } } })

    response = api.execute_query(query, variables)

    disabled = []
    protected = []

    for svc in response['data']['CloudServices']['items']:
        status = svc.get("status", {}).get("status", "").lower()
        entry = {"name": svc["name"], "controlKey": svc["controlKey"]}

        if status == "disabled":
            disabled.append(entry)
        elif status == "protected":
            protected.append(entry)

    return disabled, protected

def disable_control(controlKey, scope, test):
    """Disables a specific controlKey for a given scope"""
    if test:
        logger.info("[DRY RUN] Would disable {} on scope {}".format(controlKey,scope))
        return

    mutation = """
    mutation disableService($input: ServiceActionInput!) {
      DisableService(input: $input) {
        success
        __typename
      }
    }
    """
    variables = json.dumps({ 'input': { 'controlKey': controlKey, 'scope': scope } })

    response = api.execute_query(mutation, variables)
    logger.info("Disabled {ck} on {sc}: {status}".format(ck=controlKey,sc=scope, status=response['data']['DisableService']['success']))

def protect_control(controlKey, scope, test):
    """Protects a specific controlKey for a given scope"""
    if test:
        logger.info("[DRY RUN] Would protect {} on scope {}".format(controlKey,scope))
        return

    mutation = """
    mutation protectService($input: ProtectActionInput!) {
      ProtectService(input: $input) {
        success
        __typename
      }
    }
    """
    variables = json.dumps({
        'input': {
            'controlKey': controlKey,
            'scope': scope,
            'identities': [],
            'ssoActorIds': []
        }
    })

    response = api.execute_query(mutation, variables)
    logger.info("Protected {ck} on {sc}: {status}".format(ck=controlKey,sc=scope, status=response['data']['ProtectService']['success']))

def main():
    parser = argparse.ArgumentParser(description="Migrate disabled or protected Cloud Permission Firewall controls between AWS accounts.")
    parser.add_argument("-s", "--source", required=True, help="Source AWS account ID")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument( "-t", "--target", help="Target AWS account ID" )
    group.add_argument( "--target-file", help="Path to file with target AWS account IDs, one per line" )
    
    parser.add_argument("--test", action="store_true", help="Dry run - log actions without executing")
    
    args = parser.parse_args()
    
    # Validate and collect target account IDs
    if args.target:
        target_accounts = [args.target]
    elif args.target_file:
        if not os.path.isfile(args.target_file):
            logger.error(f"Target file '{args.target_file}' does not exist.")
            sys.exit(1)
        with open(args.target_file, "r") as f:
            target_accounts = [line.strip() for line in f if line.strip()]
    else:
        logger.error("Either --target or --target-file must be provided.")
        sys.exit(1)
        
    logger.info("Retrieving scopes for accounts...")
    #get source account scope
    source_scope = get_scope(args.source)
    if source_scope is None:
        # invalid source account, exit
        logger.error("Failed to retrieve scope for source account {}".format(args.source))
        sys.exit(1)
    else:
        logger.info("Source scope: {}".format(source_scope))
        
    logger.info("Fetching disabled and protected services from source account...")
    disabled_controls, protected_controls = get_controls_by_status(source_scope)
    
    total = len(disabled_controls) + len(protected_controls)
    if total == 0:
        logger.info("No disabled or protected services found in source account.")
        return
    
    logger.info("Found {} disabled and {} protected controls to migrate.".format(len(disabled_controls), len(protected_controls)))
    
    # Process each target account individually
    for target_account in target_accounts:
        #get destination account scope
        logger.info(f"Processing target account: {target_account}")
        target_scope = get_scope(target_account)
        if target_scope is None:
            # If we can't find the scope for the target account, skip it
            continue
        else:
            logger.info("Target scope: {}".format(target_scope))

        for control in disabled_controls:
            if args.test:
                logger.info("[DRY RUN] Disabling {control} {control_key} in target account". format(control=control['name'],control_key=control['controlKey']))
            else:
                logger.info("[EXECUTING] Disabling {control} {control_key} in target account". format(control=control['name'],control_key=control['controlKey']))

            disable_control(control["controlKey"], target_scope, args.test)

        for control in protected_controls:
            if args.test:
                logger.info("[DRY RUN] Protecting {control} {control_key} in target account". format(control=control['name'],control_key=control['controlKey']))
            else:
                logger.info("[EXECUTING] Protecting {control} {control_key} in target account". format(control=control['name'],control_key=control['controlKey']))
            protect_control(control["controlKey"], target_scope, args.test)

if __name__ == "__main__":
    main()

