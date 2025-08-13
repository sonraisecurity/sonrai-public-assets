This script is designed to migrate disabled or protected Cloud Permission Firewall controls between AWS accounts. It interacts with the Sonrai Security API to retrieve the control states from the source account and apply them to one or more target accounts.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Usage](#usage)
- [Arguments](#arguments)
- [Example](#example)
- [Notes](#notes)


## Prerequisites

Before using this script, ensure that you have:

- Python 3.x installed.
- Access to the Sonrai Security API and valid credentials to interact with it.
- Necessary permissions to interact with AWS accounts for modifying Cloud Permission Firewall controls.

## Usage

The script can be used to migrate controls (disabled or protected) from one AWS account to another. It is designed to support both real execution and dry runs for testing purposes.

```
python bulk_ticket_operations.py --source SOURCE  (-t TARGET | --target-file TARGET_FILE) [--test]
```

#### Arguments
| Argument           | Description                                                                                                          |
| ------------------ |----------------------------------------------------------------------------------------------------------------------|
| `--source` or `-s` | **(Required)** Source AWS Account ID                                                                                 |
| `--target` or `-t` | **(Mutually exclusive with ****\`target_file\`****)** Single AWS Account ID to target                                |
| `--target-file`    | **(Mutually exclusive with ****`target`****)** Path to file containing a list of target account IDs (one per line) |
| `--test`           | (Optional) If set, performs a dry-run without executing actions                                                      |

### **Requirements**

- You must provide **either** `--target` **or** `--target-file`, but **not both**.
- The `--source` argument is always required.


## Example
### Migrate to a single target account

```bash
python cpf-migrate-controls.py \
  --source 111122223333 \
  --target 444455556666
```

### Migrate to multiple target accounts from a file

```bash
python cpf-migrate-controls.py \
  --source 111122223333 \
  --target-file targets.txt
```

Contents of `targets.txt`:

```
444455556666
555566667777
666677778888
```

### Test mode (dry run)

```bash
python cpf-migrate-controls.py \
  --source 111122223333 \
  --target 444455556666 \
  --test
```
This will simulate the migration, logging the actions without performing them.

## Notes
- The script retrieves the "scope" for the source and target AWS accounts before fetching the services.
- The script handles both "disabled" and "protected" services and migrates them to the target account.
- After migration, any service controls in the target account that also exist in the source account will be overwritten by the source account's state. Service controls that exist only in the target account will remain unchanged.
- Any identities exempted for a service in the source account will ***NOT*** be copied to the target account.
