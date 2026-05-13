#!/usr/bin/env python3
import argparse
import json
import sys
import os
from sonrai_api import api, logger

def get_account_scope_map():
    """Fetches all account scopes and returns a dict mapping account_id to scope."""
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
    account_scope_map = {}
    for item in response['data']['CloudHierarchyList']['items']:
        account_scope_map[item['resourceId']] = item['scope']
    return account_scope_map

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
        logger.info("[DRY RUN] Would disable {} on scope {}".format(controlKey, scope))
        return

    mutation = """
    mutation disableService($input: ServiceActionInput!) {
      DisableService(input: $input) {
        success
      }
    }
    """
    variables = json.dumps({ 'input': { 'controlKey': controlKey, 'scope': scope } })
    response = api.execute_query(mutation, variables)
    logger.info("Disabled {ck} on {sc}: {status}".format(ck=controlKey, sc=scope, status=response['data']['DisableService']['success']))

def protect_control(controlKey, scope, test):
    """Protects a specific controlKey for a given scope"""
    if test:
        logger.info("[DRY RUN] Would protect {} on scope {}".format(controlKey, scope))
        return

    mutation = """
    mutation protectService($input: ProtectActionInput!) {
      ProtectService(input: $input) {
        success
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
    logger.info("Protected {ck} on {sc}: {status}".format(ck=controlKey, sc=scope, status=response['data']['ProtectService']['success']))

def main():
    parser = argparse.ArgumentParser(description="Migrate CPF controls and skip if already applied in target.")
    parser.add_argument("-s", "--source", required=True, help="Source AWS account ID")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--target", help="Target AWS account ID")
    group.add_argument("--target-file", help="Path to file with target AWS account IDs")
    parser.add_argument("--test", action="store_true", help="Dry run")
    parser.add_argument("--verbose", action="store_true", help="Show per-account details")

    args = parser.parse_args()

    if args.target_file:
        if not os.path.isfile(args.target_file):
            logger.error(f"Target file '{args.target_file}' does not exist.")
            sys.exit(1)
        with open(args.target_file, "r") as f:
            target_accounts = [line.strip() for line in f if line.strip()]
    else:
        target_accounts = [args.target]

    logger.info(f"Number of target accounts: {len(target_accounts)}")
    logger.info("Retrieving account scopes...")
    account_scope_map = get_account_scope_map()
    source_scope = account_scope_map.get(args.source)

    if not source_scope:
        logger.error(f"Failed to retrieve scope for source account {args.source}")
        sys.exit(1)

    logger.info(f"Fetching config from source account: {args.source}")
    src_disabled, src_protected = get_controls_by_status(source_scope)

    updated_accounts = 0
    per_account_details = []

    for target_account in target_accounts:
        target_scope = account_scope_map.get(target_account)
        if not target_scope:
            logger.error(f"Scope not found for target {target_account}. Skipping.")
            continue

        logger.info(f"Checking current status of target account: {target_account}")
        tgt_disabled, tgt_protected = get_controls_by_status(target_scope)
        
        # Create lookup sets for fast comparison
        tgt_disabled_keys = {svc['controlKey'] for svc in tgt_disabled}
        tgt_protected_keys = {svc['controlKey'] for svc in tgt_protected}

        disabled_count = 0
        protected_count = 0

        # Process Disable Actions
        for control in src_disabled:
            ck = control['controlKey']
            if ck in tgt_disabled_keys:
                logger.info(f"Service '{control['name']}' ({ck}) is already DISABLED in target. Skipping.")
            else:
                disable_control(ck, target_scope, args.test)
                disabled_count += 1

        # Process Protect Actions
        for control in src_protected:
            ck = control['controlKey']
            if ck in tgt_protected_keys:
                logger.info(f"Service '{control['name']}' ({ck}) is already PROTECTED in target. Skipping.")
            else:
                protect_control(ck, target_scope, args.test)
                protected_count += 1

        if disabled_count > 0 or protected_count > 0:
            updated_accounts += 1
        per_account_details.append({
            'account': target_account,
            'disabled': disabled_count,
            'protected': protected_count
        })

    logger.info(f"Migration complete. {updated_accounts} of {len(target_accounts)} target accounts were updated.")
    if args.verbose:
        logger.info("Per-account details:")
        for detail in per_account_details:
            logger.info(f"  Account {detail['account']}: Disabled={detail['disabled']}, Protected={detail['protected']}")


if __name__ == "__main__":
    main()