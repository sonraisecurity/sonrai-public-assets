# Sonrai API Python Client

Python client library and sample scripts to leverage the Sonrai GraphQL API.  

---

## Overview

This library (sonrai.py) provides users with the ability to query the Sonrai GraphQL API, using a variety of methods:

  * Execute a saved UI search
  * Parse and execute a GraphQL query file
  * Execute a raw GraphQL query passed via command line
  * Build logic to leverage the output of one query in another query

For more information on the GraphQL query format, please refer to the [Advanced Search documentation](https://docs.sonraisecurity.com/search/advanced-search/advanced-search-examples).

---

## Prerequisites

This script requires **Python 3**, as well as the *requests* and *pyjwt* libraries.  

The libraries can be installed using one of these two methods:  

  * Using requirements file: `pip3 install -r requirements.txt`    
  * Manually: `pip3 install requests pyjwt`  

---

### Environment Variables

| Env Variable    | Description |
| ----------- | ----------- |
| TOKEN |  Authentication token for the GraphQL server    |
| TOKENSTORE     |  Directory in which to store the refreshed auth token    |
| TOKENFILE     |  Filename to use to store the refreshed auth token    |
| SONRAI_DEBUG     |  Set to True if you would like debugging messages    |

---

## Usage

This Python library can be imported into other scripts.

```from sonrai import SonraiApi```

### CLI

For reference, sonraiquery.py is included as a reference on how to use the library. 

Instructions for sonraiquery.py:

```
 Usage:  
   ./sonraiquery.py [--debug] [--query NAME] [--file FILENAME] [--vars {VARS}]
   ./sonraiquery.py --help

 Options:
   -h, --help                  Show this message.
   -d, --debug                 Enable debugging.
   -b, --blob                  Print the output in raw format (DEFAULT)
   -l, --linebyline            Print each json data.items entry on it's own line.
   -q <name>, --query <name>   Execute the saved query named <name>.
   -f <file>, --file <file>    Execute the query contained in <file>.
   -n <queryName>, --name <queryName>    Provide a query name of <queryName>.
   -v <vars>, --vars <vars>    Use the JSON string passed as <vars> as the GraphQL query variables.
                               Typically used with -f/--file when that GraphQL query requires variables.

 Environment variables:
   TOKEN                   Sonrai API auth token
   LOGLEVEL                ERROR, INFO, DEBUG - INFO is enabled by default
```

#### Execute a Saved UI Search

Use the `-q/--query` command line argument and pass the name of the saved UI search.

```json
./sonraiquery.py --query "Accounts - Observed" -l
{
    "ExecuteSavedQuery": {
        "Query": {
            "Accounts": {
                "count": 15,
                "items": [
                    {
                        "account": "XXXXXXXX",
                        "active": null,
                        ...
                    }
                ]
            }
        }
    }
}
```

#### Parse and Execute a GraphQL Query File

Use the `-f/--file` and `-v/--vars` command line arguments to pass in the GraphQL query filename and the variable JSON array respectively.  

```json
./sonraiquery.py --file queries/actions-by-user.graphql --vars '{"username":"andrew"}' -l
{
    "Users": {
        "aggregation": {
            "performed": {
                "count": 2,
                "items": [
                    {
                        "accessKey": null,
                        "account": "XXXXXXXX",
                        ...
                    }
                ]
            }
        }
    }
}
```

### Import Module in Python Scripts

Any Python script will first need to import the module and instantiate the class:

```python
from sonraiapi import SonraiApi
sonrai = SonraiApi(queryName, savedQueryName, queryFileName, queryVariables, outputMode)
results = sonrai.executeQuery()
```

| Field Name | Description
| ------| -----
| queryName | A name value that can be passed to Sonrai (has no affect on the search)
| savedQueryName | Name of a saved search on the Sonrai Platform that can be run directly from the API
| queryFileName | Name of a file containing an Advanced Sonrai Search
| queryVariables | JSON containing the variables to be passed the Advanced Search
| outputMode | Format the output will be displayed in for the search (Default: **blob**)

`None` is an acceptable value to pass for any of these fields.

#### Execute Raw GraphQL

You can instantiate without any initial values and execute a query directly by passing your GraphQL to the `sonrai.executeQuery()` function.

```python
from sonraiapi import SonraiApi
sonrai = SonraiApi()
sonrai.executeQuery("query pivotedQuery { Accounts { count } }")
```

#### Parse and Execute a GraphQL Query File

Use the `sonrai.parseQueryFile()` function to load a local GraphQL query file. Be sure to build a JSON object with variables, if those are required for your query. Then pass the query and the variables to `sonrai.executeQuery()`.

```python
q = sonrai.parseQueryFile("queries/crm-can-access-resource.graphql")
v = {"fromDate": fromDate, "toDate": toDate, "criticalResourceSRN": criticalResourceSRN}
sonrai.executeQuery(q, v)
```
