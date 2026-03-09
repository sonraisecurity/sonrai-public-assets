#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sys
from sonrai_api import api, logger


QUERY_HIERARCHY = """
query resolveScope($filter: CloudHierarchyFilter) {
  CloudHierarchyList(where: $filter) {
    count
    items {
      name
      scope
      scopeFriendlyName
      resourceId
      entryType
    }
  }
}
"""


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
    "disable":   {"mutation": MUTATION_DISABLE,   "result_key": "DisableService",  "uses_apply_at_scope": True},
    "protect":   {"mutation": MUTATION_PROTECT,   "result_key": "ProtectService",  "uses_apply_at_scope": True},
    "unprotect": {"mutation": MUTATION_UNPROTECT, "result_key": "UnmanageService", "uses_apply_at_scope": False},
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


def load_csv(file_path):
    """Load (controlKey, scope) pairs from a CSV file.

    Accepts files with or without a header row. Expected columns:
      controlKey, scope
    """
    expanded = os.path.expanduser(file_path)
    if not os.path.isfile(expanded):
        logger.error(f"CSV file not found: {file_path}")
        sys.exit(1)

    rows = []
    with open(expanded, newline="") as f:
        sample = f.read(1024)
        f.seek(0)
        has_header = csv.Sniffer().has_header(sample)
        reader = csv.DictReader(f) if has_header else csv.reader(f)

        for lineno, row in enumerate(reader, start=2 if has_header else 1):
            if has_header:
                control_key = row.get("controlKey", "").strip()
                scope = row.get("scope", "").strip()
            else:
                if len(row) < 2:
                    logger.warning(f"Skipping line {lineno}: expected 2 columns, got {len(row)}")
                    continue
                control_key, scope = row[0].strip(), row[1].strip()

            if not control_key or not scope:
                logger.warning(f"Skipping line {lineno}: missing controlKey or scope")
                continue
            rows.append((control_key, scope))

    if not rows:
        logger.error("No valid rows found in CSV.")
        sys.exit(1)
    return rows


def resolve_scope(value, org_root=None):
    """Resolve a user-supplied scope identifier to a full Sonrai scope string.

    Accepts:
      - Full scope string (aws/...)       — returned as-is
      - 12-digit account number           — looked up by resourceId
      - OU ID (ou-...)                    — looked up by resourceId
      - Org root ID (r-...)               — looked up by resourceId
      - Account or OU name (any string)   — looked up by name (case-insensitive, exact match)

    If org_root is provided (e.g. 'r-xxxx'), results are filtered to that org only.
    """
    if value.startswith("aws/"):
        if re.match(r"^aws/r-[a-z0-9]+", value):
            return value
        # Looks like a friendly-name path (e.g. aws/SuccessCPFW/Security) — resolve via last segment
        name_segment = value.rstrip("/").rsplit("/", 1)[-1]
        query_filter = {"name": {"op": "ILIKE", "value": name_segment}}
        label = f"scopeFriendlyName '{value}' (name: '{name_segment}')"

    elif re.fullmatch(r"\d{12}", value):
        query_filter = {"resourceId": {"op": "EQ", "value": value}}
        label = f"account number '{value}'"
    elif re.match(r"^ou-", value):
        query_filter = {"resourceId": {"op": "EQ", "value": value}}
        label = f"OU ID '{value}'"
    elif re.match(r"^r-", value):
        query_filter = {"resourceId": {"op": "EQ", "value": value}}
        label = f"org root ID '{value}'"
    else:
        query_filter = {"name": {"op": "ILIKE", "value": value}}
        label = f"name '{value}'"

    if org_root:
        query_filter["scope"] = {"op": "LIKE", "value": f"aws/{org_root}%"}
        label += f" (org: {org_root})"

    try:
        response = api.execute_query(QUERY_HIERARCHY, json.dumps({"filter": query_filter}))
        items = response.get("data", {}).get("CloudHierarchyList", {}).get("items", [])
    except Exception as e:
        logger.error(f"Scope lookup failed: {e}")
        sys.exit(1)

    # Management accounts are never valid targets — skip them silently
    mgmt = [i for i in items if i.get("entryType") == "managementAccount"]
    items = [i for i in items if i.get("entryType") != "managementAccount"]
    if mgmt and not items:
        logger.error(f"No scope found for {label} — only match(es) were management account(s), which are skipped.")
        sys.exit(1)

    if not items:
        logger.error(f"No scope found for {label}. Use a full scope string (e.g. aws/r-xxxx) or check the value.")
        sys.exit(1)

    if len(items) == 1:
        resolved = items[0]["scope"]
        friendly = items[0].get("scopeFriendlyName", "")
        logger.info(f"Resolved '{value}' → {resolved}  ({friendly})")
        return resolved

    # Multiple matches — list them and ask the user to be more specific
    logger.error(f"Ambiguous scope: {len(items)} matches found for {label}. Use a more specific value or a full scope string:")
    for item in items:
        logger.error(f"  [{item.get('entryType')}]  {item['scope']}  ({item.get('scopeFriendlyName', '')})")
    sys.exit(1)


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
        if response is None:
            raise ValueError("API returned no response (None) — scope may be invalid or unrecognized")
        result = response.get("data", {}).get(result_key) or {}
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

