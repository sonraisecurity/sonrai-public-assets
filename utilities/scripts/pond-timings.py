#!/usr/bin/env python3
"""Average latency of the two Permission-on-Demand hops outside Sonrai's control.

Reports one sample per invocation, covering the last 15 minutes. Intended to be polled
on the same interval it reports on and fed into a monitoring or dashboard system.

  cloudtrail_eventbridge  CloudTrail eventTime -> EventBridge ingestionTime  (AWS)
  sonrai_to_chatops       PoD request created -> first approval message      (chat provider)

The CloudTrail hop covers every event observed, actioned or not: delivery latency does
not depend on whether an event went on to raise a PoD request. Only the ChatOps hop is
restricted to events that produced one.

Exits 0 with n=0 when the window is quiet, so a poller does not alarm on no traffic.
Exits 1 on a real failure, so alert on a non-zero exit.
"""
import argparse
import csv
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone

# sonrai_api logs while it imports (it verifies the token at module load) and calls
# logging.basicConfig(stream=sys.stdout). Both have to be headed off before the import:
# stdout belongs to the sample, and argparse has not run yet, so --verbose is read
# straight from argv. basicConfig is a no-op once a handler exists, so this one wins.
VERBOSE = any(arg in ("-v", "--verbose") for arg in sys.argv[1:])

logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] -- %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stderr,
)
# The level goes on the handler, not the root logger: the library assigns its own
# loggers a level from config.json (DEBUG by default), which would otherwise override
# anything set here and leak debug output into normal runs.
for _handler in logging.getLogger().handlers:
    _handler.setLevel(logging.DEBUG if VERBOSE else logging.WARNING)

from sonrai_api import api, logger  # noqa: E402  (must follow basicConfig above)

AUDIT_EVENT_NAME = "EventbridgeSubmitPONDRequest"
INITIAL_TEMPLATES = ("APPROVAL", "JIT_APPROVAL", "ZOMBIE_APPROVAL")

FIELDS = ["window_start", "window_end",
          "cloudtrail_eventbridge_n", "cloudtrail_eventbridge_avg_s",
          "sonrai_to_chatops_n", "sonrai_to_chatops_avg_s"]

AUDIT_QUERY = """
query PondAudit($where: CloudAuditLogsFilter) {
  ListAsyncCloudAuditLogs(where: $where) {
    count
    items { timestamp requestPayload responsePayload }
  }
}
"""

CHATOPS_QUERY = """
query PondChatops($where: ChatopsMessageSentFilter) {
  ChatopsMessageSent(where: $where) {
    items { pondRequestId chatopsTemplate sentAt }
  }
}
"""

