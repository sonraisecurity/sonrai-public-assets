# PagerDuty On-Call Email Export

A small utility to fetch on-call user emails for a given PagerDuty schedule and write them to a text file, 
for use with the cpf approvers import script, "cpf-approvers.py"

## Config
Create a config file based on `pagerduty.json.sample`:

```json
{
	"api_key": "PAGERDUTY_API_TOKEN",
	"schedule_id": "PXXXXXXXX",
	"output_file": "cpf_frompagerduty_approversatscope.txt",
	"cpf_scope": "my_scope_value",
	"time_zone": "UTC",
	"loglevel": "INFO",
	"default_approvers": ["user1@example.com", "user2@example.com"]
}
```

- `api_key`: A REST API v2 token (use header `Authorization: Token token=<key>`)
- `schedule_id`: The PagerDuty schedule ID to query
- `output_file`: Path to write output line (default: `./cpf_frompagerduty_approversatscope.txt`)
- `time_zone`: Optional; defaults to `UTC`
- `cpf_scope`: Placed at start of the output line
- `loglevel`: Optional log level (DEBUG, INFO, WARNING, ERROR, CRITICAL); defaults to `INFO`
- `default_approvers`: Optional list of extra emails to include in the output

## Run
From the repo root or this folder:

```bash
python pagerduty-oncall-schedule-query.py --config pagerduty.json
```

The script calls the `GET /oncalls` endpoint with `include[]=users` and extracts emails for the specified schedule.

### Output format
One line CSV-like format:

```
<cpf_scope>,"email1@example.com,email2@example.com,..."
```

## Notes
- Handles pagination and 429 rate limits with Retry-After.
- Uses only Python standard library (no external dependencies).
