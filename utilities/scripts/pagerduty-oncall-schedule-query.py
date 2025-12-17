#!/usr/bin/env python3
"""
Fetch on-call user emails for a PagerDuty schedule and write them to a file.

Configuration file format (JSON):

{
	"api_key": "<PAGERDUTY_API_TOKEN>",
	"schedule_id": "<PAGERDUTY_SCHEDULE_ID>",
	"output_file": "cpf_frompagerduty_approversatscope.txt",
	"time_zone": "UTC",                  
	"cpf_scope": "my_scope_value",
	"loglevel": "INFO",                 
	"default_approvers": ["user1@example.com", "user2@example.com"]
}

	Usage:
	pagerduty-oncall-schedule-query.py --config pagerduty.json
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Iterable, Set
from urllib import request, parse, error


PD_BASE_URL = "https://api.pagerduty.com"

# Logger will be initialized after config is read
logger = None


def setup_logger(log_level: str) -> None:
	"""Configure logging based on the provided log level."""
	global logger
	level = getattr(logging, log_level.upper(), logging.INFO)
	logging.basicConfig(
		level=level,
		format='[%(asctime)s] [%(levelname)s] - %(message)s',
		datefmt='%Y-%m-%d %H:%M:%S',
		stream=sys.stdout,
	)
	logger = logging.getLogger(__name__)


def _http_get(url: str, headers: dict, retry: int = 3, backoff: float = 1.5) -> dict:
	for attempt in range(retry):
		req = request.Request(url, headers=headers, method="GET")
		logger.debug(f"HTTP GET request (attempt {attempt + 1}/{retry}): {url}")
		try:
			with request.urlopen(req) as resp:
				charset = resp.headers.get_content_charset() or "utf-8"
				body = resp.read().decode(charset)
				data = json.loads(body)
				logger.debug(f"API response: {json.dumps(data, indent=2)}")
				return data
		except error.HTTPError as e:
			logger.error(f"HTTP error {e.code}: {e.reason}")
			if e.code == 429:
				retry_after = e.headers.get("Retry-After")
				wait_s = float(retry_after) if retry_after else (backoff ** attempt)
				logger.debug(f"Rate limited; waiting {wait_s}s before retry")
				time.sleep(wait_s)
				continue
			if 500 <= e.code < 600 and attempt < retry - 1:
				logger.debug(f"Server error; retrying in {backoff ** attempt}s")
				time.sleep(backoff ** attempt)
				continue
			raise
		except error.URLError as e:
			logger.error(f"URL error: {e.reason}")
			if attempt < retry - 1:
				logger.debug(f"Connection error; retrying in {backoff ** attempt}s")
				time.sleep(backoff ** attempt)
				continue
			raise


def get_oncall_emails(api_key: str, schedule_id: str, time_zone: str = "UTC") -> Set[str]:
	logger.info(f"Fetching on-call emails for schedule: {schedule_id}")
	headers = {
		"Authorization": f"Token token={api_key}",
		"Accept": "application/vnd.pagerduty+json;version=2",
		"Content-Type": "application/json",
	}

	emails: Set[str] = set()
	limit = 100
	offset = 0

	while True:
		query = {
			"schedule_ids[]": [schedule_id],
			"include[]": ["users"],
			"earliest": "true",
			"limit": limit,
			"offset": offset,
			"time_zone": time_zone or "UTC",
		}
		url = f"{PD_BASE_URL}/oncalls?{parse.urlencode(query, doseq=True)}"
		logger.debug(f"Querying with offset={offset}, limit={limit}")

		data = _http_get(url, headers=headers)
		oncalls = data.get("oncalls", [])
		logger.debug(f"Found {len(oncalls)} oncall record(s) in this response")

		for oc in oncalls:
			user = oc.get("user") or {}
			email = user.get("email")
			if email:
				emails.add(email.strip())
				logger.debug(f"Added email: {email}")
			else:
				logger.debug(f"Oncall record has no email: {oc}")

		more = bool(data.get("more"))
		returned = len(oncalls)
		logger.debug(f"Pagination: more={more}, returned={returned}")
		if not more or returned == 0:
			logger.debug("No more pages; stopping pagination")
			break
		offset += returned if returned else limit

	logger.info(f"Fetched {len(emails)} unique email(s)")
	return emails


def _strip_quotes(value: str) -> str:
	"""Remove optional surrounding quotes from a string."""
	val = value.strip()
	if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
		return val[1:-1]
	return val


def read_config(path: str) -> dict:
	"""Read JSON config and normalize fields."""
	with open(path, "r", encoding="utf-8") as f:
		cfg = json.load(f)

	# Basic required fields
	api_key = _strip_quotes(cfg.get("api_key", ""))
	schedule_id = _strip_quotes(cfg.get("schedule_id", ""))
	output_file = _strip_quotes(cfg.get("output_file", "cpf_frompagerduty_approversatscope.txt")) or "cpf_frompagerduty_approversatscope.txt"
	time_zone = _strip_quotes(cfg.get("time_zone", "UTC")) or "UTC"
	cpf_scope = _strip_quotes(cfg.get("cpf_scope", ""))
	loglevel = _strip_quotes(cfg.get("loglevel", "INFO")) or "INFO"

	if not api_key:
		raise ValueError("api_key is required in config")
	if not schedule_id:
		raise ValueError("schedule_id is required in config")
	if not cpf_scope:
		raise ValueError("cpf_scope is required in config")

	# default_approvers can be list or comma-separated string
	default_approvers_val = cfg.get("default_approvers", [])
	default_approvers: set[str] = set()
	if isinstance(default_approvers_val, list):
		default_approvers = set(e.strip() for e in default_approvers_val if isinstance(e, str) and e.strip())
	elif isinstance(default_approvers_val, str) and default_approvers_val.strip():
		default_approvers = set(e.strip() for e in default_approvers_val.split(",") if e.strip())

	return {
		"api_key": api_key,
		"schedule_id": schedule_id,
		"output_file": output_file,
		"time_zone": time_zone,
		"cpf_scope": cpf_scope,
		"loglevel": loglevel,
		"default_approvers": default_approvers,
	}


def write_emails_to_file(scope: str, emails: Iterable[str], path: str) -> None:
	unique_sorted = sorted(set(e for e in emails if e))
	joined = ",".join(unique_sorted)
	logger.debug(f"Writing {len(unique_sorted)} email(s) to {path} with scope: {scope}")
	with open(path, "w", encoding="utf-8") as f:
		f.write(f"{scope},\"{joined}\"\n")
	logger.info(f"Successfully wrote output to {path}")


def main(argv: list[str]) -> int:
	parser = argparse.ArgumentParser(description="Export PagerDuty on-call emails for a schedule")
	parser.add_argument(
		"--config",
		"-c",
		required=False,
		default="pagerduty.json",
		help="Path to JSON config file (default: pagerduty.json)",
	)
	args = parser.parse_args(argv)

	cfg = read_config(args.config)
	setup_logger(cfg["loglevel"])
	logger.debug(f"Config file: {args.config}")
	logger.debug(f"Loaded config: api_key=*****, schedule_id={cfg['schedule_id']}, scope={cfg['cpf_scope']}, output_file={cfg['output_file']}")

	emails = get_oncall_emails(
		api_key=cfg["api_key"],
		schedule_id=cfg["schedule_id"],
		time_zone=cfg.get("time_zone", "UTC"),
	)

	# Combine PagerDuty emails with default approvers
	combined_emails = emails.union(cfg["default_approvers"])
	if cfg["default_approvers"]:
		logger.info(f"Added {len(cfg['default_approvers'])} default approver(s)")

	write_emails_to_file(cfg["cpf_scope"], combined_emails, cfg["output_file"])
	logger.info(f"Wrote scope and {len(combined_emails)} email(s) to {cfg['output_file']}")
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main(sys.argv[1:]))
	except error.HTTPError as e:
		msg = getattr(e, "read", lambda: b"")().decode("utf-8", errors="ignore")
		print(f"HTTP error {e.code}: {msg}")
		raise SystemExit(2)
	except Exception as e:
		print(f"Error: {e}")
		raise SystemExit(1)

