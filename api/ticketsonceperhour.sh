#!/bin/bash
# script to run a "tickets" query to Sonrai using the 
# sonraicrc-api.py & sonraiapi.py scripts, along with 
# grqphql query file for tickets.
# passes in a variable for the time filter to go back to
#
SECONDSBACK=36000
CURRENTTIME=`date +%s`
FROMTIME=$(expr $CURRENTTIME - $SECONDSBACK)

./sonraiquery.py -l -f queries/tickets.graphql -v "{\"from\": $FROMTIME }"