from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from investigator.fingerprints import fingerprint_failure, normalize_failure_text

_ROOT_CAUSE_LABELS = {
    "checkout": "Checkout API regression",
    "auth": "Expired authentication token accepted",
    "cart": "Cart total regression for quantity above five",
}


def cluster_failures(
    failures: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.35,
) -> list[dict[str, Any]]:
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0 and 1")
    if not failures:
        return []

    prepared = []
    documents = []
    for failure in failures:
        fingerprint = fingerprint_failure(
            failure.get("error_message", ""),
            failure.get("stack_trace", ""),
            endpoint=failure.get("endpoint"),
            status=failure.get("http_status"),
        )
        text = normalize_failure_text(
            "{}\n{}\nendpoint={} status={}".format(
                failure.get("error_message", ""),
                failure.get("stack_trace", ""),
                fingerprint.endpoint,
                fingerprint.status,
            )
        )
        prepared.append({
            "fingerprint": fingerprint,
            "test_name": failure.get("test_name", "unknown"),
        })
        documents.append(text)

    try:
        vectors = TfidfVectorizer(ngram_range=(1, 2)).fit_transform(documents)
        similarities = cosine_similarity(vectors)
    except ValueError:
        similarities = np.eye(len(prepared))

    parents = list(range(len(prepared)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(prepared)):
        left_fingerprint = prepared[left]["fingerprint"]
        for right in range(left + 1, len(prepared)):
            right_fingerprint = prepared[right]["fingerprint"]
            same_boundary = (
                left_fingerprint.service == right_fingerprint.service
                and left_fingerprint.endpoint == right_fingerprint.endpoint
                and left_fingerprint.status == right_fingerprint.status
            )
            if left_fingerprint.key() == right_fingerprint.key() or (
                same_boundary and similarities[left, right] >= similarity_threshold
            ):
                union(left, right)

    groups: dict[int, list[int]] = {}
    for index in range(len(prepared)):
        groups.setdefault(find(index), []).append(index)

    clusters = []
    for indexes in groups.values():
        fingerprint = prepared[indexes[0]]["fingerprint"]
        service = fingerprint.service
        scored_pairs = [
            {
                "test_a": prepared[left]["test_name"],
                "test_b": prepared[right]["test_name"],
                "score": float(similarities[left, right]),
            }
            for position, left in enumerate(indexes)
            for right in indexes[position + 1:]
        ]
        pair_scores = [pair["score"] for pair in scored_pairs]
        comparison_examples = sorted(scored_pairs, key=lambda pair: pair["score"], reverse=True)[:5]
        clusters.append({
            "summary": _ROOT_CAUSE_LABELS.get(service, f"Failure in {service}"),
            "count": len(indexes),
            "fingerprint": fingerprint.as_dict(),
            "tests": sorted(prepared[index]["test_name"] for index in indexes),
            "similarity": round(float(np.mean(pair_scores)), 3) if pair_scores else 1.0,
            "comparison_examples": [
                {**pair, "score": round(pair["score"], 3)} for pair in comparison_examples
            ],
        })
    return sorted(clusters, key=lambda cluster: (-cluster["count"], cluster["summary"]))
