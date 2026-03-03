#!/usr/bin/env python3
import argparse
import json
import os
import sys
from sonrai_api import api, logger


MUTATION_DISABLE = """
mutation disableService($input: ServiceActionInput!) {
  DisableService(input: $input) {
    success
    issues {
      totalCount
      failureCount
      items {
        scope
        message
        account
        friendlyName
        scopeFriendlyName
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

MUTATION_PROTECT = """
mutation protectService($input: ProtectActionInput!) {
  ProtectService(input: $input) {
    success
    issues {
      totalCount
      failureCount
      items {
        scope
        message
        account
        friendlyName
        scopeFriendlyName
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

MUTATION_UNPROTECT = """
mutation unmanageService($input: ServiceActionInput!) {
  UnmanageService(input: $input) {
    success
    __typename
  }
}
"""

ACTIONS = {
    "disable":   {"mutation": MUTATION_DISABLE,   "result_key": "DisableService",   "uses_apply_at_scope": True},
    "protect":   {"mutation": MUTATION_PROTECT,   "result_key": "ProtectService",   "uses_apply_at_scope": True},
    "unprotect": {"mutation": MUTATION_UNPROTECT, "result_key": "UnmanageService",  "uses_apply_at_scope": False},
}


def load_control_keys(file_path):
    expanded = os.path.expanduser(file_path)
    if not os.path.isfile(expanded):
        logger.error(f"File not found: {file_path}")
        sys.exit(1)
    with open(expanded, "r") as f:
        keys = [line.strip() for line in f if line.strip()]
    if not keys:
        logger.error("No control keys found in file.")
        sys.exit(1)
    return keys


def run_action(action, control_key, scope, apply_at_scope, dryrun):
    config = ACTIONS[action]
    mutation = config["mutation"]
    result_key = config["result_key"]
    uses_apply_at_scope = config["uses_apply_at_scope"]

    input_vars = {"controlKey": control_key, "scope": scope}
    if uses_apply_at_scope:
        input_vars["applyAtScope"] = apply_at_scope

    variables = json.dumps({"input": input_vars})

    if dryrun:
        logger.info(f"[DRY RUN] Would {action} '{control_key}' at scope '{scope}'"
                    + (f" (applyAtScope={apply_at_scope})" if uses_apply_at_scope else ""))
        return True

    try:
        response = api.execute_query(mutation, variables)
        result = response.get("data", {}).get(result_key, {})
        success = result.get("success", False)
        issues = result.get("issues", {})
        failure_count = issues.get("failureCount", 0) if issues else 0

        if success:
            logger.info(f"[{action}] '{control_key}' at scope '{scope}' — OK")
        else:
            logger.warning(f"[{action}] '{control_key}' at scope '{scope}' — success=False")

        if failure_count:
            logger.warning(f"  {failure_count} issue(s) reported:")
            for item in issues.get("items", []):
                logger.warning(f"    [{item.get('account')}] {item.get('message')} (scope: {item.get('scope')})")

        return success
    except Exception as e:
        logger.error(f"Error running {action} on '{control_key}' at '{scope}': {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Bulk apply a CPF service action (disable, protect, unprotect) to a list of control keys at a specified scope.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
actions:
  disable    Block the service via the DisableService mutation
  protect    Restrict the service via the ProtectService mutation
  unprotect  Remove any disable or protect via the UnmanageService mutation

examples:
  Disable all services in a file at the root scope:
    %(prog)s -a disable -f service_keys.txt -s aws/r-xxxx

  Protect services at an OU scope:
    %(prog)s -a protect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx

  Unprotect services at an account scope:
    %(prog)s -a unprotect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx/123456789012

  Dry run to preview changes before applying:
    %(prog)s -a disable -f service_keys.txt -s aws/r-xxxx --dryrun

  Protect without applying at scope (applyAtScope=false):
    %(prog)s -a protect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx --no-apply-at-scope

input file format:
  One control key per line, e.g.:
    guardduty
    s3
    ec2

notes:
  - Requires Sonrai API credentials configured for the sonrai_api library.
  - The scope must be a valid Sonrai cloud hierarchy scope string.
  - applyAtScope is not applicable to the unprotect action and will be ignored.
  - Large input files (350+ keys) are supported; each key is processed sequentially.
  - A summary of succeeded/failed counts is printed at the end.
"""
    )
    parser.add_argument(
        "-a", "--action",
        required=True,
        choices=ACTIONS.keys(),
        metavar="ACTION",
        help="Action to perform: disable, protect, or unprotect"
    )
    parser.add_argument(
        "-f", "--file",
        required=True,
        metavar="FILE",
        help="Path to text file containing one control key (service key) per line"
    )
    parser.add_argument(
        "-s", "--scope",
        required=True,
        metavar="SCOPE",
        help="Sonrai scope at which to apply the action (e.g. 'aws/r-xxxx')"
    )
    parser.add_argument(
        "--apply-at-scope",
        dest="apply_at_scope",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Sets applyAtScope on disable/protect mutations (default: true). Not used for unprotect."
    )
    parser.add_argument(
        "-n", "--dryrun",
        action="store_true",
        help="Log what would be executed without running any mutations"
    )
    args = parser.parse_args()

    control_keys = load_control_keys(args.file)
    total = len(control_keys)
    apply_at_scope_display = args.apply_at_scope if ACTIONS[args.action]["uses_apply_at_scope"] else "N/A"
    logger.info(f"Loaded {total} control key(s) from '{args.file}'")
    logger.info(f"Action: {args.action} | Scope: {args.scope} | applyAtScope={apply_at_scope_display} | dryrun={args.dryrun}")

    succeeded = 0
    failed = 0

    for i, control_key in enumerate(control_keys, start=1):
        logger.info(f"[{i}/{total}] Processing '{control_key}'")
        ok = run_action(args.action, control_key, args.scope, args.apply_at_scope, args.dryrun)
        if ok:
            succeeded += 1
        else:
            failed += 1

    logger.info(f"\nDone. {succeeded} succeeded, {failed} failed out of {total} total.")


if __name__ == "__main__":
    main()
