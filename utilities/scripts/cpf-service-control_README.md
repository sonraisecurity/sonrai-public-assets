# CPF Service Control Utility

This script automates Sonrai Cloud Permission Firewall (CPF) service control management across many AWS accounts. 

Use the CPF Service Control Utility to query service control keys and then check usage or apply actions (protect, disable, unprotect) for services at scale.

## Requirements

- The `sonrai_api` Python package
- Access to the Sonrai Security API and valid credentials to interact with it
- Necessary permissions to interact with AWS accounts for modifying Cloud Permission Firewall controls

## Usage

Find matching AWS control keys:
```bash
python3 cpf-service-control.py -q SEARCH_STRING
```

Display the current status for a specified service:
```bash
python3 cpf-service-control.py -k CONTROL_KEY -m MANAGEMENT_ID -l [-v] 
```

Apply or remove protections for a specified service:
```bash
python3 cpf-service-control.py -k CONTROL_KEY -m MANAGEMENT_ID ( -p | -d | -u ) ( -i  FILEPATH | -e FILEPATH ) [-n]
```

### Command-Line Options

| Flag                         | Description                                                    |
|------------------------------|----------------------------------------------------------------|
| `-q`, `--query`              | Search for service control keys that match a string            |
| `-k`, `--control-key`        | Specify the control key to act upon                            |
| `-p`, `--protect`            | Apply Protect action for a service                             |
| `-d`, `--disable`            | Apply Disable action for a service                             |
| `-u`, `--unprotect`          | Remove any Protect or Disable actions for a service            |
| `-m`, `--management-org`     | AWS management account ID                                      |
| `-i`, `--include-list`       | Full path to file with AWS account IDs to include              |
| `-e`, `--exclude-list`       | Full path to file with AWS account IDs to exclude              |
| `-l`, `--list-status`        | List the current status of the service across accounts         |
| `-v`, `--verbose`            | When listing status, show per-account detail in CSV format     |
| `-n`, `--dryrun`             | Simulate the action without applying changes                   |

## Sample Workflow

This workflow simulates looking for the SageMaker AWS service, checking the current status, and then protecting the service for all accounts *except* those in the list of provided AWS account IDs. 

1. Search for matching control keys for SageMaker

```bash
python3 cpf-service-control.py -q sage
```

Sample output:

```bash
Matching Control Keys:

CONTROL KEY                         | FRIENDLY NAME                                 | ACTIONS
----------------------------------------------------------------------------------------------------
ec2messages                         | Amazon Message Delivery Service               | Disable
sagemaker                           | Amazon SageMaker                              | Disable, Protect
sagemaker-data-science-assistant    | Amazon SageMaker data science assistant       | Disable
sagemaker-geospatial                | Amazon SageMaker Geospatial Capabilities      | Disable
sagemaker-mlflow                    | Amazon SageMaker with MLflow                  | Disable
ssmmessages                         | Amazon Message Gateway Service                | Disable
workmailmessageflow                 | Amazon WorkMail Message Flow                  | Disable
```

2. View the current protection status of the SageMaker service in your org
```bash
python3 cpf-service-control.py -k sagemaker -m 123456789012 -l
```

3. Perform a dry run, to simulate protecting SageMaker across a list of accounts in your org *without applying changes*

```bash
python3 cpf-service-control.py -k sagemaker -m 123456789012 -p -e /path/to/exclude.txt -n
```

4. Protect the SageMaker service across a list of accounts in your org
```bash
python3 cpf-service-control.py -k sagemaker -m 123456789012 -p -e /path/to/exclude.txt
```

5. View verbose status details of the SageMaker service in your org, with CSV output
```bash
python3 cpf-service-control.py -k sagemaker -m 123456789012 -l -v 
```

Although this example involves protecting a service, you would follow a similar workflow when disabling or unprotecting services.

## Notes

- 💡 **Important**: The `--dryrun` flag is highly recommended for validating your work before making changes.
- Actions require the `--management-org` flag for scope resolution.
- Only services that support the selected action (`Protect` or `Disable`) will be processed.
- You must specify either `--include-list` or `--exclude-list` for protect, disable, or unprotect actions.
- The expected file format when listing accounts to include/exclude is one account number per line. For example:
```
123456789012
234567890123
456789012345
```
