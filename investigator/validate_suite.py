from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List


def quality_violations(report: dict) -> list[str]:
    """Require each collected test to produce its declared call outcome."""
    outcomes = report.get("outcomes", [])
    problems = []
    calls = [row for row in outcomes if row["phase"] == "call"]
    if len(calls) != report["test_count"] or len({row["test_name"] for row in calls}) != report["test_count"]:
        problems.append("Missing or duplicate test-call outcomes (setup failure, skip, or incomplete execution).")
    for row in outcomes:
        expected = "failed" if row.get("expected_bug") else "passed"
        if row["phase"] != "call" or row["outcome"] != expected:
            problems.append("{}: {} {} (expected {} call)".format(
                row["test_name"], row["phase"], row["outcome"], expected))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a pytest layer and verify its expected result.")
    parser.add_argument("--expected-tests", type=int, required=True)
    parser.add_argument("--expected-failures", type=int, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("paths", nargs="+", help="Pytest files or directories to run.")
    args = parser.parse_args()

    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    command: List[str] = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *args.paths,
        "--failure-artifact={}".format(args.artifact),
    ]
    args.artifact.unlink(missing_ok=True)
    result = subprocess.run(command, check=False)
    if not args.artifact.exists():
        print("No pytest artifact was produced.")
        return 1

    report = json.loads(args.artifact.read_text(encoding="utf-8"))
    violations = quality_violations(report)
    if violations:
        print("Quality gate rejected this run:\n" + "\n".join(violations))
        return 1
    actual = (report["test_count"], report["failure_count"])
    expected = (args.expected_tests, args.expected_failures)
    if actual != expected:
        print("Expected {} tests / {} failures, got {} tests / {} failures.".format(*expected, *actual))
        return 1
    expected_exit = 1 if args.expected_failures else 0
    if result.returncode != expected_exit:
        print("Unexpected pytest exit code {} (expected {}).".format(result.returncode, expected_exit))
        return 1

    print("Verified {} tests with {} expected failures.".format(*actual))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
