# Bulk Service Action .py

Bulk applies a Sonrai Cloud Permission Firewall (CPF) service action — **disable**, **protect**, or **unprotect** — to a list of control keys at a specified scope. Reads control keys from a text file and calls the appropriate GraphQL mutation for each one.

## Prerequisites

- **Python 3** and the [sonrai_api](../sonrai_api/README.md) library copied into the same directory as the script.
- Install required libraries: `pip3 install -r sonrai_api/requirements.txt`
- Sonrai API credentials configured in `sonrai_api/config.json`.

## Usage

```
python bulk-service-action.py -a ACTION -f FILE -s SCOPE [--no-apply-at-scope] [-n]
```

### Arguments

| Flag | Long form | Required | Default | Description |
|------|-----------|----------|---------|-------------|
| `-a` | `--action` | Yes | — | Action to perform: `disable`, `protect`, or `unprotect` |
| `-f` | `--file` | Yes | — | Path to text file containing one control key per line |
| `-s` | `--scope` | Yes | — | Sonrai scope at which to apply the action |
| | `--apply-at-scope` / `--no-apply-at-scope` | No | `true` | Sets `applyAtScope` on disable/protect mutations. Not used for `unprotect`. |
| `-n` | `--dryrun` | No | `false` | Log what would be executed without running any mutations |

### Actions

| Action | Mutation | Description |
|--------|----------|-------------|
| `disable` | `DisableService` | Blocks the service at the specified scope |
| `protect` | `ProtectService` | Restricts the service at the specified scope |
| `unprotect` | `UnmanageService` | Removes any disable or protect from the specified scope |

### Input File Format

One control key per line. Blank lines are ignored.

```
guardduty
s3
ec2
athena
```

## Examples

**Disable** all services in a file at the root scope:
```bash
python bulk-service-action.py -a disable -f service_keys.txt -s aws/r-xxxx
```

**Protect** services at an OU scope:
```bash
python bulk-service-action.py -a protect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx
```

**Unprotect** services at an account scope:
```bash
python bulk-service-action.py -a unprotect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx/123456789012
```

Dry run to preview changes without applying anything:
```bash
python bulk-service-action.py -a disable -f service_keys.txt -s aws/r-xxxx --dryrun
```

Protect without applying at scope (`applyAtScope=false`):
```bash
python bulk-service-action.py -a protect -f service_keys.txt -s aws/r-xxxx/ou-xxxx-xxxxxxxxx --no-apply-at-scope
```

## Output

The script logs progress for each control key and prints a summary on completion:

```
INFO - Loaded 5 control key(s) from 'service_keys.txt'
INFO - Action: disable | Scope: aws/r-xxxx | applyAtScope=True | dryrun=False
INFO - [1/5] Processing 'guardduty'
INFO - [disable] 'guardduty' at scope 'aws/r-xxxx' — OK
...
INFO - Done. 5 succeeded, 0 failed out of 5 total.
```

If a mutation returns failures, each issue is logged with its account, scope, and message.

## Notes

- Large input files (350+ keys) are supported; each key is processed sequentially.
- The scope must be a valid Sonrai cloud hierarchy scope string. Scope values can be found in the Sonrai UI or via the `CloudHierarchyList` GraphQL query. Three scope levels are supported:
  - Root: `aws/r-xxxx`
  - OU: `aws/r-xxxx/ou-xxxx-xxxxxxxxx`
  - Account: `aws/r-xxxx/ou-xxxx-xxxxxxxxx/123456789012`
- `applyAtScope` applies to `disable` and `protect` only; it is ignored for `unprotect`.
- Use `--dryrun` to validate your input file and scope before applying changes.
