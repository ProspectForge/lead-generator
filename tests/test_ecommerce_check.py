# tests/test_ecommerce_check.py
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker, EcommerceResult

@pytest.fixture
def ecommerce_page_content():
    return """
    <html>
    <head><script src="https://cdn.shopify.com/s/files/1/theme.js"></script></head>
    <body>
    <h1>Welcome to Our Store</h1>
    <button>Add to Cart</button>
    <a href="/checkout">Checkout</a>
    <span>$50.00</span>
    </body>
    </html>
    """

@pytest.fixture
def non_ecommerce_page_content():
    return """
    <html>
    <body>
    <h1>About Our Company</h1>
    <p>Visit us at our store locations.</p>
    <p>Contact us for more information.</p>
    </body>
    </html>
    """

@pytest.mark.asyncio
async def test_detects_ecommerce_site(ecommerce_page_content):
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([ecommerce_page_content], None)

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.confidence >= 0.5

@pytest.mark.asyncio
async def test_detects_non_ecommerce_site(non_ecommerce_page_content):
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([non_ecommerce_page_content], None)

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is False


def test_ecommerce_result_has_marketplace_fields():
    """EcommerceResult should include marketplace detection fields."""
    result = EcommerceResult(
        url="https://example.com",
        has_ecommerce=True,
        confidence=0.9,
        indicators_found=["platform:shopify"],
        platform="shopify",
        pages_checked=3,
        marketplaces=["amazon", "ebay"],
        marketplace_links={"amazon": "https://amazon.com/stores/example"},
        priority="high"
    )

    assert result.marketplaces == ["amazon", "ebay"]
    assert result.marketplace_links == {"amazon": "https://amazon.com/stores/example"}
    assert result.priority == "high"


def test_detect_marketplaces_from_links():
    """Should detect marketplace presence from URL patterns."""
    checker = EcommerceChecker()

    content = """
    <a href="https://amazon.com/stores/ExampleBrand">Amazon Store</a>
    <a href="https://ebay.com/str/examplebrand">eBay Shop</a>
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert "amazon" in marketplaces
    assert "ebay" in marketplaces
    assert "amazon" in links
    assert "amazon.com/stores/ExampleBrand" in links["amazon"]


def test_detect_marketplaces_from_text():
    """Should detect marketplace presence from text mentions."""
    checker = EcommerceChecker()

    content = """
    <p>Shop on Amazon for fast Prime shipping!</p>
    <p>Also available on Walmart marketplace.</p>
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert "amazon" in marketplaces
    assert "walmart" in marketplaces


def test_detect_no_marketplaces():
    """Should return empty when no marketplace signals found."""
    checker = EcommerceChecker()

    content = """
    <p>Shop directly on our website for the best prices.</p>
    <p>Free shipping on orders over $50.</p>
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert marketplaces == []
    assert links == {}


@pytest.fixture
def ecommerce_with_marketplace_content():
    return """
    <html>
    <head><script src="https://cdn.shopify.com/s/files/1/theme.js"></script></head>
    <body>
    <button>Add to Cart</button>
    <a href="/checkout">Checkout</a>
    <a href="https://amazon.com/stores/OurBrand">Find us on Amazon</a>
    <span>$50.00</span>
    </body>
    </html>
    """


@pytest.mark.asyncio
async def test_check_returns_marketplace_data(ecommerce_with_marketplace_content):
    """check() should return marketplace detection results."""
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([ecommerce_with_marketplace_content], None)

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert "amazon" in result.marketplaces
        assert result.priority == "high"


@pytest.mark.asyncio
async def test_check_returns_medium_priority_without_marketplace(ecommerce_page_content):
    """check() should return medium priority when no marketplace found."""
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([ecommerce_page_content], None)

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"


@pytest.mark.asyncio
async def test_crawl_failure_sets_flag():
    """When site can't be fetched, crawl_failed should be True."""
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([], "Connection failed")

        result = await checker.check("https://dead-site.com")

        assert result.has_ecommerce is False
        assert result.crawl_failed is True
        assert result.fail_reason == "Connection failed"
        assert result.pages_checked == 0


def test_find_shop_links():
    """Should extract shop/product page links from HTML."""
    checker = EcommerceChecker()

    html = """
    <nav>
    <a href="/shop">Shop</a>
    <a href="/about">About</a>
    <a href="/collections/all">All Products</a>
    <a href="https://other-domain.com/store">External</a>
    </nav>
    """

    paths = checker._find_shop_links(html, "https://example.com")

    assert "/shop" in paths
    assert "/collections/all" in paths
    # External links should be excluded
    assert not any("other-domain" in p for p in paths)
