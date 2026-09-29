import pytest
from fastapi.testclient import TestClient
from app.main import app, reset_state


@pytest.mark.parametrize("coupon", ["DOUBLE5", "SAVE5"])
@pytest.mark.parametrize("subtotal,expected", [(2500, 2000), (500, 0), (200, 0)])
def test_five_dollar_coupon_applies_once_and_never_goes_negative(coupon, subtotal, expected):
    reset_state()
    with TestClient(app) as client:
        response = client.post("/api/checkout", json={"cart_total_cents": subtotal, "coupon_code": coupon})
    assert response.status_code == 200
    assert response.json()["total_cents"] == expected
