#!/usr/bin/env python3

import os
import shlex
import subprocess
import sys


CPF_PATH = os.path.expanduser("/opt/cpf")


def run_command(cmd: list[str]) -> int:
	"""Run a command, echo it, and return the exit code."""
	print(f"Running: {' '.join(shlex.quote(part) for part in cmd)}")
	completed = subprocess.run(cmd, check=False)
	return completed.returncode


def main() -> int:
	first_cmd = [
		os.path.join(CPF_PATH, "pagerduty-oncall-schedule-query.py"),
		"--config",
		os.path.join(CPF_PATH, "pagerduty.json"),
	]
	second_cmd = [
		os.path.join(CPF_PATH, "cpf-approvers.py"),
		"--import",
		"--file",
		os.path.join(CPF_PATH, "cpf_frompagerduty_approversatscope.txt"),
	]

	first_rc = run_command(first_cmd)
	if first_rc != 0:
		return first_rc

	return run_command(second_cmd)


if __name__ == "__main__":
	sys.exit(main())
