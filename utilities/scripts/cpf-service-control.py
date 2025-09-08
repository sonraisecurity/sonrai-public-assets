import argparse
import json
import os
from sonrai_api import api
from collections import defaultdict


def search_control_keys(pattern):
    query = """
    query getCloudControls($filter: CloudControlFilter) {
      CloudControls(where: $filter) {
        items {
          controlKey
          serviceFriendlyName
          controlType
        }
      }
    }
    """
    query_vars = {
        "filter": {
            "cloudType": {"op": "EQ", "value": "aws"},
            "controlKey": {"op": "ILIKE", "value": f"%{pattern}%"}
        }
    }
    response = api.execute_query(query, json.dumps(query_vars))
    controls = response.get("data", {}).get("CloudControls", {}).get("items", [])
    if not controls:
        print("No matching control keys found.")
        return

    result_dict = defaultdict(lambda: {"friendlyName": "", "actions": set()})

    for item in controls:
        control_key = item.get("controlKey", "")
        result_dict[control_key]["friendlyName"] = item.get("serviceFriendlyName", "")
        ctype_list = item.get("controlType")
        if ctype_list:
            if "Permissions" in ctype_list:
                result_dict[control_key]["actions"].add("Protect")
            if "ServiceBlock" in ctype_list:
                result_dict[control_key]["actions"].add("Disable")

    print("\nMatching Control Keys:\n")
    print(f"{'CONTROL KEY':<35} | {'FRIENDLY NAME':<45} | {'ACTIONS'}")
    print("-" * 100)
    for ck in sorted(result_dict):
        actions = ", ".join(sorted(result_dict[ck]["actions"]))
        print(f"{ck:<35} | {result_dict[ck]['friendlyName']:<45} | {actions}")


def list_service_status(control_key, cloud_hierarchy, scope, verbose=False):
    query = """
    query getCloudServiceUsage( $filters: CloudServiceUsageFilter!) {
      CloudServiceUsage(where: $filters) {
        count
        items {
          project
          usage
          status {
            status
            isStatusPending: isPending
          }
          scope
          account: scope @regex(match: ".*/([0-9]*)", replace: "$1")
          suggestedAction
        }
      }
    }
    """
    query_vars = {
        "filters": {
            "scope": {"op": "STARTS_WITH", "value": scope},
            "controlKey": {"op": "EQ", "value": control_key}
        }
    }
    response = api.execute_query(query, json.dumps(query_vars))
    if not isinstance(response, dict) or "data" not in response:
        print("Error: Unexpected response format from API.")
        return
    items = response.get("data", {}).get("CloudServiceUsage", {}).get("items", [])

    summary = defaultdict(int)
    pending = 0
    detailed = defaultdict(list)

    for item in items:
        status_obj = item.get("status", {})
        status = status_obj.get("status", "UNKNOWN")
        is_pending = status_obj.get("isStatusPending", False)
        key = status.upper()
        if is_pending:
            pending += 1
        summary[key] += 1
        if verbose:
            detailed[key].append((item.get("scope"), item.get("account")))

    print(f"\nService '{control_key}' status summary:")
    for status, count in summary.items():
        print(f" - {status}: {count} account(s)")
    print(f" - Pending: {pending} account(s)\n")

    if verbose:
        for status, records in detailed.items():
            print(f"\n{status} accounts:")
            print("Scope,Account")
            for scope, account in sorted(records):
                print(f"{cloud_hierarchy[scope]},{account}")


def is_action_supported(control_key, action):
    query = """
    query getCloudControls($filter: CloudControlFilter) {
      CloudControls(where: $filter) {
        items {
          controlType
        }
      }
    }
    """
    query_vars = {
        "filter": {
            "controlKey": {"op": "EQ", "value": control_key},
            "cloudType": {"op": "EQ", "value": "aws"}
        }
    }
    response = api.execute_query(query, json.dumps(query_vars))
    items = response.get("data", {}).get("CloudControls", {}).get("items", [])
    if not items:
        print(f"Error: No service found for controlKey '{control_key}'.")
        return None
    
    for item in items:
        control_types = item.get("controlType", [])
        if action == "protect" and "Permissions" in control_types:
            return True
        if action == "disable" and "ServiceBlock" in control_types:
            return True
    return False


def fetch_account_scopes_from_org(org_id):
    query_root = """
    query getCloudHierarchyList($filters: CloudHierarchyFilter) {
      CloudHierarchyList(where: $filters) {
        items {
          rootScope
        }
      }
    }
    """
    vars_root = {
        "filters": {
            "resourceId": {"op": "EQ", "value": org_id},
            "entryType": {"op": "EQ", "value": "managementAccount"},
            "active": {"op": "EQ", "value": True}
        }
    }
    response_root = api.execute_query(query_root, json.dumps(vars_root))
    items_root = response_root.get("data", {}).get("CloudHierarchyList", {}).get("items", [])
    if not items_root:
        print(f"Error: Management org {org_id} not found.")
        return {}

    root_scope = items_root[0].get("rootScope")
    print(f"Fetched root scope: {root_scope}")

    query_accounts = """
    query getCloudHierarchyList($filters: CloudHierarchyFilter) {
      CloudHierarchyList(where: $filters) {
        items {
          resourceId
          scope
          scopeFriendlyName
        }
      }
    }
    """
    vars_accounts = {
        "filters": {
            "purpleEnabled": {"op": "EQ", "value": True},
            "entryType": {"op": "EQ", "value": "account"},
            "active": {"op": "EQ", "value": True},
            "scope": {"op": "STARTS_WITH", "value": root_scope}
        }
    }
    response_accounts = api.execute_query(query_accounts, json.dumps(vars_accounts))
    items = response_accounts.get("data", {}).get("CloudHierarchyList", {}).get("items", [])
    print(f"Found {len(items)} accounts under root scope")
    return {item["resourceId"]: item["scope"] for item in items}, {item["scope"]: item["scopeFriendlyName"] for item in items}, root_scope


