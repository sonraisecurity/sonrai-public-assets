import boto3
from botocore.exceptions import ClientError

# Constants for quota increase
SERVICE_CODE = 'iam'
QUOTA_CODES = ['L-0DA4ABF3']  # Quota codes for desired policies
DESIRED_QUOTA_VALUE = 20
ASSUME_ROLE_NAME = 'OrganizationAccountAccessRole'  # Default IAM role for AWS Organizations

def assume_role(account_id, role_name):
    """Assumes an IAM role in a member account and returns temporary credentials."""
    sts_client = boto3.client('sts')
    try:
        response = sts_client.assume_role(
            RoleArn=f'arn:aws:iam::{account_id}:role/{role_name}',
            RoleSessionName='QuotaIncreaseSession'
        )
        return response['Credentials']
    except ClientError as e:
        print(f"Could not assume role in account {account_id}: {e}")
        return None

def create_service_linked_role(credentials):
    """Creates the required service-linked role for Service Quotas."""
    iam_client = boto3.client(
        'iam',
        aws_access_key_id=credentials.get('AccessKeyId'),
        aws_secret_access_key=credentials.get('SecretAccessKey'),
        aws_session_token=credentials.get('SessionToken')
    )
    try:
        iam_client.create_service_linked_role(AWSServiceName='servicequotas.amazonaws.com')
        print("Service-linked role created successfully.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidInput':
            print("Service-linked role already exists.")
        else:
            print(f"Error creating service-linked role: {e}")

def get_current_quota(credentials, quota_code):
    """Retrieves the current value of the specified quota."""
    sq_client = boto3.client(
        'service-quotas',
        aws_access_key_id=credentials.get('AccessKeyId'),
        aws_secret_access_key=credentials.get('SecretAccessKey'),
        aws_session_token=credentials.get('SessionToken'),
        region_name='us-east-1'  # Service Quotas for IAM are only available in us-east-1
    )
    try:
        response = sq_client.get_service_quota(
            ServiceCode=SERVICE_CODE,
            QuotaCode=quota_code
        )
        return response['Quota']['Value']
    except ClientError as e:
        print(f"Error retrieving current quota for {quota_code}: {e}")
        return None

def request_quota_increase(credentials, quota_code):
    """Requests a quota increase for the specified quota."""
    sq_client = boto3.client(
        'service-quotas',
        aws_access_key_id=credentials.get('AccessKeyId'),
        aws_secret_access_key=credentials.get('SecretAccessKey'),
        aws_session_token=credentials.get('SessionToken'),
        region_name='us-east-1'  # Service Quotas for IAM are only available in us-east-1
    )
    try:
        response = sq_client.request_service_quota_increase(
            ServiceCode=SERVICE_CODE,
            QuotaCode=quota_code,
            DesiredValue=DESIRED_QUOTA_VALUE
        )
        print(f"Quota increase request submitted for {quota_code}: {response}")
    except ClientError as e:
        print(f"Error requesting quota increase for {quota_code}: {e}")

def process_account(account_id, local_credentials):
    """Processes quota increase requests for a given account."""
    if local_credentials:
        print(f"Processing management account: {account_id}")
        credentials = {}
    else:
        credentials = assume_role(account_id, ASSUME_ROLE_NAME)
        if not credentials:
            print(f"Skipping account {account_id} due to role assumption failure.")
            return

    # Create the service-linked role if needed
    create_service_linked_role(credentials)

    # Check current quota and request increase if needed
    for quota_code in QUOTA_CODES:
        current_value = get_current_quota(credentials, quota_code)
        if current_value is not None:
            if DESIRED_QUOTA_VALUE > current_value:
                print(f"Current value for {quota_code} is {current_value}. Requesting increase to {DESIRED_QUOTA_VALUE}.")
                request_quota_increase(credentials, quota_code)
            else:
                print(f"Current value for {quota_code} is {current_value}, which is greater than or equal to {DESIRED_QUOTA_VALUE}. Skipping.")
        else:
            print(f"Unable to retrieve current value for {quota_code}. Skipping.")

def get_all_accounts():
    """Uses a paginator to retrieve all accounts in the AWS Organization."""
    org_client = boto3.client('organizations')
    paginator = org_client.get_paginator('list_accounts')
    accounts = []
    try:
        for page in paginator.paginate():
            accounts.extend(page['Accounts'])
    except ClientError as e:
        print(f"Error retrieving accounts: {e}")
    return accounts

def main():
    try:
        # Retrieve all accounts in the organization
        accounts = get_all_accounts()
        current_account_id = boto3.client('sts').get_caller_identity()['Account']

        for account in accounts:
            account_id = account['Id']
            local_credentials = account_id == current_account_id  # Use local creds if management account
            process_account(account_id, local_credentials)

    except ClientError as e:
        print(f"Error listing accounts or processing request: {e}")

if __name__ == "__main__":
    main()

