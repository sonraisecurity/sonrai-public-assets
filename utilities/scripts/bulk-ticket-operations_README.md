# bulk-ticket-operations.py

Python script to make bulk actions against Sonrai tickets.

## Introduction

The bulk-ticket-operations.py script allows you to add comments, change the status, assign or export tickets based on a search provided to the script.

## Prerequisites

- **sonrai_api** - folder in same directory as this script
- **Sonrai ticket query** - A query that is either built in GraphQL format, built in Sonrai Advanced Search page, or built using the user interface's ticket screen to build a query and then use the URL field as the basis of the query.

## Description

This script allows you to perform the following actions on Sonrai Tickets:
- add a comment on tickets
- change the status of tickets
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

usage: bulk-ticket-operations.py [-h] (-f FILE | -u URL) [-m MESSAGE]
                                 [-a EMAIL] [-c] [-o] [-r] [-s TIME] [-e FILE]
```

| **option**        |                     | **description**                                                                                                                                                |
|-------------------|---------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `-h`              | `--help`            | Provides the script's usage options                                                                                                                            |
| **query options** |                     |                                                                                                                                                                |
| `-f FILE`         | `--file FILE`       | Provide the GraphQL query in the file <FILE>. More details available [below](#Query-File-Format).                                                              |
| `-u URL`          | `--URL URL`         | The *URL* from the UI's ticket screen, which includes all the necessary filters. More details available [below](#Query-URL). [_Note: Must be a quoted string_] |
| **actions**       |                     |                                                                                                                                                                |
| `-m MESSAGE`      | `--message MESSAGE` | Add a *MESSAGE* or comment to the ticket(s) matching the query. Must be a quoted string. ***NOTE:*** Comments are required for all actions except `--export`   |
| `-a EMAIL`        | `--assign EMAIL`    | Assign ticket(s) to user with *EMAIL* address                                                                                                                  |
| `-c`              | `--close`           | Close ticket(s) returned from search                                                                                                                           |
| `-o`              | `--open`            | Re-open ticket(s) returned from search                                                                                                                         |
| `-r`              | `--risk_accept`     | Risk Accept ticket(s) returned from search                                                                                                                     |
| `-s TIME`         | `--snooze TIME`     | Snooze ticket(s) returned from search for *TIME* days                                                                                                          |
| `-e FILE`         | `--export FILE`     | Export ticket(s) returned from search in JSON format and save in *FILE*                                                                                        |


## Query File Format

If using the option of `-f` for the query, there are a few different things that need to be added to the query to make it work properly.

### Offset and Limit
The script is designed to query 1000 tickets at a time. To accomplish this, your query needs to have the following lines for compatibility.

- **opening header**
  - `query Ticket ($limit:Long $offset:Long) {`
- **items**
  - `items (limit:$limit offset:$offset) {`

### Count Values - count / globalCount
The query uses the ticket `count` and `globalCount` values in the processing of searches over 1000 results [both values need to be included in the search].

### Filters and Items
The filters added to the `where` clause and the fields added to the `items` sections of the query are all optional and can be defined as needed. (Example: 'where the SRN is ___', 'where the ticket status is `new`')

*NOTE:* The more fields you add to the query, the larger the results set that is returned, and the longer the query will take to complete.

### Sample Queries

Here are a few sample queries that show the script usage:

#### Sample Query 1
```
query Ticket ($limit:Long $offset:Long) {
  Tickets(
    where: {
      controlFrameworkSrn: {op:EQ value:"srn:Sonrai::ControlFramework/b00cf230-8202-454d-85ea-4d471b166c44/17929365-ec04-456d-8431-c1006cd7e273"}
      status: {op:EQ value:"NEW"}
    }
  ) {
    globalCount
    count
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
query Tickets ($limit: Long, $offset: Long) { 
  Tickets(
    where: {  
      assignedTo: {op:IN_LIST, values:["srn:myOrg::SonraiUser/1b7d8409-0162-45b3-8e66-1a6d2e60c222" ]
      } 
    }
  ) 
      { 
      globalCount 
      count
      items (limit:$limit offset:$offset) {
        srn
        policy{alertingLevelNumeric}
        evidence { policyEvidence }
        resource{account}
        swimlanes{title}
      }
  }
}
 ```

## Query URL

If using the option of `-u` for the query, navigate to the ticket screen (https://app.sonraisecurity.com/App/SecurityCenter/Tickets) and build a filter using the different options available. Once the desired filter is complete, copy the URL from the browser's address bar and use that value with the script. Here is an example of what the URL could look like:

https://app.sonraisecurity.com/App/SecurityCenter/Tickets?cloudType=aws&dateType=lastSeen&endDate=2023-04-06&maturityLevel=1&severityCategory=CRITICAL&startDate=2023-04-01&status=NEW&ticketType=Policy

_Reminder_: The URL value needs to be quoted on the command line to handle the special characters present in the URL that command line interprets differently.
