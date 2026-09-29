from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--failure-artifact",
        default=os.environ.get("FAILURE_ARTIFACT", "artifacts/failures.json"),
        help="Path where structured failure data is written.",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    context = item.get_closest_marker("failure_context")
    bug_id = context.kwargs.get("bug_id") if context else None
    if report.when == "call" or report.failed or report.skipped:
        item.config._investigator_outcomes.append({
            "test_name": item.nodeid, "phase": report.when,
            "outcome": report.outcome, "expected_bug": bug_id,
        })
    if report.when == "call":
        item.rep_call = report
    if report.when != "call" or not report.failed:
        return

    context = item.get_closest_marker("failure_context")
    metadata = context.kwargs if context else {}
    message = str(report.longrepr)
    status_match = re.search(r"received\s+(\d{3})\b(?!\d)", message, re.I)
    failure_record = {
        "test_name": item.nodeid,
        "suite": Path(str(item.fspath)).stem,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_message": message.splitlines()[-1] if message else "test failed",
        "stack_trace": message,
        "http_status": int(status_match.group(1)) if status_match else metadata.get("status"),
        "endpoint": metadata.get("endpoint"),
        "bug_id": metadata.get("bug_id"),
        "browser": None,
        "retry": 0,
        "duration": report.duration,
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "screenshot": None,
        "trace": None,
        "network_errors": [],
    }
    item._investigator_failure_record = failure_record
    item.config._investigator_failures.append(failure_record)


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._investigator_failures = []
    session.config._investigator_outcomes = []


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    artifact_path = Path(session.config.getoption("--failure-artifact"))
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    report = session.config._investigator_failures
    artifact_path.write_text(json.dumps({
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "test_count": len(session.items),
        "exit_status": int(exitstatus),
        "failure_count": len(report),
        "failures": report,
        "outcomes": session.config._investigator_outcomes,
    }, indent=2), encoding="utf-8")
