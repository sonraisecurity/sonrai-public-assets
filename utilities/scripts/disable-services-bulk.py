#!/usr/bin/env python3
import argparse
import json
import os
import sys
from sonrai_api import api, logger


MUTATION = """
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


def disable_service(control_key, scope, apply_at_scope, dryrun):
    variables = json.dumps({
        "input": {
            "controlKey": control_key,
            "scope": scope,
            "applyAtScope": apply_at_scope
        }
    })

    if dryrun:
        logger.info(f"[DRY RUN] Would disable '{control_key}' at scope '{scope}' (applyAtScope={apply_at_scope})")
        return True

    try:
        response = api.execute_query(MUTATION, variables)
        result = response.get("data", {}).get("DisableService", {})
        success = result.get("success", False)
        issues = result.get("issues", {})
        failure_count = issues.get("failureCount", 0) if issues else 0

        if success:
            logger.info(f"Disabled '{control_key}' at scope '{scope}'")
        else:
            logger.warning(f"DisableService returned success=False for '{control_key}' at '{scope}'")

        if failure_count:
            logger.warning(f"  {failure_count} issue(s) reported:")
            for item in issues.get("items", []):
                logger.warning(f"    [{item.get('account')}] {item.get('message')} (scope: {item.get('scope')})")

        return success
    except Exception as e:
        logger.error(f"Error disabling '{control_key}' at '{scope}': {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Bulk disable Sonrai CPF services by control key at a specified scope.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  Disable all control keys listed in a file at a given scope:
    %(prog)s -f service_keys.txt -s aws/r-bitm

  Preview what would be disabled without making changes:
    %(prog)s -f service_keys.txt -s aws/r-bitm --dryrun

  Disable without applying at scope (applyAtScope=false):
    %(prog)s -f service_keys.txt -s aws/r-bitm --no-apply-at-scope

input file format:
  One control key per line, e.g.:
    guardduty
    s3
    ec2

notes:
  - Requires Sonrai API credentials configured for the sonrai_api library.
  - The scope must be a valid Sonrai cloud hierarchy scope string.
  - Large input files (350+ keys) are supported; each key is processed sequentially.
  - A summary of succeeded/failed counts is printed at the end.
"""
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
        help="Sonrai scope at which to disable each service (e.g. 'aws/r-bitm')"
    )
    parser.add_argument(
        "--apply-at-scope",
        dest="apply_at_scope",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass applyAtScope=true/false on the DisableService mutation (default: true). "
             "Use --no-apply-at-scope to set false."
    )
    parser.add_argument(
        "-n", "--dryrun",
        action="store_true",
        help="Log what would be disabled without executing any mutations"
    )
    args = parser.parse_args()

    control_keys = load_control_keys(args.file)
    total = len(control_keys)
    logger.info(f"Loaded {total} control key(s) from '{args.file}'")
    logger.info(f"Target scope: {args.scope} | applyAtScope={args.apply_at_scope} | dryrun={args.dryrun}")

    succeeded = 0
    failed = 0

    for i, control_key in enumerate(control_keys, start=1):
        logger.info(f"[{i}/{total}] Processing '{control_key}'")
        ok = disable_service(control_key, args.scope, args.apply_at_scope, args.dryrun)
        if ok:
            succeeded += 1
        else:
            failed += 1

    logger.info(f"\nDone. {succeeded} succeeded, {failed} failed out of {total} total.")


if __name__ == "__main__":
    main()
