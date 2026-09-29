import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
def test_storefront_shows_products(page: Page, base_url: str) -> None:
    page.goto(base_url)
    expect(page.get_by_role("heading", name="Useful things, made to last.")).to_be_visible()
    expect(page.get_by_role("heading", name="Canvas Daypack")).to_be_visible()
    expect(page.get_by_role("button", name="Add to cart").first).to_be_visible()


@pytest.mark.ui
def test_search_filters_products(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.get_by_role("textbox", name="Search products").fill("mug")
    page.get_by_role("button", name="Search").click()
    expect(page.get_by_role("heading", name="Ceramic Travel Mug")).to_be_visible()
    expect(page.get_by_role("heading", name="Canvas Daypack")).to_have_count(0)


@pytest.mark.ui
def test_login_add_to_cart_and_checkout(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Signed in as demo")).to_be_visible()
    page.get_by_role("button", name="Add to cart").first.click()
    expect(page.locator("#cart-content")).to_have_text("$48.00")
    page.get_by_test_id("checkout-submit").click()
    expect(page.get_by_role("status")).to_contain_text("Order order-")


@pytest.mark.ui
def test_login_error_is_announced(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.get_by_label("Password").fill("incorrect")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("status")).to_have_text("invalid username or password")


@pytest.mark.ui
@pytest.mark.injected_defect(bug_id="BUG-07")
@pytest.mark.failure_context(endpoint="/", status=200, bug_id="BUG-07")
def test_checkout_locator_survives_release_variant(page: Page, base_url: str) -> None:
    page.route("**/api/products*", lambda route: route.abort())
    page.goto(base_url + "/?locator_bug=true")
    expect(page.get_by_test_id("checkout-submit")).to_be_visible(timeout=1000)
