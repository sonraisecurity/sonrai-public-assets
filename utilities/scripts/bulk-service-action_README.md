# bulk-service-action.py

Bulk applies a Sonrai Cloud Permission Firewall (CPF) service action — **disable**, **protect**, or **unprotect** — to a list of control keys. Supports two input modes: a plain text file of control keys at a single scope, or a CSV file with per-row control key and scope pairs.

## Prerequisites

- **Python 3.9+** and the [sonrai_api](../sonrai_api/README.md) library copied into the same directory as the script.
- Install required libraries: `pip3 install -r sonrai_api/requirements.txt`
- Sonrai API credentials configured in `sonrai_api/config.json`.

## Usage

```
# File mode — one action applied to all keys at a single scope
python bulk-service-action.py -a ACTION -f FILE -s SCOPE [--no-apply-at-scope] [-n]

# CSV mode — one action applied to each controlKey/scope pair in the CSV
python bulk-service-action.py -a ACTION --csv FILE [--no-apply-at-scope] [-n]
```

### Arguments

| Flag | Long form | Required | Default | Description |
|------|-----------|----------|---------|-------------|
| `-a` | `--action` | Yes | — | Action to perform: `disable`, `protect`, or `unprotect` |
| `-f` | `--file` | One of `-f` or `--csv` | — | Text file with one control key per line (requires `--scope`) |
| | `--csv` | One of `-f` or `--csv` | — | CSV file with `controlKey` and `scope` columns |
| `-s` | `--scope` | With `--file` only | — | Scope to apply the action at. Accepts a full scope string, friendly-name path (e.g. `aws/SuccessCPFW/Security`), account number, OU ID, org root ID, or account/OU name. |
| | `--org` | No | — | Restrict scope lookups to a specific org root (e.g. `r-xxxx` or `aws/r-xxxx`). Useful when a name or account number exists in multiple orgs. |
| | `--apply-at-scope` / `--no-apply-at-scope` | No | `true` | Sets `applyAtScope` on disable/protect mutations. Not used for `unprotect`. |
| `-n` | `--dryrun` | No | `false` | Log what would be executed without running any mutations |

### Actions

| Action | Mutation | Description |
|--------|----------|-------------|
| `disable` | `DisableService` | Blocks the service at the specified scope |
| `protect` | `ProtectService` | Restricts the service at the specified scope |
| `unprotect` | `UnmanageService` | Removes any disable or protect from the specified scope |

### Input File Format (--file mode)

One control key per line. Blank lines are ignored.

```
guardduty
s3
ec2
athena
```

### CSV Format (--csv mode)

Two columns: `controlKey` and `scope`. A header row is optional — the script detects it automatically. The `scope` column accepts the same formats as `--scope`: full scope strings, friendly-name paths, account numbers, OU IDs, or names.

```csv
controlKey,scope
guardduty,111122223333
guardduty,444455556666
s3,aws/r-xxxx/ou-xxxx-xxxxxxxxx/111122223333
```

## Examples

**Disable** all services in a file using a full scope string:
```bash
python bulk-service-action.py -a disable -f service_keys.txt -s aws/r-xxxx
```

**Protect** services — scope resolved from an OU name:
```bash
python bulk-service-action.py -a protect -f service_keys.txt -s "Services"
```

**Unprotect** services — scope resolved from a 12-digit account number:
```bash
python bulk-service-action.py -a unprotect -f service_keys.txt -s 123456789012
```

**Disable** services — scope resolved from an OU ID:
```bash
python bulk-service-action.py -a disable -f service_keys.txt -s ou-xxxx-xxxxxxxxx
```

**Unprotect** specific controlKey/scope pairs from a CSV (e.g. exemptions after a bulk disable):
```bash
python bulk-service-action.py -a unprotect --csv exemptions.csv
```

**Disable** services across mixed scopes from a CSV:
```bash
python bulk-service-action.py -a disable --csv actions.csv
```

Dry run to preview changes without applying anything:
```bash
python bulk-service-action.py -a unprotect --csv exemptions.csv --dryrun
```

Protect without applying at scope (`applyAtScope=false`):
```bash
python bulk-service-action.py -a protect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx --no-apply-at-scope
```

### Two-Pass Workflow: Bulk Disable with Exemptions

A common pattern is to disable a set of services org-wide, then unprotect specific accounts that are allowed to use one of those services:

```bash
# Pass 1: disable everything at root
python bulk-service-action.py -a disable -f service_keys.txt -s aws/r-xxxx

# Pass 2: carve out exemptions per account
python bulk-service-action.py -a unprotect --csv exemptions.csv
```

Where `exemptions.csv` lists only the specific service/account combinations to exempt:
```csv
controlKey,scope
guardduty,aws/r-xxxx/ou-xxxx-xxxxxxxxx/111122223333
guardduty,aws/r-xxxx/ou-xxxx-xxxxxxxxx/444455556666
```

## Output

The script logs progress for each entry and prints a summary on completion:

```
INFO - Loaded 5 control key(s) from 'service_keys.txt'
INFO - Action: disable | Scope: aws/r-xxxx | applyAtScope=True | dryrun=False
INFO - [1/5] Processing 'guardduty' at 'aws/r-xxxx'
INFO - [disable] 'guardduty' at scope 'aws/r-xxxx' — OK
...
INFO - Done. 5 succeeded, 0 failed out of 5 total.
```

If a mutation returns failures, each issue is logged with its account, scope, and message.

## Notes

- Large input files (350+ keys or rows) are supported; each entry is processed sequentially.
- The `--scope` argument accepts several formats — the script resolves them automatically:
  | Input | Example | Resolved by |
  |-------|---------|-------------|
  | Full scope string | `aws/r-xxxx/ou-xxxx-xxxxxxxxx/123456789012` | Passed through as-is |
  | Friendly-name path | `aws/SuccessCPFW/Security` | `scopeFriendlyName` lookup |
  | 12-digit account number | `123456789012` | `resourceId` lookup |
  | OU ID | `ou-xxxx-xxxxxxxxx` | `resourceId` lookup |
  | Org root ID | `r-xxxx` | `resourceId` lookup |
  | Account or OU name | `bathurst` or `Services` | `name` ILIKE lookup |
- Name lookups use a case-insensitive exact match — `Support` will not match `Sonrai Support Org`. If a name lookup still returns multiple matches (same name in different orgs), use `--org` to restrict to a specific org, or use a full scope string.
- `--org` applies to all lookup types (name, account number, OU ID), not just name lookups.
- Scope lookup applies to both `--file` and `--csv` modes. CSV scopes can be full scope strings, account numbers, OU IDs, or names. Identical scope values in a CSV are resolved only once.
- `applyAtScope` applies to `disable` and `protect` only; it is ignored for `unprotect`.
- CSV header detection is automatic — the header row is optional.
- Use `--dryrun` to validate your input file and scopes before applying changes.
