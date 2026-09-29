from typing import Optional

from fastapi.testclient import TestClient
import pytest

from app.main import app, reset_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store() -> None:
    reset_state()


@pytest.mark.api
@pytest.mark.parametrize(
    "query",
    [
        "", "canvas", "mug", "mat", "daypack", "travel", "wool", "CAM", "ceramic", "desk",
        "Canvas Daypack", "Ceramic", "Travel Mug", "Wool Desk Mat", "supply", "pack", "pottery",
        "office", "weekend", "field",
    ],
)
def test_product_search_contract(query: str) -> None:
    response = client.get("/api/products", params={"q": query})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert all("product_id" in item and "name" in item and "price_cents" in item for item in response.json())


@pytest.mark.api
@pytest.mark.parametrize("user", ["demo", "alice", "bob", "user-03", "user-04", "user-05", "user-06", "user-07", "user-08", "user-09"])
def test_valid_bearer_profile_contract(user: str) -> None:
    response = client.get("/api/profile", headers={"Authorization": "Bearer valid-" + user})
    assert response.status_code == 200
    assert response.json() == {"user_id": user}


@pytest.mark.api
@pytest.mark.parametrize("token", ["", "bad", "invalid-user", "Bearer", pytest.param("expired-a", marks=pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02")), pytest.param("expired-b", marks=pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02")), pytest.param("expired-c", marks=pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02")), pytest.param("expired-d", marks=pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02")), pytest.param("expired-e", marks=pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02")), pytest.param("expired-f", marks=pytest.mark.failure_context(endpoint="/api/profile", status=200, bug_id="BUG-02"))])
def test_invalid_or_expired_bearer_is_rejected(token: str) -> None:
    headers = {} if token == "" else {"Authorization": "Bearer " + token}
    response = client.get("/api/profile", headers=headers)
    assert response.status_code == 401


@pytest.mark.api
@pytest.mark.parametrize("coupon,total", [(None, 2500), ("SAVE5", 2000), ("UNKNOWN", 2500), ("WELCOME", 2500), ("", 2500), ("save5", 2500), ("SAVE10", 2500), ("SPRING", 2500), ("VIP", 2500), ("NEW", 2500)])
def test_checkout_coupon_response_contract(coupon: Optional[str], total: int) -> None:
    response = client.post("/api/checkout", json={"cart_total_cents": 2500, "coupon_code": coupon})
    assert response.status_code == 200
    assert response.json()["total_cents"] == total
    assert "order_id" in response.json()


@pytest.mark.api
@pytest.mark.parametrize("quantity", [1, 2, 3, 4, 5])
def test_cart_total_contract(quantity: int) -> None:
    response = client.post("/api/cart/total", json={"unit_price_cents": 200, "quantity": quantity})
    assert response.status_code == 200
    assert response.json()["total_cents"] == 200 * quantity


@pytest.mark.api
@pytest.mark.parametrize("quantity", [0, -1, -5, -10, -100])
def test_cart_rejects_nonpositive_quantity(quantity: int) -> None:
    response = client.post("/api/cart/total", json={"unit_price_cents": 200, "quantity": quantity})
    assert response.status_code == 422


@pytest.mark.api
@pytest.mark.parametrize("path", ["/api/health"] * 20)
def test_health_contract(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.api
@pytest.mark.parametrize("quantity", [6, 7, 8, 9, 10])
@pytest.mark.injected_defect(bug_id="BUG-03")
@pytest.mark.failure_context(endpoint="/api/cart/total", status=200, bug_id="BUG-03")
def test_cart_large_quantity_contract(quantity: int) -> None:
    response = client.post("/api/cart/total", json={"unit_price_cents": 200, "quantity": quantity})
    assert response.json()["total_cents"] == 200 * quantity


@pytest.mark.api
@pytest.mark.parametrize("index", range(15))
def test_invalid_login_contract(index: int) -> None:
    response = client.post("/api/login", json={"username": "unknown-{}".format(index), "password": "wrong"})
    assert response.status_code == 401
