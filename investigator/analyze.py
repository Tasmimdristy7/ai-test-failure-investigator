from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from investigator.clustering import cluster_failures


def load_failures(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["failures"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fingerprint and cluster a pytest failure artifact.")
    parser.add_argument("artifact", nargs="?", type=Path, default=Path("artifacts/failures.json"))
    args = parser.parse_args()
    clusters = cluster_failures(load_failures(args.artifact))

    print(f"{sum(cluster['count'] for cluster in clusters)} FAILED TESTS")
    print(f"\n{len(clusters)} LIKELY ROOT CAUSES")
    for index, cluster in enumerate(clusters, start=1):
        fingerprint = cluster["fingerprint"]
        print(f"\nCluster {index}")
        print(f"{cluster['count']} tests")
        print(cluster["summary"])
        print(f"Mean text similarity: {cluster['similarity']:.0%}")
        print(f"Fingerprint: service={fingerprint['service']} endpoint={fingerprint['endpoint']} status={fingerprint['status']} exception={fingerprint['exception']}")


if __name__ == "__main__":
    main()