def load_account_list(option):
    if len(option) == 1 and os.path.isfile(os.path.expanduser(option[0])):
        with open(os.path.expanduser(option[0]), 'r') as f:
            return [line.strip() for line in f if line.strip()]
    return option


def print_skipped_accounts(all_accounts, excluded_accounts):
    skipped = [acct for acct in all_accounts if acct in excluded_accounts]
    if skipped:
        print("\nSkipping the following accounts (from exclude list):")
        for acct in skipped:
            print(f" - {acct}")


def apply_service_action(action, control_key, scopes, dryrun):
    supported = is_action_supported(control_key, action)
    if supported is None:
        return
    if not supported:
        print(f"Error: The action '{action}' is not supported for controlKey '{control_key}'.")
        return

    mutations = {
        "protect": """
            mutation protectService($input: ProtectActionInput!) {
              ProtectService(input: $input) {
                success
              }
            }
        """,
        "disable": """
            mutation disableService($input: ServiceActionInput!) {
              DisableService(input: $input) {
                success
              }
            }
        """,
        "unprotect": """
            mutation unmanageService($input: ServiceActionInput!) {
              UnmanageService(input: $input) {
                success
              }
            }
        """
    }
    mutation = mutations[action]

    if not scopes:
        print("No matching accounts found for action.")
        return

    print(f"Total accounts to be processed: {len(scopes)}")

    for account, scope in scopes.items():
        query_vars = {
            "input": {
                "controlKey": control_key,
                "scope": scope
            }
        }
        if action == "protect":
            query_vars["input"].update({"identities": [], "ssoActorIds": []})
        if dryrun:
            print(f"[DryRun] Would apply '{action}' to '{control_key}' on account {account} ({scope})")
        else:
            print(f"Applying '{action}' to '{control_key}' on account {account} ({scope})")
            try:
                response = api.execute_query(mutation, json.dumps(query_vars))
                print(response)
            except Exception as e:
                print(f"Error applying action to account {account}: {e}")
                
def pending_changes(scope):
    query = """
        query fetchPendingChangesCount($filters: PendingChangeFilter) {
        PendingChanges(where: $filters) {
          count
          __typename
        }
      }
    """
    query_vars = {
        "filters": {
          "inTransaction": {
            "value": False,
            "op": "EQ"
          },
          "rootScope": {
            "value": scope,
            "op": "EQ"
          }
        }
      }
    response = api.execute_query(query, json.dumps(query_vars))
    count = response.get("data", {}).get("PendingChanges", {}).get("count",0)
    if count > 0:
        print(f"Warning: There are {count} pending changes in the organization.")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Script to manage Sonrai CPF service controls across AWS accounts.")
    parser.add_argument("-q", "--query", dest="search", help="Query CloudControls endpoint for matching control keys")
    parser.add_argument("-i", "--include-list", nargs="*", dest="include", help="List or file of account IDs to include")
    parser.add_argument("-e", "--exclude-list", nargs="*", dest="exclude", help="List or file of account IDs to exclude")
    parser.add_argument("-k", "--control-key", help="The control key to act upon")
    parser.add_argument("-p", "--protect", action="store_true", help="Apply Protect action to the control")
    parser.add_argument("-d", "--disable", action="store_true", help="Apply Disable action to the control")
    parser.add_argument("-u", "--unprotect", action="store_true", help="Apply Unmanage (unprotect) action to the control")
    parser.add_argument("-m", "--management-org", dest="management_org", help="The AWS management org account ID")
    parser.add_argument("-n", "--dryrun", action="store_true", help="Simulate the action without applying changes")
    parser.add_argument("-l", "--list-status", action="store_true", help="List current status of the control across accounts")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed per-account status when listing")
    args = parser.parse_args()

    if args.search:
        search_control_keys(args.search)
        return
    
    if not args.management_org:
        print("Error: You must specify the management organization account ID with --management-org")
        return

    accounts, friendly_scope_mapping, scope = fetch_account_scopes_from_org(args.management_org)

    if args.list_status:
        if not args.control_key:
            print("Error: --control-key (-k) is required with --list-status (-l)")
            return
        list_service_status(args.control_key, friendly_scope_mapping, scope, args.verbose)
        return

    action = None
    if args.protect:
        action = "protect"
    elif args.disable:
        action = "disable"
    elif args.unprotect:
        action = "unprotect"

    if not action or not args.control_key:
        print("Error: You must specify --control-key and one of --protect, --disable, or --unprotect")
        return
    
    if pending_changes(scope):
        print("\n\nThere are already pending changes in CPF for this AWS organization. Proceed? (Y/N) ")
        ans = input().strip().lower()
        if ans != 'y':
            print("Exiting without making changes.")
            return
    

    if args.include:
        include_accounts = load_account_list(args.include)
        scopes = {acct: scope for acct, scope in accounts.items() if acct in include_accounts}
    elif args.exclude:
        exclude_accounts = load_account_list(args.exclude)
        print_skipped_accounts(accounts.keys(), exclude_accounts)
        scopes = {acct: scope for acct, scope in accounts.items() if acct not in exclude_accounts}
    else:
        print("Error: Must provide either --include-list or --exclude-list")
        return

    apply_service_action(action, args.control_key, scopes, args.dryrun)


if __name__ == "__main__":
    main()
