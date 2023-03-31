# bulk-ticket-operations.py

Python script to make bulk actions against Sonrai tickets

## Introduction

The bulk-ticket-operations.py script allows you to add comments, change the status, assign or export tickets based on a search provided to the script.

## Prerequisites

- **sonrai_api** - folder in same directory as this script
- **Sonrai ticket query** - A query that is either built in graphQL format, built in Sonrai Advanced Search page or built using user interface's ticket screen to build a query and then use the URL field as the bases of the query.

## Description

This script allows you to perform the following actions on Sonrai Tickets:
- add a comment on tickets
- change status of tickets
  - close _(status = "CLOSED")_
  - re-open _(status = "NEW")_
  - risk accept _(status = "RISK_ACCEPTED")_
  - snooze _(status = "SNOOZED")_
- assign tickets to a Sonrai user
- export tickets to JSON

## Usage

This is the **--help** output of the script and below is a table defining each option.

```
% python3 bulk-ticket-operations.py --help

usage: bulk-ticket-operations.py [-h] (-f FILE | -u URL) [-m MESSAGE]
                                 [-a EMAIL] [-c] [-o] [-r] [-s TIME] [-e FILE]
```

| **option**        |                     | **description**                                                                                                                                              |
|-------------------|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `-h`              | `--help`            | provide the scripts usage                                                                                                                                    |
| **query options** |                     |                                                                                                                                                              |
| `-f FILE`         | `--file FILE`       | Provide the graphQL query in the file <FILE>                                                                                                                 |
| `-u URL`          | `--URL URL`         | UI *URL* to ticket screen with the query to run. Must be a quoted string                                                                                     |
| **actions**       |                     |                                                                                                                                                              |
| `-m MESSAGE`      | `--message MESSAGE` | Add a *MESSAGE* or comment to the ticket(s) matching the query. Must be a quoted string. ***NOTE:*** Comments are required for all actions except `--export` |
| `-a EMAIL`        | `--assign EMAIL`    | Assign ticket(s) to user with *EMAIL* address                                                                                                                |
| `-c`              | `--close`           | Close ticket(s) returned from search                                                                                                                         |
| `-o`              | `--open`            | Re-Open ticket(s) returned from search                                                                                                                       |
| `-r`              | `--risk_accept`     | Risk Accept ticket(s) returned from search                                                                                                                   |
| `-s TIME`         | `--snooze TIME`     | Snooze ticket(s) returned from search for *TIME* days                                                                                                        |
| `-e FILE`         | `--export FILE`     | Export ticket(s) returned from search in JSON format and save in *FILE*                                                                                      |