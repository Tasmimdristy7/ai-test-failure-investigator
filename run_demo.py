from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from investigator.clustering import cluster_failures
from investigator.validate_suite import quality_violations

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "artifacts" / "failures.json"


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.unlink(missing_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_milestone.py",
            f"--failure-artifact={ARTIFACT}",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        check=False,
    )
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    violations = quality_violations(data)
    if violations:
        print("Quality gate rejected run:", violations)
        return 1
    clusters = cluster_failures(data["failures"])
    observed = sorted(cluster["count"] for cluster in clusters)
    expected = [5, 8, 15]

    print("\nDeterministic failure analysis")
    for index, cluster in enumerate(clusters, start=1):
        fingerprint = cluster["fingerprint"]
        print(f"Cluster {index}: {cluster['count']} tests | {cluster['summary']}")
        print(
            "  Fingerprint: "
            f"service={fingerprint['service']} endpoint={fingerprint['endpoint']} "
            f"status={fingerprint['status']} exception={fingerprint['exception']}"
        )

    if result.returncode not in (0, 1):
        return result.returncode
    if (
        data["test_count"] != 50
        or data["failure_count"] != 28
        or sum(observed) != 28
        or observed != expected
        or len(clusters) != 3
    ):
        print(
            f"Unexpected experiment result: {data['test_count']} tests, "
            f"{data['failure_count']} failures, cluster sizes {observed}"
        )
        return 1

    print("\nMilestone verified: 50 executions, 28 intentional failures, 3 root-cause clusters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
