# CPF Approvers

This utility script enables Sonrai Security users to export and import scope owners (approvers) for cloud environments using the `sonrai_api` library and GraphQL.

## Features

- Export a CSV file of all scopes and their owners for a given cloud type and management account.
- Import a CSV file of scope owners to assign users as scope owners.
- Automatically creates missing users in CPF during import.
- Existing scope owners are not removed during import.
- Dry Run mode for safe testing of import actions.
- Uses Sonrai's GraphQL API via the `sonrai_api` library.

## Requirements

- Python 3.7+
- `sonrai_api` library (must be installed and authenticated)

## Usage

```bash
python cpf-approvers.py --export --file output.csv --management-account-id 123456789012
```

```bash
python cpf-approvers.py --import --file input.csv --dry-run
```

```bash
python cpf-approvers.py --import --file input.csv
```

### Options

| Flag                        | Description                                                                 |
|----------------------------|-----------------------------------------------------------------------------|
| `-e`, `--export`           | Export mode                                                                 |
| `-i`, `--import`           | Import mode                                                                 |
| `--file`                   | Input (for import) or output (for export) CSV file                          |
| `-m`, `--management-account-id` | Required in export. The AWS management account ID                         |
| `--dry-run`                | Optional. Simulate import without making changes                            |
<!---
commenting out this line until we have multiple clouds supported
| `-c`, `--cloud-type`       | Required in export. Cloud type: `aws`, `azure`, or `gcp`                    |
-->

## CSV Format

### Exported CSV Example

```csv
scope,scopeFriendlyName,entryType,resourceId,owners
aws/r-xxxx/ou-xxxx-xxxx/123456789012,Account A,account,123456789012,"user1@domain.com,user2@domain.com"
```

### Input CSV for Import

- optional headers: `scope`, `owners` (Additional columns, if present, are ignored).
- Multiple owners should be comma-separated within the `owners` column and have double-quotes to start and end the field
