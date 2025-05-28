This script is designed to migrate disabled or protected Cloud Permission Firewall controls between AWS accounts. It interacts with the Sonrai Security API to retrieve the control states from the source account and apply them to the target account.

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
python cpf-migrate-controls.py --source <source_account_id> --target <target_account_id> [--test]
```

#### Arguments
```
-s, --source: Required. AWS Account ID for the source account.

-t, --target: Required. AWS Account ID for the target account.

--test: Optional. A dry run flag to log actions without executing them.
```

## Example
#### Full execution:
```
python cpf-migrate-controls.py --source 123456789012 --target 987654321098
````
This will fetch the disabled and protected services from the source account and migrate them to the target account.

#### Dry run:
```
python cpf-migrate-controls.py --source 123456789012 --target 987654321098 --test
````
This will simulate the migration, logging the actions without performing them.

## Notes
The script retrieves the "scope" for the source and target AWS accounts before fetching the services.

The script handles both "disabled" and "protected" services and migrates them to the target account.
