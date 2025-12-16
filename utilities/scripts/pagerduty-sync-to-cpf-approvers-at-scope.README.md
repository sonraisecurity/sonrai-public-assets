# PagerDuty Sync to CPF Approvers at Scope

## Overview

This script uses 2 component scripts to automate the synchronization of PagerDuty on-call schedules to CPF (Cloud Platform Framework) approver assignments at a specific scope. It runs two sequential operations:

1. Fetches on-call user emails from a PagerDuty schedule using `pagerduty-oncall-schedule-query.py`
2. If step 1 succeeds, imports those emails as approvers in CPF at a specified scope using `cpf-approvers.py`

## Prerequisites

- Python 3.7+
- `pagerduty-oncall-schedule-query.py` script & configuration file
- `cpf-approvers.py` script
- `sonrai_api/*` python library
- PagerDuty API key and configuration
- Sonrai API token

## Usage

```bash
python pagerduty-sync-to-cpf-approvers-at-scope.py
```

## Configuration & Setup

To use this script, 

- download copies of scripts to /opt/cpf/ (or elsewhere)
	- [`sonrai_api/*`](https://github.com/sonraisecurity/sonrai-public-assets/tree/main/utilities/sonrai_api) (and place in sonrai_api directory)
	- [`pagerduty-oncall-schedule-query.py`](https://github.com/sonraisecurity/sonrai-public-assets/tree/main/utilities/scripts/pagerduty-oncall-schedule-query.py)
	- [`pagerduty-sync-to-cpf-approvers-at-scope.py`](https://github.com/sonraisecurity/sonrai-public-assets/tree/main/utilities/scripts/pagerduty-sync-to-cpf-approvers-at-scope.py)
	- [`pagerduty.json.sample`](https://github.com/sonraisecurity/sonrai-public-assets/tree/main/utilities/scripts/pagerduty.json.sample)
	- [`cpf-approvers.py`](https://github.com/sonraisecurity/sonrai-public-assets/tree/main/utilities/scripts/cpf-approvers.py)

- edit `pagerduty-sync-to-cpf-approvers-at-scope.py` and update the `CPF_PATH` variable
- rename `pagerduty.json.sample` to `pagerduty.json` and update `api_key`, `schedule_id`, `output_file` , `cpf_scope` & `default_approvers`
- update `sonrai_api/config.json` 
	- update the path to `token_store` path for the Sonrai Token location (ie, `/opt/cpf/`)
	- update the `token_length_secs` and `token_refresh_threshold_secs` values to align with your schedule, so that the "length" is longer than your time period.  Suggestions would be:  Hourly: 5400 (90 minutes) / Daily: 100800 (28h) / Weekly: 691,200 (8 days)


*pagerduty.json configuration options:*

| Option | Required | Description |
|--------|----------|-------------|
| `api_key` | Yes | PagerDuty REST API v2 token |
| `schedule_id` | Yes | PagerDuty schedule ID to query |
| `output_file` | Yes | Path where to write the output file, default: `cpf_frompagerduty_approversatscope.txt`) |
| `cpf_scope` | Yes | CPF scope value to associate with approvers, ie, `aws/r-bitf/ou-bitf-w42d5lr0`|
| `time_zone` | No | Timezone for PagerDuty queries (default: UTC) |
| `loglevel` | No | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO) |
| `default_approvers` | No | Comma-separated list of additional email addresses to include |




## How It Works


After making your changes above, run the script `pagerduty-sync-to-cpf-approvers-at-scope.py`, which calls

```bash
pagerduty-oncall-schedule-query.py --config pagerduty.json
```
This command:
- Connects to PagerDuty API using the provided credentials
- Queries the specified schedule for current on-call users
- Fetches their email addresses
- Combines them with any default approvers from the config
- Writes the result to the output file in the format: `scope,"email1,email2,email3"`

If the call to Pagerduty succeeds, `pagerduty-sync-to-cpf-approvers-at-scope.py` then calls:

```bash
cpf-approvers.py --import --file /opt/cpf/cpf_frompagerduty_approversatscope.txt
```

This command:
- Reads the email list from the output file
- Imports the users as approvers in CPF at the specified scope
- Any users **not already** configured in CPF are sent invitations, as approvers at the specified scope

## Sample output
```bash
(python313) dwight@DwightSpencer-MBP-5M64 cpf % python3.13 pagerduty-sync-to-cpf-approvers-at-scope.py
Running: /opt/cpf/pagerduty-oncall-schedule-query.py --config /opt/cpf/pagerduty.cfg
[2025-12-15 17:11:24] [INFO] - Fetching on-call emails for schedule: P3TPKPG
[2025-12-15 17:11:24] [INFO] - Fetched 1 unique email(s)
[2025-12-15 17:11:24] [INFO] - Added 1 default approver(s)
[2025-12-15 17:11:24] [INFO] - Successfully wrote output to /opt/cpf/cpf_frompagerduty_approversatscope.txt
[2025-12-15 17:11:24] [INFO] - Wrote scope and 2 email(s) to /opt/cpf/cpf_frompagerduty_approversatscope.txt
Running: /opt/cpf/cpf-approvers.py --import --file /opt/cpf/cpf_frompagerduty_approversatscope.txt
[2025-12-15 17:11:26] [INFO] - Importing owners from /opt/cpf/cpf_frompagerduty_approversatscope.txt (dry run: False)
[2025-12-15 17:11:26] [INFO] - Fetching existing Sonrai users
[2025-12-15 17:11:26] [INFO] - Need to create 0 users
[2025-12-15 17:11:26] [INFO] - Successfully assigned owners ['dwight@sonrai.com', 'michael@sonrai.com'] to aws/r-bitf/ou-bitf-w42d5lr0
(python313) dwight@DwightSpencer-MBP-5M64 cpf %

```

## Error Handling

- The script exits immediately with the error code from `pagerduty-oncall-schedule-query.py` if it fails
- Only proceeds to the CPF import step if the PagerDuty query succeeds
- All commands are echoed to stdout before execution for visibility

## Exit Codes

- `0`: Both commands succeeded
- Non-zero: Error occurred (either in PagerDuty query or CPF import)

## Logging

Output includes:
- Each command being executed (with proper quoting for shell safety)
- Standard output/error from both called scripts
- Exit codes for debugging

## Advanced Features

### Default Approvers

The `default_approvers` config option allows you to specify additional email addresses that should always be included as approvers, regardless of the current PagerDuty schedule. These are merged with the on-call emails, with automatic deduplication.

Example:
```json
{
  "default_approvers": ["ops-lead@example.com", "escalation@example.com"]
}
```

## Troubleshooting

**Issue**: "api_key is required in config"
- Verify your PagerDuty API token is set in the config file

**Issue**: "schedule_id is required in config"
- Verify the PagerDuty schedule ID is correctly set

**Issue**: Script fails at CPF import step
- Check that the output file was created by the PagerDuty query
- Verify CPF credentials and network connectivity
- Ensure the CPF scope is valid

