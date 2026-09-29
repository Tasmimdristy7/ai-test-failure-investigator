from fastapi.testclient import TestClient
import pytest

from app.main import app, reset_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store() -> None:
    reset_state()


@pytest.mark.integration
@pytest.mark.parametrize("product_id", ["SKU-001", "SKU-002", "SKU-003", "SKU-001", "SKU-002", "SKU-003", "SKU-001", "SKU-002", "SKU-003", "SKU-001"])
def test_login_add_to_cart_and_checkout(product_id: str) -> None:
    login = client.post("/api/login", json={"username": "demo", "password": "demo-password"})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    added = client.post("/api/cart/items", headers=headers, json={"product_id": product_id, "quantity": 1})
    assert added.status_code == 200
    cart = client.get("/api/cart", headers=headers).json()
    order = client.post("/api/checkout", headers=headers, json={"cart_total_cents": cart["total_cents"]})
    assert order.status_code == 200
    assert order.json()["total_cents"] == cart["total_cents"]
    assert len(client.get("/api/orders", headers=headers).json()) == 1


@pytest.mark.integration
@pytest.mark.parametrize("user", ["demo", "alice", "bob", "customer-04", "customer-05", "customer-06", "customer-07", "customer-08", "customer-09", "customer-10"])
def test_order_visibility_in_owner_list(user: str) -> None:
    created = client.post("/api/checkout", json={"user_id": user, "cart_total_cents": 1500}).json()
    headers = {"Authorization": "Bearer valid-" + user}
    orders = client.get("/api/orders", headers=headers).json()
    assert len(orders) == 1
    assert orders[0]["order_id"] == created["order_id"]
    assert orders[0]["user_id"] == user