input modes:
  --file + --scope   Apply one action to all control keys in the file at a single scope
  --csv              Apply one action to each controlKey/scope pair from the CSV file

examples:
  Disable all services in a file at the root scope (full scope string):
    %(prog)s -a disable -f service_keys.txt -s aws/r-xxxx

  Protect services — scope resolved from an OU name:
    %(prog)s -a protect -f service_keys.txt -s "Services"

  Unprotect services — scope resolved from an account number:
    %(prog)s -a unprotect -f service_keys.txt -s 123456789012

  Disable services — scope resolved from an OU ID:
    %(prog)s -a disable -f service_keys.txt -s ou-xxxx-xxxxxxxxx

  Unprotect specific controlKey/scope pairs from a CSV (exemptions):
    %(prog)s -a unprotect --csv exemptions.csv

  Disable services from a CSV across mixed scopes:
    %(prog)s -a disable --csv actions.csv

  Dry run with CSV to preview before applying:
    %(prog)s -a unprotect --csv exemptions.csv --dryrun

  Protect without applying at scope (applyAtScope=false):
    %(prog)s -a protect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx --no-apply-at-scope

csv file format:
  Two columns, with or without a header row:
    controlKey,scope
    guardduty,aws/r-xxxx/ou-xxxx-xxxxxxxxx/111122223333
    guardduty,aws/r-xxxx/ou-xxxx-xxxxxxxxx/444455556666
    s3,aws/r-xxxx/ou-xxxx-xxxxxxxxx/111122223333

text file format (--file mode):
  One control key per line, e.g.:
    guardduty
    s3
    ec2

notes:
  - Requires Sonrai API credentials configured for the sonrai_api library.
  - The scope must be a valid Sonrai cloud hierarchy scope string.
  - applyAtScope is not applicable to the unprotect action and will be ignored.
  - Large input files (350+ keys) are supported; each entry is processed sequentially.
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

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-f", "--file",
        metavar="FILE",
        help="Path to text file containing one control key per line (requires --scope)"
    )
    input_group.add_argument(
        "--csv",
        metavar="CSV",
        help="Path to CSV file with controlKey and scope columns"
    )

    parser.add_argument(
        "-s", "--scope",
        metavar="SCOPE",
        help="Scope to apply the action at — required with --file, not used with --csv. "
             "Accepts a full scope string (aws/r-xxxx/...), a 12-digit account number, "
             "an OU ID (ou-...), an org root ID (r-...), or an account/OU name."
    )
    parser.add_argument(
        "--org",
        metavar="ORG",
        help="Restrict scope lookups to a specific org root (e.g. r-xxxx or aws/r-xxxx). "
             "Ignored when scope is already a full aws/ string."
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

    if args.file and not args.scope:
        parser.error("--scope / -s is required when using --file / -f")
    if args.csv and args.scope:
        parser.error("--scope / -s should not be used with --csv (scope comes from the CSV)")

    # Normalize --org to bare root ID (r-xxxx), stripping leading aws/ if present
    org_root = None
    if args.org:
        org_root = args.org.removeprefix("aws/")

    # Build list of (control_key, scope) pairs
    if args.file:
        scope = resolve_scope(args.scope, org_root=org_root)
        control_keys = load_control_keys(args.file)
        entries = [(key, scope) for key in control_keys]
        logger.info(f"Loaded {len(entries)} control key(s) from '{args.file}'")
        logger.info(f"Action: {args.action} | Scope: {scope} | applyAtScope="
                    f"{'N/A' if not ACTIONS[args.action]['uses_apply_at_scope'] else args.apply_at_scope}"
                    f" | dryrun={args.dryrun}")
    else:
        raw_entries = load_csv(args.csv)
        scope_cache = {}
        entries = []
        for control_key, raw_scope in raw_entries:
            if raw_scope not in scope_cache:
                scope_cache[raw_scope] = resolve_scope(raw_scope, org_root=org_root)
            entries.append((control_key, scope_cache[raw_scope]))

        logger.info(f"Loaded {len(entries)} row(s) from '{args.csv}'")
        logger.info(f"Action: {args.action} | applyAtScope="
                    f"{'N/A' if not ACTIONS[args.action]['uses_apply_at_scope'] else args.apply_at_scope}"
                    f" | dryrun={args.dryrun}")

    total = len(entries)
    succeeded = 0
    failed = 0

    for i, (control_key, scope) in enumerate(entries, start=1):
        logger.info(f"[{i}/{total}] Processing '{control_key}' at '{scope}'")
        ok = run_action(args.action, control_key, scope, args.apply_at_scope, args.dryrun)
        if ok:
            succeeded += 1
        else:
            failed += 1

    logger.info(f"\nDone. {succeeded} succeeded, {failed} failed out of {total} total.")


if __name__ == "__main__":
    main()
