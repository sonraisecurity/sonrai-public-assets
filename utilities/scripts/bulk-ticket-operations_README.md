# bulk-ticket-operations.py

Python script to make bulk actions against Sonrai tickets or findings.

## Introduction

The bulk-ticket-operations.py script allows you to add comments, change the status, assign or export tickets based on a search provided to the script.

## Prerequisites

- **sonrai_api** - folder in same directory as this script
- **Sonrai ticket query** - A query that is built in GraphQL format, built in Sonrai Advanced Search page
- **Python Library**:
  - **pandas** - library for converting to CSV format
    - Installation: `pip3 install pandas`

## Description

This script allows you to perform the following actions on Sonrai Findings:
- change the status of tickets and add a comment on tickets
  - close _(status = "CLOSED")_
  - re-open _(status = "NEW")_
  - risk accept _(status = "RISK_ACCEPTED")_
  - snooze _(status = "SNOOZED")_
- assign tickets to a Sonrai user
- export tickets to JSON

## Usage

Below is the **--help** output of the script and a table defining each available help option.

```
% python3 bulk-ticket-operations.py --help

usage: bulk-ticket-operations.py [-h] -f FILE [-m MESSAGE]
                                 [-a EMAIL] [-c] [-o] [-r] [-s TIME] [-e FILE]
```

| **option**        |                     | **description**                                                                                                                               |
|-------------------|---------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `-h`              | `--help`            | Provides the script's usage options                                                                                                           |
| **query options** |                     |                                                                                                                                               |
| `-f FILE`         | `--file FILE`       | Provide the GraphQL query in the file <FILE>. More details available [below](#Query-File-Format).                                             |
| `-l LIMIT`        | `--limit LIMIT`     | The ***LIMIT*** is the number of tickets to process with each call of the script. *Default LIMIT:* ***1000***                                 |
| **actions**       |                     |                                                                                                                                               |
| `-m MESSAGE`      | `--message MESSAGE` | When updating the status of a ticket, a comment it required. This flag is to add the comment/message.                                         |
| `-a EMAIL`        | `--assign EMAIL`    | Assign ticket(s) to user with *EMAIL* address                                                                                                 |
| `-c`              | `--close`           | Close ticket(s) returned from search                                                                                                          |
| `-o`              | `--open`            | Re-open ticket(s) returned from search                                                                                                        |
| `-r`              | `--risk_accept`     | Risk Accept ticket(s) returned from search                                                                                                    |
| `-s TIME`         | `--snooze TIME`     | Snooze ticket(s) returned from search for ***TIME*** days                                                                                     |
| `-e FILE`         | `--export FILE`     | Export ticket(s) returned from search in JSON format and save in *FILE*                                                                       |
|                   | `--csv`             | Used in conjunction with the `-e` option to export in CSV format                                                                              |
| | `--name_lookup`     | Used in conjunction with the `-e` option to do a Name lookup for Swimlane Name, Control Framework Name and Assignee Name                      |
| | `--list_comments`   | Used in conjunction with the `-e` option to do list all comments for a finding or ticket. _Note:_ This could add considerable processing time |


## Query File Format

If using the option of `-f` for the query, there are a few different things that need to be added to the query to make it work properly.

### Offset and Limit
The script is designed to query 1000 tickets at a time. To achieve this, your query needs to have the following lines for compatibility.

- **opening header**
  - `query ListFindings ($limit:Long $offset:Long) {`
- **items**
  - `items (limit:$limit offset:$offset) {`

### Count Values - totalCount / pageCount
The query uses the finding `pageCount` and `totalCount` values in the processing of searches over `--limit` results [both values need to be included in the search].

### Filters and Items
The filters added to the `where` clause and the fields added to the `items` sections of the query are all optional and can be defined as needed. (Example: 'where the SRN is ___', 'where the ticket status is `new`')

If you only want tickets and not findings you can add a line to the filter like this:
- `isOperationalized:{op:EQ value:true}`

*NOTE:* The more fields you add to the query, the larger the result set that is returned, and the longer the query will take to complete.

### Sample Queries

Here are a few sample queries that show the script usage:

#### Sample Query 1
```
query ListFindings ($limit:Long $offset:Long) {
  ListFindings(
    where: {
      frameworkSrns: {
        op:EQ 
        value:"srn:Sonrai::ControlFramework/b00cf230-8202-454d-85ea-4d471b166c44/17929365-ec04-456d-8431-c1006cd7e273"
      }
      status: {op:EQ value:"NEW"}
    }
  ) {
    pageCount
    totalCount
    items (limit:$limit offset:$offset) {
      title
      srn
      severityCategory
      policy {alertingLevelNumeric maturityLevel}
    }
  }
}
```
#### Sample Query 2
```
query ListFindings ($limit: Long, $offset: Long) { 
  ListFindings(
    where: {  
      assignee: {op:IN_LIST, values:["srn:myOrg::SonraiUser/1b7d8409-0162-45b3-8e66-1a6d2e60c222" ]
      } 
    }
  ) 
      { 
      pageCount 
      totalCount
      items (limit:$limit offset:$offset) {
        srn
        policy{alertingLevelNumeric}
        evidence { policyEvidence }
        resource{account}
        swimlanes{title}
        frameworkSrns
        assignee
      }
  }
}
 ```