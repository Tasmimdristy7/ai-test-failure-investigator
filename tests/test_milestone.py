from typing import Optional

from fastapi.testclient import TestClient
import pytest

from app.main import app
from investigator.fingerprints import fingerprint_failure, normalize_failure_text

client = TestClient(app)


@pytest.mark.parametrize("case", range(15))
@pytest.mark.failure_context(endpoint="/api/checkout", status=500, bug_id="BUG-01")
def test_checkout_rejects_broken_coupon(case: int) -> None:
    response = client.post("/api/checkout", json={"coupon_code": f"BUG-01-{case}"})
    assert response.status_code == 200, f"expected HTTP 200, received {response.status_code} for POST /api/checkout"


@pytest.mark.parametrize("case", range(8))
@pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02")
def test_expired_auth_token_is_rejected(case: int) -> None:
    response = client.get("/api/profile", headers={"Authorization": f"Bearer expired-user-{case}"})
    assert response.status_code == 401, f"expected HTTP 401, received {response.status_code} for GET /api/profile"


@pytest.mark.parametrize("quantity", range(6, 11))
@pytest.mark.failure_context(endpoint="/api/cart/total", status=200, bug_id="BUG-03")
def test_cart_total_for_quantity_above_five(quantity: int) -> None:
    response = client.post("/api/cart/total", json={"unit_price_cents": 200, "quantity": quantity})
    expected = 200 * quantity
    assert response.json()["total_cents"] == expected, (
        f"expected total {expected} cents, received {response.json()['total_cents']} cents"
    )


@pytest.mark.parametrize("path", ["/api/health"] * 4)
def test_health_endpoint(path: str) -> None:
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("coupon", [None, "SAVE5", "UNKNOWN", "WELCOME"])
def test_checkout_without_injected_defect(coupon: Optional[str]) -> None:
    response = client.post("/api/checkout", json={"cart_total_cents": 2500, "coupon_code": coupon})
    expected = 2000 if coupon == "SAVE5" else 2500
    assert response.status_code == 200
    assert response.json()["total_cents"] == expected


@pytest.mark.parametrize("user", ["alice", "bob", "casey", "devon"])
def test_valid_auth_token(user: str) -> None:
    response = client.get("/api/profile", headers={"Authorization": f"Bearer valid-{user}"})
    assert response.status_code == 200
    assert response.json()["user_id"] == user


def test_profile_rejects_missing_authentication() -> None:
    assert client.get("/api/profile").status_code == 401


@pytest.mark.parametrize("quantity", [1, 2, 3, 4])
def test_cart_total_at_or_below_five(quantity: int) -> None:
    response = client.post("/api/cart/total", json={"unit_price_cents": 200, "quantity": quantity})
    assert response.json()["total_cents"] == 200 * quantity


@pytest.mark.parametrize("variant", range(5))
def test_fingerprint_normalizes_run_specific_noise(variant: int) -> None:
    samples = [
        "HTTPError: POST /api/checkout -> 500 at 2026-09-28T12:30:00Z on localhost:43121",
        "HTTPError: POST /api/checkout -> 500 at 2026-09-29T09:00:00Z on localhost:51234",
        "HTTPError: POST /api/checkout -> 500 id 1a2b3c4d-1234-5678-9abc-123456789abc on localhost:60001",
        "HTTPError: POST /api/checkout -> 500 session=token-secret on localhost:40000",
        "HTTPError: POST /api/checkout -> 500 from app.py:123 on localhost:44000",
    ]
    fingerprint = fingerprint_failure(samples[variant], endpoint="/api/checkout")
    assert fingerprint.key() == "checkout|/api/checkout|500|HTTPError"
    assert normalize_failure_text(samples[variant])
