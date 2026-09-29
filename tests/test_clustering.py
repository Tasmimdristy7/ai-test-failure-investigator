import pytest

from investigator.clustering import cluster_failures
from investigator.fingerprints import normalize_failure_text


def test_similar_checkout_failures_cluster_despite_wording_changes() -> None:
    failures = [
        {
            "test_name": "test_coupon_validation",
            "error_message": "CheckoutError: POST /api/checkout returned HTTP 500 while coupon validation failed",
            "endpoint": "/api/checkout",
            "http_status": 500,
        },
        {
            "test_name": "test_coupon_normalization",
            "error_message": "HttpError: POST /api/checkout -> 500; checkout coupon validation could not complete",
            "endpoint": "/api/checkout",
            "http_status": 500,
        },
    ]

    clusters = cluster_failures(failures)

    assert len(clusters) == 1
    assert clusters[0]["count"] == 2
    assert clusters[0]["similarity"] >= 0.35
    assert clusters[0]["tests"] == ["test_coupon_normalization", "test_coupon_validation"]


def test_unrelated_errors_on_same_endpoint_remain_separate() -> None:
    failures = [
        {
            "test_name": "test_coupon",
            "error_message": "CheckoutError coupon validation failed",
            "endpoint": "/api/checkout",
            "http_status": 500,
        },
        {
            "test_name": "test_database_pool",
            "error_message": "DatabaseError connection pool exhausted during transaction serialization",
            "endpoint": "/api/checkout",
            "http_status": 500,
        },
    ]

    assert len(cluster_failures(failures)) == 2


def test_similar_text_never_crosses_endpoint_or_status_boundary() -> None:
    base_failure = {
        "error_message": "HTTPError checkout coupon validation failed HTTP 500",
        "http_status": 500,
    }
    failures = [
        dict(base_failure, test_name="checkout", endpoint="/api/checkout"),
        dict(base_failure, test_name="profile", endpoint="/api/profile"),
        dict(base_failure, test_name="checkout-timeout", endpoint="/api/checkout", http_status=504),
    ]

    assert len(cluster_failures(failures)) == 3


def test_empty_input_and_invalid_threshold() -> None:
    assert cluster_failures([]) == []
    with pytest.raises(ValueError, match="similarity_threshold"):
        cluster_failures([], similarity_threshold=1.1)


def test_timestamp_with_timezone_offset_is_normalized() -> None:
    normalized = normalize_failure_text("started at 2026-09-28T20:53:18.429237+00:00")

    assert "<timestamp>" in normalized
    assert "2026-09-28" not in normalized
    assert "+00:00" not in normalized
