# PoD Pipeline Latency Probe

This utility reports the average latency of the two Permission-on-Demand (PoD) pipeline
hops that sit outside Sonrai's control, so you can track them in your own monitoring or
dashboard system.

| Measurement | From | To | Owned by |
|---|---|---|---|
| `cloudtrail_eventbridge` | CloudTrail `eventTime` | EventBridge `ingestionTime` | AWS |
| `sonrai_to_chatops` | PoD request created | first approval message sent | your chat provider |

Each invocation emits **one sample** covering the last 15 minutes. Run it on the same
interval it reports on.

## Features

- One row per run — append straight to a CSV, or pipe JSON into a collector.
- Quiet by default: only the sample reaches stdout, so it pipes cleanly. Errors go to
  stderr, and `--verbose` adds the API library's debug output there.
- CSV, TSV, JSON and plain-text output.
- Exits `0` with `n=0` when no PoD traffic occurred, so a quiet period is not an alarm.
- Exits `1` on a genuine failure (expired token, API error), so alert on a non-zero exit.
- Uses Sonrai's GraphQL API via the `sonrai_api` library.

## Requirements

- Python 3.7+
- [`sonrai_api`](../sonrai_api/README.md) library copied into the same directory as the script
- `pip3 install -r sonrai_api/requirements.txt`
- Sonrai API credentials configured in `sonrai_api/config.json`

> `sonrai_api` loads `sonrai_api/config.json` by **relative path**, so run the script from
> the directory that holds the `sonrai_api` folder. Running it from elsewhere either fails
> to find the library config or picks up a different copy, and the token lookup fails with
> `No 'user token' found`. Set `SONRAI_API_TOKENSTORE` to an absolute path if you need to
> run it from another directory.

## Usage

```bash
python pond-timings.py
```

```bash
python pond-timings.py --format json
```

```bash
python pond-timings.py --no-header --output pod-latency.csv
```

```bash
python pond-timings.py --minutes 5
```

### Options

| Flag | Description |
|---|---|
| `--minutes` | Window to average over, 1–1440. Match your poll interval (default `15`) |
| `--format` | `csv` (default), `tsv`, `json` or `text` |
| `--no-header` | Omit the CSV/TSV header, and append to `--output` rather than overwrite |
| `--output` | Write to this file instead of stdout |
| `-v`, `--verbose` | Show debug output from the Sonrai API library (stderr) |

### Output

```
window_start,window_end,cloudtrail_eventbridge_n,cloudtrail_eventbridge_avg_s,sonrai_to_chatops_n,sonrai_to_chatops_avg_s
2026-10-22T09:15:00Z,2026-10-22T09:30:00Z,412,5.413,9,6.271
```

The `_n` columns are the sample counts behind each average. An empty `_avg_s` means no
qualifying events in the window.

## Polling

Run it on the same interval as `--minutes` so the windows tile without gaps or overlap:

```cron
*/15 * * * * cd /path/to/scripts && /usr/bin/python3 pond-timings.py --no-header --output /var/log/pod-latency.csv
```

## Notes

- **The averages are means.** A single slow request in an otherwise quiet window moves
  the number noticeably. Use the `_n` columns to require a minimum sample size before
  treating a spike as meaningful.
- **`cloudtrail_eventbridge` covers every event observed**, whether or not it went on to
  raise a PoD request — delivery latency does not depend on what the event triggered.
  `sonrai_to_chatops` necessarily covers only events that created a request.
- **Only the first approval message counts.** Reminder and escalation messages are sent
  later by design and are excluded; counting them would report normal escalation delay as
  pipeline latency.
- **Window edges.** A request created near the end of a window whose approval message
  lands just after it is not counted in either sample. This slightly lowers
  `sonrai_to_chatops_n` but does not bias the average.
- **Large windows.** The API does not paginate these queries. If a long `--minutes` returns
  a capped result the script warns that the sample is partial — shorten the window.
- **Working directory matters.** See the note under Requirements - the cron example above
  uses `cd` for this reason.
- **Token expiry.** API tokens are time-limited. When one lapses the script exits non-zero
  with `Sonrai Token Expired`; issue a new token from the Advanced Search UI. If no token
  is present at all, `sonrai_api` tries to prompt for one - under a scheduler, where stdin
  is closed, that surfaces as a non-zero exit rather than a hang, which is why alerting on
  the exit code matters.
