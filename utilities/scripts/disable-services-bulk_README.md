# disable-services-bulk.py

Bulk disables Sonrai Cloud Permission Firewall (CPF) services by control key at a specified scope. Reads a list of control keys from a text file and calls the `DisableService` mutation for each one.

## Prerequisites

- **Python 3** and the [sonrai_api](../sonrai_api/README.md) library copied into the same directory as the script.
- Install required libraries: `pip3 install -r sonrai_api/requirements.txt`
- Sonrai API credentials configured in `sonrai_api/config.json`.

## Usage

```
python disable-services-bulk.py -f FILE -s SCOPE [--no-apply-at-scope] [-n]
```

### Arguments

| Flag | Long form | Required | Default | Description |
|------|-----------|----------|---------|-------------|
| `-f` | `--file` | Yes | — | Path to text file containing one control key per line |
| `-s` | `--scope` | Yes | — | Sonrai scope at which to disable each service (e.g. `aws/r-bitm`) |
| | `--apply-at-scope` / `--no-apply-at-scope` | No | `true` | Sets `applyAtScope` on the `DisableService` mutation |
| `-n` | `--dryrun` | No | `false` | Log what would be disabled without executing any mutations |

### Input File Format

One control key per line. Blank lines are ignored.

```
guardduty
s3
ec2
athena
```

## Examples

Disable all services listed in a file at a given scope:
```bash
python disable-services-bulk.py -f service_keys.txt -s aws/r-bitm
```

Preview what would be disabled without making any changes:
```bash
python disable-services-bulk.py -f service_keys.txt -s aws/r-bitm --dryrun
```

Disable with `applyAtScope` set to false:
```bash
python disable-services-bulk.py -f service_keys.txt -s aws/r-bitm --no-apply-at-scope
```

## Output

The script logs progress for each control key and prints a summary on completion:

```
INFO - Loaded 5 control key(s) from 'service_keys.txt'
INFO - Target scope: aws/r-bitm | applyAtScope=True | dryrun=False
INFO - [1/5] Processing 'guardduty'
INFO - Disabled 'guardduty' at scope 'aws/r-bitm'
...
INFO - Done. 5 succeeded, 0 failed out of 5 total.
```

If a mutation returns failures, each issue is logged with its account, scope, and message.

## Notes

- Large input files (350+ keys) are supported; each key is processed sequentially.
- The scope must be a valid Sonrai cloud hierarchy scope string. You can find scope values in the Sonrai UI or via the `CloudHierarchyList` GraphQL query.
- Use `--dryrun` to validate your input file and scope before applying changes.
