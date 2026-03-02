# Sonrai Scripts

Python scripts leveraging the Sonrai Python API Library.  

## Introduction

The scripts in this folder make use of the [sonrai_api](../sonrai_api/README.md) library, providing users with the ability to query the Sonrai GraphQL API. These scripts are built by the customer success team to make certain tasks easier and faster. Feel free to use these as samples of how to build your own Sonrai automation tools.

## Prerequisites

 * **Python 3**, as well as the *[sonrai_api](../sonrai_api/README.md)* library copied in as a sub-folder of the folder where the scripts are stored.
 * Install the (`sonrai_api/requirements.txt`) required libraries into your python environment.

## Scripts

### Cloud Permission Firewall (CPF) Management  
- [cpf-approvers.py](cpf-approvers_README.md) - Export and import scope owners (approvers) for cloud environments
- [cpf-invite-sonrai-users.py](cpf-invite-sonrai-users_README.md) - Generate Sonrai user invite GraphQL mutations from a CSV file
- [cpf-migrate-controls.py](cpf-migrate-controls_README.md) - Migrate disabled or protected CPF controls between AWS accounts
- [cpf-service-control.py](cpf-service-control_README.md) - Automate Cloud Permission Firewall service control management across AWS accounts

### Sonrai CIEM Platform
- [bulk-ticket-operations.py](bulk-ticket-operations_README.md) - Perform bulk actions on Sonrai tickets (close, reopen, risk accept, snooze, assign, export)
- [swimlane-maintenance.py](swimlane-maintenance_README.md) - Create and update Sonrai swimlanes based on cloud resource tags

### PagerDuty Integration
- [pagerduty-oncall-schedule-query.py](pagerduty-oncall-schedule-query.README.md) - Fetch on-call user emails from a PagerDuty schedule
- [pagerduty-sync-to-cpf-approvers-at-scope.py](pagerduty-sync-to-cpf-approvers-at-scope.README.md) - Automate synchronization of PagerDuty on-call schedules to CPF approver assignments

### Search & Export
- [search-export.py](search-export_README.md) - Export GraphQL query results to JSON format with automatic paging

### Utilities
- [CMPQuotas.py](CMPQuotas_README.md) - Automate AWS IAM quota increases across AWS Organization accounts
- example.py - Basic script showing how to use the sonrai_api library