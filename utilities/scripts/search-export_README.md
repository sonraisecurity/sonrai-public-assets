# search-export.py

Python script to export a GraphQL query

## Introduction

The `search-export.py` script enables you to run a GraphQL query using paging to return and export *all* query results in JSON format.

## Prerequisites

- **sonrai_api** - The `sonrai_api` folder and this script must be in the same directory together
- **Sonrai query** - A query that is either built in GraphQL format or built using the Sonrai Advanced Search page

## Description

By default most Sonrai GraphQL queries are limited to return a limited number of results. This script allows the query to be run and gather all results that match the search, by paging through all the results.

## Usage

Below is the **--help** output of the script and a table defining each available help option.

```
% python3 search-export.py --help

usage: search-export.py [-h] -q QUERY [-l LIMIT] -f FILE
```

| **option**        |                     | **description**                                                                                                                                                    |
|-------------------|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `-h`              | `--help`            | Provides the script's usage options                                                                                                                                |
| **query options** |                     |                                                                                                                                                                    |
| `-q FILE`         | `--query FILE`      | Provide the GraphQL query in the file <FILE>. More details available [below](#Query-File-Format).                                                                  |
| `-l LIMIT`        | `--limit LIMIT`     | The ***LIMIT*** is the number of tickets to process with each call of the script. *Default LIMIT:* ***1000***                                                      |
| `-f FILE`         | `--file FILE`       | Export results to <FILE> in JSON format |

## Query File Format

If using the option of `-q` for the query, there are a few different command arguments that need to be added to the query for it work properly.

### Offset and Limit
The script is designed to query 1000 tickets at a time. To accomplish this, your query needs to have the following lines for compatibility.

- **opening header**
  - `query searchName ($limit:Long $offset:Long) {`
- **items**
  - `items (limit:$limit offset:$offset) {`

### Count Values 
The query uses the `count` field to know when the query is complete if the total exceeds the `--limit` value. 

### Filters and Items
The filters added to the `where` clause and the fields added to the `items` sections of the query are all optional and can be defined as needed. 

*NOTE:* The more fields you add to the query, the larger the results set that is returned, and the longer the query will take to complete! It might be necessary to drop the value of the `--limit` to make these queries work.

### Query Example

Here is an example query that shows the script usage:

#### Query Example
```
query queryUsers($limit: Int, $offset: Int) {
  Users(
    where: { active: { op: EQ, value: true }  }
  ) {
    count
    items(limit: $limit, offset: $offset) {
      name
      userName
      type
      label
      isConsoleEnabled
      active
      account
      createdDate
      srn
    }
  }
}
```
