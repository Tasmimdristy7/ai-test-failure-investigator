from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient
import pytest

from app.main import app, reset_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store() -> None:
    reset_state()


def bearer(user: str = "demo") -> dict[str, str]:
    return {"Authorization": "Bearer valid-" + user}


def test_login_search_cart_checkout_and_order_history() -> None:
    login = client.post("/api/login", json={"username": "demo", "password": "demo-password"})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert [item["product_id"] for item in client.get("/api/products?q=mug").json()] == ["SKU-002"]
    assert client.post("/api/cart/items", headers=headers, json={"product_id": "SKU-002"}).status_code == 200
    cart = client.get("/api/cart", headers=headers).json()
    assert cart["total_cents"] == 1800
    order = client.post("/api/checkout", headers=headers, json={"cart_total_cents": cart["total_cents"]}).json()
    assert order["total_cents"] == 1800
    assert client.get("/api/orders", headers=headers).json()[0]["order_id"] == order["order_id"]
    assert client.get("/api/profile", headers=headers).json()["user_id"] == "demo"


def test_coupon_discount_is_applied_once() -> None:
    response = client.post("/api/checkout", json={"cart_total_cents": 2500, "coupon_code": "DOUBLE5"})
    assert response.json()["total_cents"] == 2000


@pytest.mark.failure_context(endpoint="/api/orders/order-0001", status=200, bug_id="BUG-05")
def test_order_details_are_private_to_the_owner() -> None:
    created = client.post("/api/checkout", json={"user_id": "alice", "cart_total_cents": 1200}).json()
    response = client.get("/api/orders/" + created["order_id"], headers=bearer("bob"))
    assert response.status_code == 404


@pytest.mark.failure_context(endpoint="/api/products", status=200, bug_id="BUG-06")
def test_search_latency_stays_within_budget() -> None:
    started = time.monotonic()
    response = client.get("/api/products?q=slow-canvas")
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < 0.15, "search exceeded 150ms budget"


@pytest.mark.failure_context(endpoint="/", status=200, bug_id="BUG-07")
def test_checkout_button_keeps_stable_test_locator() -> None:
    page = client.get("/?locator_bug=true").text
    assert 'data-testid="checkout-submit"' in page


@pytest.mark.failure_context(endpoint="/api/products", status=200, bug_id="BUG-08")
def test_product_response_keeps_price_cents_schema() -> None:
    product = client.get("/api/products?schema_drift=true").json()[0]
    assert "price_cents" in product
    assert "price" not in product


@pytest.mark.failure_context(endpoint="/api/checkout", status=200, bug_id="BUG-09")
def test_checkout_retry_with_same_key_is_idempotent() -> None:
    def submit_order() -> str:
        return client.post(
            "/api/checkout",
            headers={"Idempotency-Key": "retry-123"},
            json={"user_id": "demo", "cart_total_cents": 1000},
        ).json()["order_id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        order_ids = list(pool.map(lambda _: submit_order(), range(2)))
    assert order_ids[0] == order_ids[1]


@pytest.mark.failure_context(endpoint="/api/products", status=200, bug_id="BUG-10")
def test_product_api_responds_within_ui_timeout() -> None:
    started = time.monotonic()
    response = client.get("/api/products?delayed=true")
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < 0.5, "product request exceeded 500ms UI timeout"


def test_unknown_product_is_not_added_to_cart() -> None:
    response = client.post("/api/cart/items", headers=bearer(), json={"product_id": "missing"})
    assert response.status_code == 404


def test_invalid_login_is_rejected() -> None:
    response = client.post("/api/login", json={"username": "demo", "password": "wrong"})
    assert response.status_code == 401
