import itertools
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Failure Investigator E-commerce Testbed", version="0.1.0")


class CheckoutRequest(BaseModel):
    cart_total_cents: int = 2500
    coupon_code: Optional[str] = None
    user_id: str = "demo"


class CartTotalRequest(BaseModel):
    unit_price_cents: int = 200
    quantity: int


class LoginRequest(BaseModel):
    username: str
    password: str


class CartItemRequest(BaseModel):
    product_id: str
    quantity: int = 1


PRODUCTS: List[Dict[str, Any]] = [
    {"product_id": "SKU-001", "name": "Canvas Daypack", "price_cents": 4800},
    {"product_id": "SKU-002", "name": "Ceramic Travel Mug", "price_cents": 1800},
    {"product_id": "SKU-003", "name": "Wool Desk Mat", "price_cents": 3200},
]
USERS = {"demo": "demo-password", "alice": "alice-password", "bob": "bob-password"}
ORDERS: Dict[str, Dict[str, Any]] = {}
CARTS: Dict[str, List[Dict[str, Any]]] = {}
IDEMPOTENCY_KEYS: Dict[str, str] = {}
ORDER_SEQUENCE = itertools.count(1)
ORDER_LOCK = Lock()


def reset_state() -> None:
    global ORDER_SEQUENCE
    ORDERS.clear()
    CARTS.clear()
    IDEMPOTENCY_KEYS.clear()
    ORDER_SEQUENCE = itertools.count(1)


def user_from_authorization(authorization: Optional[str]) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ")
    if token.startswith("expired-"):
        # BUG-02: expired tokens are accepted as if they were current.
        return token.removeprefix("expired-")
    if not token.startswith("valid-"):
        raise HTTPException(status_code=401, detail="invalid token")
    return token.removeprefix("valid-")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def storefront(locator_bug: bool = Query(default=False)) -> str:
    page = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    if locator_bug:
        # BUG-07: a release variant changes the checkout button's test locator.
        page = page.replace('data-testid="checkout-submit"', 'data-testid="place-order"')
    return page


@app.post("/api/login")
def login(request: LoginRequest) -> Dict[str, str]:
    if USERS.get(request.username) != request.password:
        raise HTTPException(status_code=401, detail="invalid username or password")
    return {"access_token": "valid-" + request.username, "token_type": "bearer"}


@app.get("/api/products")
def products(
    q: str = "",
    schema_drift: bool = False,
    delayed: bool = False,
) -> List[Dict[str, Any]]:
    if q.lower().startswith("slow-"):
        # BUG-06: certain search terms trigger an unexpectedly slow query.
        time.sleep(0.25)
    if delayed:
        # BUG-10: the product API exceeds a typical UI request timeout.
        time.sleep(0.6)

    result = [product.copy() for product in PRODUCTS if q.lower() in product["name"].lower()]
    if schema_drift:
        # BUG-08: this response variant renames a public field without versioning.
        for product in result:
            product["price"] = product.pop("price_cents")
    return result


@app.get("/api/cart")
def get_cart(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    user_id = user_from_authorization(authorization)
    items = CARTS.get(user_id, [])
    return {"items": items, "total_cents": sum(item["line_total_cents"] for item in items)}


@app.post("/api/cart/items")
def add_cart_item(
    request: CartItemRequest,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if request.quantity < 1:
        raise HTTPException(status_code=422, detail="quantity must be positive")
    product = next((item for item in PRODUCTS if item["product_id"] == request.product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    user_id = user_from_authorization(authorization)
    line_total = product["price_cents"] * request.quantity
    if request.quantity > 5:
        # BUG-03: quantities above five lose one unit from the calculated total.
        line_total -= product["price_cents"]
    item = {
        "product_id": product["product_id"],
        "name": product["name"],
        "quantity": request.quantity,
        "line_total_cents": line_total,
    }
    CARTS.setdefault(user_id, []).append(item)
    return item


@app.post("/api/checkout")
def checkout(
    request: CheckoutRequest,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None),
) -> dict[str, object]:
    if request.coupon_code and request.coupon_code.startswith("BUG-01-"):
        raise HTTPException(status_code=500, detail="coupon normalization failed")

    # BUG-04 fixed: both five-dollar coupons apply exactly one discount.
    discount_cents = 500 if request.coupon_code in ("SAVE5", "DOUBLE5") else 0
    user_id = user_from_authorization(authorization) if authorization else request.user_id

    if idempotency_key:
        if idempotency_key in IDEMPOTENCY_KEYS:
            # BUG-09: concurrent retries race between this check and the write below.
            time.sleep(0.03)
        else:
            time.sleep(0.03)

    with ORDER_LOCK:
        order_id = "order-{:04d}".format(next(ORDER_SEQUENCE))
        order = {
            "order_id": order_id,
            "user_id": user_id,
            "total_cents": max(0, request.cart_total_cents - discount_cents),
            "status": "placed",
        }
        ORDERS[order_id] = order
        if idempotency_key:
            IDEMPOTENCY_KEYS[idempotency_key] = order_id
    return {key: value for key, value in order.items() if key != "user_id"}


@app.get("/api/orders")
def orders(authorization: Optional[str] = Header(default=None)) -> List[Dict[str, Any]]:
    user_id = user_from_authorization(authorization)
    return [order.copy() for order in ORDERS.values() if order["user_id"] == user_id]


@app.get("/api/orders/{order_id}")
def order_detail(
    order_id: str,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    user_from_authorization(authorization)
    order = ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    # BUG-05: the authenticated user's identity is not checked against the order owner.
    return order.copy()


@app.get("/api/profile")
def profile(authorization: Optional[str] = Header(default=None)) -> dict[str, str]:
    user_id = user_from_authorization(authorization)
    return {"user_id": user_id}


@app.post("/api/cart/total")
def cart_total(request: CartTotalRequest) -> dict[str, int]:
    if request.quantity < 1:
        raise HTTPException(status_code=422, detail="quantity must be positive")

    total = request.unit_price_cents * request.quantity
    if request.quantity > 5:
        # BUG-03: quantities above five lose one unit from the calculated total.
        total -= request.unit_price_cents
    return {"total_cents": total}
