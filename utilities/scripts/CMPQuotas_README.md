# CMPQuotas.py

Python script to automate AWS IAM quota increases across AWS Organization accounts using AWS CloudShell.

## Introduction

Sonrai has created a Python script to automate Cloud Permission Firewall (CPF) quota increases for existing accounts. Most customers require no configuration or modification to run this script. Simply log in to your AWS Management Console using an administrative account, and run the script using AWS CloudShell.

## Prerequisites

- AWS Management Console access with administrative privileges
- AWS CloudShell available in your AWS region
- The default IAM role for AWS Organizations (`OrganizationAccountAccessRole`) must exist in your organization

> **Note:** If your organization does not use `OrganizationAccountAccessRole`, or if you use a different role to provision and manage accounts, see the Configuration section below.

## Running the CMPQuotas Python Script

1. **Save a copy** of the `CMPQuotas.py` script locally.
2. **Open AWS CloudShell** in your AWS Console by clicking the CloudShell icon (top-right toolbar).
3. **Upload the script** using the Actions → Upload file menu.
4. **Run the script:**
   ```bash
   python3 CMPQuotas.py
   ```

## Configuration

Most customers can run this script without any modifications. However, if your organization uses a different IAM role name for account management, you may need to modify one line before running:

```python
ASSUME_ROLE_NAME = 'OrganizationAccountAccessRole'
```

Change `'OrganizationAccountAccessRole'` to whatever role name your organization uses to provision and manage accounts.

## Expected Output

The script will automatically discover all accounts in your AWS Organization and submit quota increase requests. Expected output should look similar to:

```
$ python3 CMPQuotas.py
Service-linked role created successfully.
Current value for L-12345678 is 10.0. Requesting increase to 25.
Quota increase request submitted for L-12345678: {'RequestedQuota': {'Id': 'e012345678901234567890123456789012345678', 'ServiceCode': 'iam', 'ServiceName': 'AWS Identity and Access Management (IAM)', 'QuotaCode': 'L-12345678', 'QuotaName': 'Managed policies per role', 'DesiredValue': 25.0, 'Status': 'PENDING', 'Created': datetime.datetime(2025, 8, 29, 17, 40, 1, 956000, tzinfo=tzlocal()), 'Requester': '{"accountId":"123456789012","callerArn":"arn:aws:sts::123456789012:assumed-role/OrganizationAccountAccessRole/QuotaIncreaseSession"}', 'QuotaArn': 'arn:aws:servicequotas::123456789012:iam/L-12345678', 'GlobalQuota': True, 'Unit': 'None', 'QuotaRequestedAtLevel': 'ACCOUNT', 'QuotaContext': {'ContextScope': 'RESOURCE', 'ContextScopeType': 'AWS::IAM::Role', 'ContextId': '*'}}, 'ResponseMetadata': {'RequestId': 'abc123de-f456-ghi7-89ab-c012-def345g', 'HTTPStatusCode': 200, 'HTTPHeaders': {'date': 'Fri, 29 Aug 2025 17:40:00 GMT', 'content-type': 'application/x-amz-json-1.1', 'content-length': '657', 'connection': 'keep-alive', 'x-amzn-requestid': 'abc123de-f456-ghi7-89ab-c012-def345g'}, 'RetryAttempts': 0}}
...
```

The script will process each account in your organization and submit quota increase requests as needed. The `Status: 'PENDING'` indicates the request has been successfully submitted.
