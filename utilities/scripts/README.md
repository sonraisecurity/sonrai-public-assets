# Sonrai Scripts

Python scripts leveraging the Sonrai Python API Library.  

## Introduction

The scripts in this folder make use of the [sonrai_api](../sonrai_api/README.md) library, providing users with the ability to query the Sonrai GraphQL API. These scripts are built by the customer success team to make certain tasks easier and faster. Feel free to use these as samples of how to build your own Sonrai automation tools.

## Prerequisites

 * **Python 3**, as well as the *[sonrai_api](../sonrai_api/README.md)* library copied in as a sub-folder of the folder where the scripts are stored.
 * Install the (`sonrai_api/requirements.txt`) required libraries into your python environment.

## Scripts

- example.py - basic script showing how to use sonrai_api library
- [bulk-ticket-operations.py](bulk-ticket-operations_README.md) - script to perform bulk actions on Sonrai tickets
- [cpf-migrate-controls.py](cpf-migrate-controls_README.md) - script to migrate CPF controls from one AWS Account to another AWS Account
