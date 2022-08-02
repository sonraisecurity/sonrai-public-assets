# Change log

All notable changes will be documented in this file.

#### July 8, 2022 / mj
- added severity filters

#### Feb 2, 2022 / mj
- added -c for adding a comment
- added -u for user adding comment

#### Feb 2, 2021 / dwight
- added --printquery option
- added --all-swimlanes option, overriding -g, -s
- updated base sonrai.py library to use new sonrai tokens, no longer supports legacy API tokens.

#### Jan 11, 2021 / dwight
- added --testonly option
- added resourceSRN filter
- moved logging for cli parameters
- refactored/cleaned up graphql query variables for querying tickets
- fixed graphql filters - "startswith" switched to "neq null"
- maxticketsBulkClose added, increased from 20 to 50, though this might cause some errors with too many at once.
- added --maxclose-per-request option
- added getopts error output


#### Dec 22, 2020 / dwight
- refactored changes from NM around 'lastModified" filter 
- added -o -n (older/newer) that selected time, to allow for "older" or "newer" time cutoff
- refactored -i/-a inactive/active resource ticket closing
- added policy filter flag
- reformatted logging - thanks NM 
- renamed script to "closetickets.py"

#### Dec 19, 2020 - nm
- `CHANGELOG.md` (this file) in markdown
- `-i` to call and close tickets for inactive resources
- Feature to close tickets that have not been updated for last x number of hours, where x is the input provided with option `-t`
- `requirements.txt` to easily setup developer virtual environment
- Logging format in `logging.basicConfig`. Added the `format` to properly format the logging
- Removed manually entered function names from logging messages
- Updated `README.md` with markdown
- Renamed `closetickets_inactiveresources.py` to `sonrai_close_tickets.py` 
- Renamed `closetickets_inactiveresources.readme` to `README.md`
