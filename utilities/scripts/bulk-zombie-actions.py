#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone

from sonrai_api import api, logger

# --- CSV formula injection guard (CWE-1236) ---------------------------------
# Excel and Sheets execute a cell whose text starts with one of these
# characters. Values below come from API data we do not control, so a crafted
# name can run a formula when someone opens the export.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Prefix a quote so a spreadsheet reads the cell as text, not a formula."""
    if not isinstance(value, str) or not value.startswith(_CSV_FORMULA_PREFIXES):
        return value
    try:
        float(value)  # a plain negative number is not a formula
        return value
    except ValueError:
        return "'" + value


def _csv_safe_row(row):
    """Apply _csv_safe across a list row or a dict row."""
    if isinstance(row, dict):
        return {k: _csv_safe(v) for k, v in row.items()}
    return [_csv_safe(v) for v in row]



QUERY_CPF_CONFIGS = """
query fetchCPFConfigs {
  CPFConfigs {
    items {
      key
      value
      defaultValue
    }
  }
}
""".strip()

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
      active
    }
  }
}
""".strip()

QUERY_UNUSED_IDENTITIES = """
query getUnusedIdentities($filters: UnusedIdentitiesFilter!) {
  UnusedIdentities(where: $filters) {
    count
    items {
      account
      identities {
        actorId
        actorName
        scope
        timestamp
      }
    }
  }
}
""".strip()

QUERY_QUARANTINED = """
query fetchIdentitiesInQuarantine($filters: IdentitiesInQuarantineFilter) {
  IdentitiesInQuarantine(where: $filters) {
    count
    items {
      srn
      resourceId
      name
      account
      scope
      quarantinedBy
      quarantinedOn
      inTransaction
      lastUsed
      icon
      quarantinedByFriendlyName
    }
  }
}
""".strip()

MUTATION_QUARANTINE = """
mutation quarantineZombies($input: ChangeQuarantineStatusInput!) {
  ChangeQuarantineStatus(input: $input) {
    transactionId
    success
    count
  }
}
""".strip()

MUTATION_UNQUARANTINE = """
mutation unquarantineZombies($input: ChangeQuarantineStatusInput) {
  ChangeQuarantineStatus(input: $input) {
    success
  }
}
""".strip()

BATCH_SIZE = 50
TABLE_MAX_ROWS = 50

# CSV columns written by the list --output flag (compatible with quarantine/unquarantine input)
LIST_CSV_FIELDNAMES = [
    "Scope",
    "Scope (friendly)",
    "Identity",
    "Last active",
    "Last active (readable)",
    "quarantinedOn",
    "quarantinedBy",
]


def resolve_scope(value):
    """Resolve a user-supplied scope identifier to a full Sonrai scope string.

    Accepts full scope string (aws/...), 12-digit account number, OU ID (ou-...),
    org root ID (r-...), or an account/OU name. Returns None on failure.
    """
    if value.startswith("aws/"):
        if re.match(r"^aws/r-[a-z0-9]+", value):
            return value
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

    try:
        response = api.execute_query(QUERY_HIERARCHY, json.dumps({"filter": query_filter}))
        items = response.get("data", {}).get("CloudHierarchyList", {}).get("items", [])
    except Exception as e:
        logger.error(f"Scope lookup failed: {e}")
        return None

    mgmt = [i for i in items if i.get("entryType") == "managementAccount"]
    items = [i for i in items if i.get("entryType") != "managementAccount"]
    if mgmt and not items:
        logger.error(f"No scope found for {label} — only match(es) were management account(s), which are skipped.")
        return None

    if not items:
        logger.error(f"No scope found for {label}. Use a full scope string (e.g. aws/r-xxxx) or check the value.")
        return None

    if len(items) == 1:
        resolved = items[0]["scope"]
        friendly = items[0].get("scopeFriendlyName", "")
        logger.info(f"Resolved '{value}' → {resolved}  ({friendly})")
        return resolved

    logger.error(f"Ambiguous scope: {len(items)} matches found for {label}. Use a more specific value or a full scope string:")
    for item in items:
        logger.error(f"  [{item.get('entryType')}]  {item['scope']}  ({item.get('scopeFriendlyName', '')})")
    return None


def load_csv(file_path):
    """Load identity rows from a CSV file.

    Accepts the zombie export format (Scope, Identity, Last active) or the
    list-output format (scope, resourceId). Returns a list of partial dicts;
    scope may be empty if the column was blank.
    """
    expanded = os.path.expanduser(file_path)
    if not os.path.isfile(expanded):
        logger.error(f"CSV file not found: {file_path}")
        sys.exit(1)

    rows = []
    with open(expanded, newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            first_line = sample.split("\n")[0].lower()
            has_header = any(col in first_line for col in ("scope", "identity", "last active", "resourceid"))
        reader = csv.DictReader(f, dialect=dialect) if has_header else csv.reader(f, dialect=dialect)

        for lineno, row in enumerate(reader, start=2 if has_header else 1):
            if has_header:
                # Accept both the zombie export column names and the list-output names
                scope = (row.get("Scope") or row.get("scope") or "").strip()
                identity = (row.get("Identity") or row.get("resourceId") or "").strip()
                last_active_str = (row.get("Last active") or "").strip()
            else:
                if len(row) < 2:
                    logger.warning(f"Skipping line {lineno}: expected at least 2 columns, got {len(row)}")
                    continue
                scope = row[0].strip()
                identity = row[1].strip()
                last_active_str = row[2].strip() if len(row) > 2 else ""

            if not identity:
                logger.warning(f"Skipping line {lineno}: missing Identity / resourceId")
                continue

            last_active = None  # None = "Unused" / never used
            if last_active_str and last_active_str.lower() != "unused":
                try:
                    last_active = datetime.fromisoformat(last_active_str.replace("Z", "+00:00"))
                except ValueError:
                    last_active = "UNKNOWN"
                    logger.warning(f"Line {lineno}: unparseable 'Last active' value '{last_active_str}'")

            rows.append({
                "_lineno": lineno,
                "scope": scope,
                "resourceId": identity,
                "lastActive": last_active,
            })

    if not rows:
        logger.error("No valid rows found in CSV.")
        sys.exit(1)
    return rows


def resolve_identity(name, scope):
    """Look up a bare identity name via UnusedIdentities, falling back to
    IdentitiesInQuarantine for identities that are already quarantined.

    Returns the ARN string on success, None if not found or ambiguous.
    """
    filters = {
        "scope": {"op": "EQ", "value": scope},
        "identitySearch": name,
    }
    try:
        response = api.execute_query(QUERY_UNUSED_IDENTITIES, json.dumps({"filters": filters}))
        items = (response or {}).get("data", {}).get("UnusedIdentities", {}).get("items", [])
        matches = [
            ident
            for group in items
            for ident in group.get("identities", [])
            if ident.get("actorName") == name
        ]
        if len(matches) == 1:
            return matches[0]["actorId"]
        if len(matches) > 1:
            logger.warning(f"Ambiguous identity: {len(matches)} matches for '{name}' at scope '{scope}':")
            for m in matches:
                logger.warning(f"  {m.get('actorId')}  ({m.get('scope', '')})")
            logger.warning("  Skipping — provide the full ARN to disambiguate")
            return None
    except Exception as e:
        logger.warning(f"UnusedIdentities lookup failed for '{name}': {e}")

    # Not found in UnusedIdentities — try IdentitiesInQuarantine (already quarantined)
    result = resolve_quarantined_identity(name, scope=scope)
    return result["resourceId"] if result else None


def resolve_quarantined_identity(name, scope=None, quiet=False):
    """Look up a bare identity name in IdentitiesInQuarantine.

    scope is optional — omitting it searches across all quarantined identities.
    quiet suppresses the "not found" warning when the caller has a fallback.
    Returns the full identity dict on success, None if not found or ambiguous.
    """
    filters = {}
    if scope:
        filters["scope"] = {"op": "STARTS_WITH", "value": scope}

    try:
        response = api.execute_query(QUERY_QUARANTINED, json.dumps({"filters": filters}))
        items = (response or {}).get("data", {}).get("IdentitiesInQuarantine", {}).get("items", [])
    except Exception as e:
        logger.warning(f"IdentitiesInQuarantine lookup failed for '{name}': {e}")
        return None

    matches = [i for i in items if i.get("name") == name]

    if not matches:
        if not quiet:
            logger.warning(f"No identity found for '{name}'"
                           + (f" at scope '{scope}'" if scope else "") + " — skipping")
        return None

    if len(matches) > 1:
        logger.warning(f"Ambiguous identity: {len(matches)} quarantined matches for '{name}':")
        for m in matches:
            logger.warning(f"  {m.get('resourceId')}  ({m.get('scope', '')})")
        logger.warning("  Skipping — provide the full ARN to disambiguate")
        return None

    return matches[0]


def resolve_row(row):
    """Fill in missing scope and bare-name identity; derive name, account, rootScope.

    Returns the completed row dict, or None if the row should be skipped.
    """
    lineno = row.get("_lineno", "?")
    identity = row["resourceId"]
    scope = row["scope"]

    # Bare name with no scope — can't extract an account, so search IdentitiesInQuarantine
    # across all scopes and use the result to fill everything in.
    if not identity.startswith("arn:") and not scope:
        result = resolve_quarantined_identity(identity, quiet=True)
        if result is None:
            # Not currently quarantined — search UnusedIdentities across all root scopes
            threshold = fetch_zombie_threshold()
            all_matches = []
            for root in fetch_root_scopes():
                _, items = _query_unused_identities(root, threshold)
                for item in items:
                    item_name = (item.get("actorId") or "").rstrip("/").rsplit("/", 1)[-1]
                    if item_name == identity:
                        all_matches.append(item)
            if len(all_matches) == 0:
                logger.warning(f"Line {lineno}: no identity found for name '{identity}' in UnusedIdentities or IdentitiesInQuarantine — skipping")
                return None
            if len(all_matches) > 1:
                logger.warning(f"Line {lineno}: ambiguous name '{identity}' — {len(all_matches)} matches found:")
                for m in all_matches:
                    logger.warning(f"  {m.get('actorId')}  ({m.get('scope', '')})")
                logger.warning("  Skipping — provide the full ARN to disambiguate")
                return None
            item = all_matches[0]
            result = {
                "resourceId": item["actorId"],
                "scope": item["scope"],
                "name": identity,
                "account": item["scope"].split("/")[3] if len(item["scope"].split("/")) >= 4 else "",
            }
        row["resourceId"] = result["resourceId"]
        row["scope"] = result["scope"]
        row["name"] = result["name"]
        row["account"] = result["account"]
        row["rootScope"] = "/".join(result["scope"].split("/")[:2])
        return row

    if not re.match(r"^aws/r-[a-z0-9]+", scope):
        # Scope is missing or not yet a full aws/r-... string — resolve it.
        lookup = scope if scope else None
        if not lookup:
            m = re.search(r"arn:[^:]+:[^:]+::(\d{12}):", identity)
            if not m:
                logger.warning(f"Line {lineno}: missing Scope and cannot extract account from '{identity}' — skipping")
                return None
            lookup = m.group(1)
            logger.info(f"Line {lineno}: Scope missing, resolving from account {lookup}")
        scope = resolve_scope(lookup)
        if scope is None:
            logger.warning(f"Line {lineno}: could not resolve scope '{lookup}' — skipping")
            return None
        row["scope"] = scope

    if not identity.startswith("arn:"):
        arn = resolve_identity(identity, scope)
        if arn is None:
            return None
        identity = arn
        row["resourceId"] = identity

    name = identity.rstrip("/").rsplit("/", 1)[-1]

    m = re.search(r"arn:[^:]+:[^:]+::(\d{12}):", identity)
    if not m:
        logger.warning(f"Line {lineno}: cannot extract account from ARN '{identity}' — skipping")
        return None
    account = m.group(1)

    parts = scope.split("/")
    if len(parts) < 2:
        logger.warning(f"Line {lineno}: scope '{scope}' too short to derive rootScope — skipping")
        return None

    row["name"] = name
    row["account"] = account
    row["rootScope"] = "/".join(parts[:2])
    return row


def fetch_zombie_threshold():
    """Return zombie_threshold_days from CPFConfigs, defaulting to 90."""
    try:
        response = api.execute_query(QUERY_CPF_CONFIGS, "{}")
        items = (response or {}).get("data", {}).get("CPFConfigs", {}).get("items", [])
        for item in items:
            if item.get("key") == "zombie_threshold_days":
                val = item.get("value") or item.get("defaultValue")
                if val:
                    return int(val)
    except Exception as e:
        logger.warning(f"Could not fetch CPFConfigs: {e}")
    logger.info("zombie_threshold_days not found in CPFConfigs; defaulting to 90")
    return 90


def fetch_root_scopes():
    """Return all org root scope strings (aws/r-xxxx) visible in CloudHierarchyList."""
    query_filter = {"resourceId": {"op": "LIKE", "value": "r-%"}}
    try:
        response = api.execute_query(QUERY_HIERARCHY, json.dumps({"filter": query_filter}))
        items = (response or {}).get("data", {}).get("CloudHierarchyList", {}).get("items", [])
        roots = [
            item["scope"] for item in items
            if re.match(r"^aws/r-[a-z0-9]+$", item.get("scope", ""))
        ]
    except Exception as e:
        logger.error(f"Failed to fetch root scopes: {e}")
        sys.exit(1)

    if not roots:
        logger.error("No org root scopes found in CloudHierarchyList.")
        sys.exit(1)

    return roots


def fetch_friendly_names(scopes):
    """Return {scope: scopeFriendlyName} for a collection of full scope strings.

    Groups by org root and issues one CloudHierarchyList query per root to
    avoid per-scope API calls.
    """
    root_groups = {}
    for scope in set(scopes):
        parts = scope.split("/")
        if len(parts) >= 2:
            root_groups.setdefault("/".join(parts[:2]), None)

    result = {}
    for root in root_groups:
        query_filter = {"scope": {"op": "STARTS_WITH", "value": root}}
        try:
            response = api.execute_query(QUERY_HIERARCHY, json.dumps({"filter": query_filter}))
            items = (response or {}).get("data", {}).get("CloudHierarchyList", {}).get("items", [])
            for item in items:
                if item.get("scopeFriendlyName"):
                    result[item["scope"]] = item["scopeFriendlyName"]
        except Exception as e:
            logger.warning(f"Could not fetch friendly scope names for '{root}': {e}")

    return result


def fetch_account_status(root_scopes):
    """Return {scope: {entryType, active}} for every account-level entry under the given org roots.

    One CloudHierarchyList query per root. Used to filter out identities whose
    account is a management account or suspended/deactivated before quarantining.
    """
    status = {}
    for root in root_scopes:
        query_filter = {"scope": {"op": "STARTS_WITH", "value": root}}
        try:
            response = api.execute_query(QUERY_HIERARCHY, json.dumps({"filter": query_filter}))
            items = (response or {}).get("data", {}).get("CloudHierarchyList", {}).get("items", [])
            for item in items:
                if item.get("entryType") in ("account", "managementAccount"):
                    status[item["scope"]] = {
                        "entryType": item.get("entryType"),
                        "active": item.get("active", True),
                    }
        except Exception as e:
            logger.warning(f"Could not fetch account status for '{root}': {e}")
    return status


def validate_quarantine_targets(rows):
    """Drop identities whose account is a management account or inactive.

    Returns (kept_rows, summary_dict).
    """
    if not rows:
        return rows, {"mgmt": 0, "inactive": 0, "unknown": 0}

    root_scopes = sorted({r["rootScope"] for r in rows})
    status = fetch_account_status(root_scopes)

    kept = []
    skipped_mgmt = 0
    skipped_inactive = 0
    skipped_unknown = 0
    for r in rows:
        info = status.get(r["scope"])
        if info is None:
            logger.warning(f"Skipping '{r['name']}': account scope '{r['scope']}' not found in CloudHierarchyList")
            skipped_unknown += 1
            continue
        if info["entryType"] == "managementAccount":
            logger.warning(f"Skipping '{r['name']}': account '{r['account']}' is a management account")
            skipped_mgmt += 1
            continue
        if not info["active"]:
            logger.warning(f"Skipping '{r['name']}': account '{r['account']}' is suspended/deactivated")
            skipped_inactive += 1
            continue
        kept.append(r)

    return kept, {"mgmt": skipped_mgmt, "inactive": skipped_inactive, "unknown": skipped_unknown}


def ms_to_iso(ms):
    if ms is None:
        return ""
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_to_age(ms):
    """Return a human-readable age string for a millisecond epoch timestamp."""
    if not ms or int(ms) == 0:
        return "never used"
    days = (datetime.now(timezone.utc).timestamp() * 1000 - int(ms)) / 86_400_000
    if days < 1:
        return "< 1 day ago"
    if days < 2:
        return "1 day ago"
    if days < 60:
        return f"{int(days)} days ago"
    months = int(days / 30.44)
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years, rem_months = divmod(months, 12)
    if rem_months:
        return f"{years} yr{'s' if years != 1 else ''}, {rem_months} mo ago"
    return f"{years} year{'s' if years != 1 else ''} ago"


def _print_table(rows, headers):
    """Print a left-aligned table to stdout with dynamic column widths."""
    widths = [len(h) for h in headers]
    for row in rows:
        for j, val in enumerate(row):
            widths[j] = max(widths[j], len(val))
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(val.ljust(widths[i]) for i, val in enumerate(row)))


def _render_table(table_rows, headers, output_file=None):
    """Print a table, truncating to TABLE_MAX_ROWS when the dataset is large.

    If output_file is set and the table would be truncated, skip the table
    entirely — _write_csv already logged the row count and destination.
    """
    if len(table_rows) <= TABLE_MAX_ROWS:
        _print_table(table_rows, headers)
        return
    if output_file:
        print(f"({len(table_rows)} rows — see {output_file})")
        return
    _print_table(table_rows[:TABLE_MAX_ROWS], headers)
    print(f"... and {len(table_rows) - TABLE_MAX_ROWS} more rows (use --output FILE to capture all)")


def _write_csv(csv_rows, output_file):
    """Write list output rows to a CSV file."""
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LIST_CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_csv_safe_row(r) for r in csv_rows)
    logger.info(f"Wrote {len(csv_rows)} rows to {output_file}")


def list_quarantined(scope_filter=None, days_quarantined=None, output_file=None):
    """List identities currently in quarantine."""
    filters = {}
    if scope_filter:
        filters["scope"] = {"op": "STARTS_WITH", "value": scope_filter}

    try:
        response = api.execute_query(QUERY_QUARANTINED, json.dumps({"filters": filters}))
        data = (response or {}).get("data", {}).get("IdentitiesInQuarantine", {})
        items = data.get("items", [])
        total = data.get("count", 0)
    except Exception as e:
        logger.error(f"Failed to fetch quarantined identities: {e}")
        sys.exit(1)

    logger.info(f"API returned {total} quarantined identit{'y' if total == 1 else 'ies'}")

    if days_quarantined is not None:
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        items = [
            i for i in items
            if i.get("quarantinedOn") is not None
            and (now_ms - i["quarantinedOn"]) / 86_400_000 >= days_quarantined
        ]
        logger.info(f"After --days-quarantined {days_quarantined} filter: {len(items)} remain")

    if not items:
        print("No quarantined identities found.")
        return

    friendly = fetch_friendly_names(i["scope"] for i in items)

    csv_rows = []
    table_rows = []
    for item in items:
        scope = item.get("scope", "")
        arn = item.get("resourceId", "")
        last_used_ms = item.get("lastUsed")
        quarantined_on_ms = item.get("quarantinedOn")
        scope_friendly = friendly.get(scope, scope)

        csv_rows.append({
            "Scope": scope,
            "Scope (friendly)": scope_friendly,
            "Identity": arn,
            "Last active": ms_to_iso(last_used_ms),
            "Last active (readable)": ms_to_age(last_used_ms),
            "quarantinedOn": ms_to_iso(quarantined_on_ms),
            "quarantinedBy": item.get("quarantinedBy", ""),
        })
        table_rows.append([
            item.get("name", ""),
            item.get("account", ""),
            scope_friendly,
            ms_to_iso(quarantined_on_ms),
            ms_to_age(last_used_ms),
        ])

    if output_file:
        _write_csv(csv_rows, output_file)

    _render_table(table_rows, ["NAME", "ACCOUNT", "SCOPE", "QUARANTINED ON", "LAST USED"], output_file)


def _query_unused_identities(scope, threshold):
    """Run one UnusedIdentities API call for the given scope and day threshold.

    Uses STARTS_WITH for root/OU scopes (< 4 path segments) and EQ for account
    scopes (4 segments) so the API filter matches the right level.
    """
    parts = scope.rstrip("/").split("/")
    if len(parts) >= 4:
        scope_filter = {"op": "EQ", "value": scope}
    else:
        scope_filter = {"op": "STARTS_WITH", "value": scope.rstrip("/") + "/"}

    filters = {
        "daysSinceLastLogin": {"op": "EQ", "value": str(threshold)},
        "identitySearch": "",
        "scope": scope_filter,
    }
    response = api.execute_query(QUERY_UNUSED_IDENTITIES, json.dumps({"filters": filters}))
    data = (response or {}).get("data", {}).get("UnusedIdentities", {})
    groups = data.get("items", [])
    count = data.get("count", 0)
    identities = [ident for group in groups for ident in group.get("identities", [])]
    return count, identities


def list_zombies(scope_filter=None, days=None, output_file=None):
    """List zombie (unused) identities."""
    if days is None:
        days = fetch_zombie_threshold()
        logger.info(f"Using zombie threshold: {days} days (from CPFConfigs)")
    else:
        logger.info(f"Using zombie threshold: {days} days (from --days)")

    # The API requires a scope filter. If none supplied, fan out across all org roots.
    if scope_filter:
        scope_queries = [scope_filter]
    else:
        scope_queries = fetch_root_scopes()
        logger.info(f"No --scope provided; querying {len(scope_queries)} org root(s): {', '.join(scope_queries)}")

    identities = []
    try:
        for scope in scope_queries:
            count, found = _query_unused_identities(scope, days)
            logger.info(f"Scope '{scope}': {count} account group(s), {len(found)} identit{'y' if len(found) == 1 else 'ies'}")
            identities.extend(found)
    except Exception as e:
        logger.error(f"Failed to fetch unused identities: {e}")
        sys.exit(1)

    logger.info(f"Total: {len(identities)} identit{'y' if len(identities) == 1 else 'ies'}")

    if not identities:
        print("No zombie identities found.")
        return

    friendly = fetch_friendly_names(i["scope"] for i in identities)

    csv_rows = []
    table_rows = []
    for ident in identities:
        scope = ident.get("scope", "")
        arn = ident.get("actorId", "")
        last_used_ms = ident.get("timestamp")
        scope_friendly = friendly.get(scope, scope)
        name = arn.rstrip("/").rsplit("/", 1)[-1] if arn else ident.get("actorName", "")
        m = re.search(r"arn:[^:]+:[^:]+::(\d{12}):", arn)
        account = m.group(1) if m else ""

        csv_rows.append({
            "Scope": scope,
            "Scope (friendly)": scope_friendly,
            "Identity": arn,
            "Last active": ms_to_iso(last_used_ms) if last_used_ms and int(last_used_ms) > 0 else "Unused",
            "Last active (readable)": ms_to_age(last_used_ms),
            "quarantinedOn": "",
            "quarantinedBy": "",
        })
        table_rows.append([
            name,
            account,
            scope_friendly,
            ms_to_age(last_used_ms),
        ])

    if output_file:
        _write_csv(csv_rows, output_file)

    _render_table(table_rows, ["NAME", "ACCOUNT", "SCOPE", "LAST ACTIVE"], output_file)


def _batch(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def run_quarantine(groups, dryrun):
    total = sum(len(v) for v in groups.values())
    total_batches = sum((len(v) + BATCH_SIZE - 1) // BATCH_SIZE for v in groups.values())
    succeeded = 0
    failed = 0
    batch_num = 0

    for root_scope, identities in groups.items():
        for batch in _batch(identities, BATCH_SIZE):
            batch_num += 1
            if dryrun:
                logger.info(f"[DRY RUN] [quarantine {batch_num}/{total_batches}] would quarantine {len(batch)} identit{'y' if len(batch) == 1 else 'ies'} at rootScope '{root_scope}'")
                succeeded += len(batch)
                continue

            input_vars = {
                "identities": [
                    {
                        "resourceId": i["resourceId"],
                        "scope": i["scope"],
                        "name": i["name"],
                        "account": i["account"],
                    }
                    for i in batch
                ],
                "action": "ADD",
                "rootScope": root_scope,
            }
            try:
                response = api.execute_query(MUTATION_QUARANTINE, json.dumps({"input": input_vars}))
                result = (response or {}).get("data", {}).get("ChangeQuarantineStatus", {})
                success = result.get("success", False)
                count = result.get("count", len(batch))
                if success:
                    logger.info(f"[quarantine {batch_num}/{total_batches}] {count} identit{'y' if count == 1 else 'ies'} at rootScope '{root_scope}' — OK")
                    succeeded += len(batch)
                else:
                    logger.warning(f"[quarantine {batch_num}/{total_batches}] batch at rootScope '{root_scope}' — success=False")
                    failed += len(batch)
            except Exception as e:
                logger.error(f"[quarantine {batch_num}/{total_batches}] error at '{root_scope}': {e}")
                failed += len(batch)

    logger.info(f"\nDone. {succeeded} succeeded, {failed} failed out of {total} total.")


def run_unquarantine(groups, dryrun):
    total = sum(len(v) for v in groups.values())
    total_batches = sum((len(v) + BATCH_SIZE - 1) // BATCH_SIZE for v in groups.values())
    succeeded = 0
    failed = 0
    batch_num = 0

    for root_scope, identities in groups.items():
        for batch in _batch(identities, BATCH_SIZE):
            batch_num += 1
            if dryrun:
                logger.info(f"[DRY RUN] [unquarantine {batch_num}/{total_batches}] would unquarantine {len(batch)} identit{'y' if len(batch) == 1 else 'ies'} at rootScope '{root_scope}'")
                succeeded += len(batch)
                continue

            input_vars = {
                "action": "REMOVE",
                "rootScope": root_scope,
                "identities": [
                    {
                        "srn": None,
                        "resourceId": i["resourceId"],
                        "name": i["name"],
                        "account": i["account"],
                        "scope": i["scope"],
                        "icon": None,
                    }
                    for i in batch
                ],
            }
            try:
                response = api.execute_query(MUTATION_UNQUARANTINE, json.dumps({"input": input_vars}))
                result = (response or {}).get("data", {}).get("ChangeQuarantineStatus", {})
                success = result.get("success", False)
                if success:
                    logger.info(f"[unquarantine {batch_num}/{total_batches}] {len(batch)} identit{'y' if len(batch) == 1 else 'ies'} at rootScope '{root_scope}' — OK")
                    succeeded += len(batch)
                else:
                    logger.warning(f"[unquarantine {batch_num}/{total_batches}] batch at rootScope '{root_scope}' — success=False")
                    failed += len(batch)
            except Exception as e:
                logger.error(f"[unquarantine {batch_num}/{total_batches}] error at '{root_scope}': {e}")
                failed += len(batch)

    logger.info(f"\nDone. {succeeded} succeeded, {failed} failed out of {total} total.")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk quarantine, unquarantine, or list zombie identities via the Sonrai API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
subcommands:
  quarantine         Quarantine zombie identities from a CSV file
  unquarantine       Remove quarantine from identities in a CSV file
  list-quarantined   List currently quarantined identities
  list-zombies       List zombie (unused) identities

examples:
  Quarantine all zombies from a CSV (days threshold from CPFConfigs):
    %(prog)s quarantine -c zombies.csv

  Quarantine only identities unused for 180+ days:
    %(prog)s quarantine -c zombies.csv --days 180

  Quarantine identities scoped to a specific account:
    %(prog)s quarantine -c zombies.csv --scope 471112776591

  Dry run to preview what would be quarantined:
    %(prog)s quarantine -c zombies.csv --dryrun

  Unquarantine identities from a CSV:
    %(prog)s unquarantine -c zombies.csv

  List all quarantined identities:
    %(prog)s list-quarantined

  List identities quarantined for 30+ days and export to CSV:
    %(prog)s list-quarantined --days 30 --output quarantined.csv

  List all zombie identities (threshold from CPFConfigs):
    %(prog)s list-zombies

  List zombies unused for 180+ days in a specific org:
    %(prog)s list-zombies --days 180 --scope aws/r-xxxx --output zombies-out.csv

  Pipe zombie list into quarantine:
    %(prog)s list-zombies --output zombies-out.csv
    %(prog)s quarantine -c zombies-out.csv --dryrun

csv file format (quarantine/unquarantine input):
  Columns (with or without a header row):
    Scope,Identity,Last active
    aws/r-xxxx/ou-xxxx-xxxxxxxxx/123456789012,arn:aws:iam::123456789012:role/MyRole,Unused
    aws/r-xxxx/ou-xxxx-xxxxxxxxx/123456789012,arn:aws:iam::123456789012:role/OtherRole,2025-08-01T00:00:00.000Z

  - Scope may be blank; derived from the account number in the ARN via API lookup.
  - Identity may be a bare name instead of a full ARN; looked up via UnusedIdentities API.
  - The output of list-quarantined/list-zombies --output is usable as input for quarantine or unquarantine.
"""
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    q_parser = subparsers.add_parser("quarantine", help="Quarantine zombie identities from a CSV")
    q_parser.add_argument("-c", "--csv", required=True, metavar="FILE", help="CSV file of identities to quarantine")
    q_parser.add_argument(
        "-s", "--scope", metavar="SCOPE",
        help="Only process identities at this scope (account number, OU ID, name, or full scope string)",
    )
    q_parser.add_argument(
        "--days", type=int, metavar="N",
        help="Only quarantine identities unused for >= N days (default: zombie_threshold_days from CPFConfigs)",
    )
    q_parser.add_argument("-n", "--dryrun", action="store_true", help="Preview actions without executing mutations")

    u_parser = subparsers.add_parser("unquarantine", help="Remove quarantine from identities in a CSV")
    u_parser.add_argument("-c", "--csv", required=True, metavar="FILE", help="CSV file of identities to unquarantine")
    u_parser.add_argument(
        "-s", "--scope", metavar="SCOPE",
        help="Only process identities at this scope",
    )
    u_parser.add_argument("-n", "--dryrun", action="store_true", help="Preview actions without executing mutations")

    lq_parser = subparsers.add_parser("list-quarantined", help="List currently quarantined identities")
    lq_parser.add_argument(
        "-s", "--scope", metavar="SCOPE",
        help="Filter to identities at this scope (account number, OU ID, name, or full scope string)",
    )
    lq_parser.add_argument(
        "--days", type=int, metavar="N", dest="days_quarantined",
        help="Only show identities that have been quarantined for >= N days",
    )
    lq_parser.add_argument("-o", "--output", metavar="FILE", help="Write results to a CSV file")

    lz_parser = subparsers.add_parser("list-zombies", help="List zombie (unused) identities")
    lz_parser.add_argument(
        "-s", "--scope", metavar="SCOPE",
        help="Filter to identities at this scope (account number, OU ID, name, or full scope string)",
    )
    lz_parser.add_argument(
        "--days", type=int, metavar="N",
        help="Only show identities unused for >= N days (default: zombie_threshold_days from CPFConfigs)",
    )
    lz_parser.add_argument("-o", "--output", metavar="FILE", help="Write results to a CSV file (compatible with quarantine input)")

    args = parser.parse_args()

    if args.command in ("list-quarantined", "list-zombies"):
        scope_filter = None
        if args.scope:
            scope_filter = resolve_scope(args.scope)
            if scope_filter is None:
                sys.exit(1)
        if args.command == "list-zombies":
            list_zombies(scope_filter=scope_filter, days=args.days, output_file=args.output)
        else:
            list_quarantined(scope_filter=scope_filter, days_quarantined=args.days_quarantined, output_file=args.output)
        return

    # quarantine / unquarantine
    rows = load_csv(args.csv)
    logger.info(f"Loaded {len(rows)} rows from '{args.csv}'")

    bare_name_count = sum(1 for r in rows if not r["resourceId"].startswith("arn:"))
    if bare_name_count:
        logger.info(f"{bare_name_count} of {len(rows)} rows use bare identity names — each requires a per-row API lookup, which may be slow at scale")

    resolved = []
    for i, row in enumerate(rows, start=1):
        r = resolve_row(row)
        if r is not None:
            resolved.append(r)
        if i % 1000 == 0:
            logger.info(f"  resolved {i}/{len(rows)} rows...")

    skipped = len(rows) - len(resolved)
    logger.info(f"Resolved {len(resolved)} identities" + (f" ({skipped} skipped)" if skipped else ""))

    if args.scope:
        scope_filter = resolve_scope(args.scope)
        if scope_filter is None:
            sys.exit(1)
        before = len(resolved)
        resolved = [r for r in resolved if r["scope"].startswith(scope_filter)]
        logger.info(f"Scope filter '{scope_filter}': {len(resolved)} of {before} identities match")

    if args.command == "quarantine":
        before = len(resolved)
        resolved, skipped = validate_quarantine_targets(resolved)
        parts = [f"{len(resolved)} qualify"]
        if skipped["mgmt"]:
            parts.append(f"{skipped['mgmt']} in management account")
        if skipped["inactive"]:
            parts.append(f"{skipped['inactive']} in suspended/deactivated account")
        if skipped["unknown"]:
            parts.append(f"{skipped['unknown']} account not found")
        if before != len(resolved):
            logger.info("Account validation: " + ", ".join(parts))

        days = args.days
        if days is None:
            days = fetch_zombie_threshold()
            logger.info(f"Using zombie threshold: {days} days (from CPFConfigs)")
        else:
            logger.info(f"Using zombie threshold: {days} days (from --days)")

        today = datetime.now(timezone.utc)
        filtered = []
        skipped_recent = 0
        skipped_unknown = 0
        for r in resolved:
            la = r["lastActive"]
            if la is None:
                filtered.append(r)
            elif la == "UNKNOWN":
                logger.warning(f"Skipping '{r['name']}': unparseable last-active date")
                skipped_unknown += 1
            else:
                if (today - la).days >= days:
                    filtered.append(r)
                else:
                    skipped_recent += 1
        resolved = filtered
        parts = [f"{len(resolved)} qualify"]
        if skipped_recent:
            parts.append(f"{skipped_recent} too recent")
        if skipped_unknown:
            parts.append(f"{skipped_unknown} unknown last-active")
        logger.info(f"Days filter (>= {days} days unused): " + ", ".join(parts))

    if not resolved:
        logger.info("No identities to process.")
        return

    groups = {}
    for r in resolved:
        groups.setdefault(r["rootScope"], []).append(r)

    action_label = "Quarantining" if args.command == "quarantine" else "Unquarantining"
    logger.info(
        f"{'[DRY RUN] ' if args.dryrun else ''}{action_label} {len(resolved)} "
        f"identit{'y' if len(resolved) == 1 else 'ies'} across {len(groups)} org root(s)"
    )

    if args.command == "quarantine":
        run_quarantine(groups, args.dryrun)
    else:
        run_unquarantine(groups, args.dryrun)


if __name__ == "__main__":
    main()