RE_EVENT_TIME = re.compile(r"eventTime[^0-9]{0,12}(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
RE_INGEST_TIME = re.compile(r"ingestionTime[^0-9]{0,12}(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
RE_POND_ID = re.compile(
    r"pondRequestId[^0-9a-fA-F]{0,8}"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


def parse_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).strip().rstrip("Z")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_ts(value):
    """Timestamps arrive as ISO text or epoch milliseconds depending on the field."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, timezone.utc)
    text = str(value)
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000.0, timezone.utc)
    return parse_iso(text)


def blob_to_text(blob):
    if blob is None:
        return ""
    if isinstance(blob, (dict, list)):
        return json.dumps(blob)
    return str(blob)


def extract_pond_id(blob):
    if isinstance(blob, dict):
        inner = blob.get("pondRequest") or {}
        if isinstance(inner, dict) and inner.get("pondRequestId"):
            return inner["pondRequestId"]
    found = RE_POND_ID.search(blob_to_text(blob))
    return found.group(1) if found else None


def iso(when):
    return when.isoformat().replace("+00:00", "Z") if when else ""


def query(gql, where, root):
    """Returns (items, count). sonrai_api raises on auth, timeout and server errors."""
    resp = api.execute_query(gql, variables=json.dumps({"where": where}))
    if resp.get("errors"):
        raise SystemExit("GraphQL error: " +
                         "; ".join(e.get("message", "?") for e in resp["errors"])[:600])
    node = (resp.get("data") or {}).get(root) or {}
    return node.get("items") or [], node.get("count")


def collect(minutes):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    audit, audit_count = query(AUDIT_QUERY, {
        "eventName": {"op": "EQ", "value": AUDIT_EVENT_NAME},
        "timestamp": {"op": "GT", "value": iso(start)},
    }, "ListAsyncCloudAuditLogs")
    # The API does not paginate, so a short read means the result was capped and the
    # averages would be computed over a biased subset.
    if isinstance(audit_count, int) and audit_count > len(audit):
        logger.warning("API reported %s events but returned %s; averages cover a partial "
                       "sample - use a shorter --minutes", audit_count, len(audit))

    # Only the first approval message counts. *_ESCALATED fires an hour later and would
    # otherwise read as an hour of latency.
    chatops = {}
    chat_items, _ = query(CHATOPS_QUERY, {"sentAt": {"op": "GT", "value": iso(start)}},
                          "ChatopsMessageSent")
    for row in chat_items:
        pond_id = row.get("pondRequestId")
        sent = parse_ts(row.get("sentAt"))
        if pond_id and sent and (row.get("chatopsTemplate") or "") in INITIAL_TEMPLATES:
            if pond_id not in chatops or sent < chatops[pond_id]:
                chatops[pond_id] = sent

    # A PoD request is re-notified on every re-request, so a message well after this one
    # was created belongs to a later cycle rather than to this request's latency.
    gap_cap = min(minutes * 60, 3600)
    ct_hop, chat_hop = [], []
    for item in audit:
        payload = blob_to_text(item.get("requestPayload"))
        event_match = RE_EVENT_TIME.search(payload)
        ingest_match = RE_INGEST_TIME.search(payload)
        if event_match and ingest_match:
            t_event = parse_iso(event_match.group(1))
            t_bridge = parse_iso(ingest_match.group(1))
            if t_event and t_bridge:
                ct_hop.append((t_bridge - t_event).total_seconds())

        pond_id = extract_pond_id(item.get("responsePayload"))
        t_created = parse_ts(item.get("timestamp"))
        sent = chatops.get(pond_id) if pond_id else None
        if t_created and sent:
            gap = (sent - t_created).total_seconds()
            if -2 <= gap <= gap_cap:
                chat_hop.append(gap)

    average = lambda vals: sum(vals) / len(vals) if vals else None
    return {
        "window_start": iso(start),
        "window_end": iso(end),
        "cloudtrail_eventbridge_n": len(ct_hop),
        "cloudtrail_eventbridge_avg_s": average(ct_hop),
        "sonrai_to_chatops_n": len(chat_hop),
        "sonrai_to_chatops_avg_s": average(chat_hop),
    }


def emit(sample, fmt, no_header, handle):
    if fmt == "json":
        json.dump(sample, handle, indent=2)
        handle.write("\n")
        return

    def cell(value):
        return "" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))

    if fmt == "text":
        width = max(len(f) for f in FIELDS) + 2
        for field in FIELDS:
            print(f"{field:<{width}}{cell(sample[field])}", file=handle)
        return

    # Every value is a timestamp or a number this script formats itself, so no cell can
    # begin with a spreadsheet formula character.
    writer = csv.writer(handle, delimiter="\t" if fmt == "tsv" else ",", lineterminator="\n")
    if not no_header:
        writer.writerow(FIELDS)
    writer.writerow([cell(sample[f]) for f in FIELDS])


def minutes_arg(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected an integer")
    if not 1 <= value <= 1440:
        raise argparse.ArgumentTypeError("must be between 1 and 1440")
    return value


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--minutes", type=minutes_arg, default=15,
                        help="window to average over; match your poll interval (default 15)")
    parser.add_argument("--format", choices=("csv", "tsv", "json", "text"), default="csv")
    parser.add_argument("--no-header", action="store_true",
                        help="omit the csv/tsv header when appending to a file")
    parser.add_argument("--output", help="write here instead of stdout")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show debug output from the Sonrai API library (stderr)")
    args = parser.parse_args()

    sample = collect(args.minutes)
    if args.output:
        with open(args.output, "a" if args.no_header else "w", encoding="utf-8", newline="") as fh:
            emit(sample, args.format, args.no_header, fh)
    else:
        emit(sample, args.format, args.no_header, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # sonrai_api raises SonraiAPIException on auth/timeout
        logger.error(str(exc))
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
