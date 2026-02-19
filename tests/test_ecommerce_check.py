# tests/test_ecommerce_check.py
import pytest
import httpx
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
        mock_fetch.return_value = ([ecommerce_page_content], None, [])

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.confidence >= 0.5

@pytest.mark.asyncio
async def test_detects_non_ecommerce_site(non_ecommerce_page_content):
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([non_ecommerce_page_content], None, [])

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
        mock_fetch.return_value = ([ecommerce_with_marketplace_content], None, [])

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert "amazon" in result.marketplaces
        assert result.priority == "high"


@pytest.mark.asyncio
async def test_check_returns_medium_priority_without_marketplace(ecommerce_page_content):
    """check() should return medium priority when no marketplace found."""
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([ecommerce_page_content], None, [])

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"


@pytest.mark.asyncio
async def test_crawl_failure_sets_flag():
    """When site can't be fetched, crawl_failed should be True."""
    checker = EcommerceChecker()

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([], "Connection failed", [])

        result = await checker.check("https://dead-site.com")

        assert result.has_ecommerce is False
        assert result.crawl_failed is True
        assert result.fail_reason == "Connection failed"
        assert result.pages_checked == 0


@pytest.mark.parametrize("platform,html_snippet", [
    ("wix", '<script src="https://static.wixstatic.com/something.js"></script>'),
    ("ecwid", '<script src="https://app.ecwid.com/script.js"></script>'),
    ("volusion", '<link href="/v/vspfiles/templates/style.css">'),
    ("shift4shop", '<script src="https://cdn.3dcart.com/js/main.js"></script>'),
    ("opencart", '<a href="index.php?route=product/category">Shop</a>'),
    ("salesforce_commerce", '<script src="https://example.demandware.net/script.js"></script>'),
    ("sap_commerce", '<link href="/yacceleratorstorefront/style.css">'),
    ("snipcart", '<button class="snipcart-add-item" data-item-id="prod1">Buy</button>'),
])
def test_detect_new_platforms(platform, html_snippet):
    """Should detect new e-commerce platforms from HTML signatures."""
    checker = EcommerceChecker()
    detected = checker._detect_platform(html_snippet)
    assert detected == platform, f"Expected {platform}, got {detected}"


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


@pytest.mark.asyncio
async def test_fetch_site_pages_returns_headers():
    """_fetch_site_pages should return page headers alongside HTML."""
    checker = EcommerceChecker()

    mock_headers = httpx.Headers({"x-powered-by": "Shopify", "content-type": "text/html"})

    with patch.object(checker, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body>Shop</body></html>", None, mock_headers)
        pages, fail_reason, all_headers = await checker._fetch_site_pages("https://example.com")

    assert len(pages) == 1
    assert len(all_headers) == 1
    assert all_headers[0].get("x-powered-by") == "Shopify"


@pytest.mark.parametrize("headers_dict,expected_platform", [
    ({"x-powered-by": "Shopify"}, "shopify"),
    ({"x-shopid": "12345"}, "shopify"),
    ({"x-powered-by": "WP Engine", "set-cookie": "woocommerce_items_in_cart=0"}, "woocommerce"),
    ({"set-cookie": "_shopify_s=abc123; path=/"}, "shopify"),
    ({"set-cookie": "frontend=abc123; path=/", "x-powered-by": "Magento"}, "magento"),
    ({"server": "BigCommerce"}, "bigcommerce"),
    ({"content-type": "text/html"}, None),  # No platform signal
])
def test_detect_platform_from_headers(headers_dict, expected_platform):
    """Should detect platform from HTTP response headers."""
    checker = EcommerceChecker()
    headers = httpx.Headers(headers_dict)
    result = checker._detect_platform_from_headers(headers)
    assert result == expected_platform


def test_detect_platform_from_meta_generator():
    """Should detect platform from meta generator tag."""
    checker = EcommerceChecker()
    html = '<html><head><meta name="generator" content="WooCommerce 8.0"></head><body></body></html>'
    result = checker._detect_from_meta_tags(html)
    assert result == "woocommerce"


def test_detect_platform_from_script_src():
    """Should detect platform from script CDN URLs."""
    checker = EcommerceChecker()
    html = '<html><head><script src="https://cdn.shopify.com/s/files/1/0123/theme.js"></script></head><body></body></html>'
    result = checker._detect_from_meta_tags(html)
    assert result == "shopify"


def test_detect_product_from_og_type():
    """Should detect product pages from og:type meta."""
    checker = EcommerceChecker()
    html = '<html><head><meta property="og:type" content="product"></head><body></body></html>'
    result = checker._detect_from_meta_tags(html)
    assert result == "product_page"


def test_detect_ecommerce_from_json_ld_product():
    """Should detect e-commerce from JSON-LD Product structured data."""
    checker = EcommerceChecker()
    html = '''<html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Running Shoes", "offers": {"@type": "Offer", "price": "99.99"}}
    </script>
    </head><body></body></html>'''
    has_product, has_offer = checker._detect_from_json_ld(html)
    assert has_product is True
    assert has_offer is True


def test_no_json_ld_product():
    """Should return False when no Product JSON-LD found."""
    checker = EcommerceChecker()
    html = '''<html><head>
    <script type="application/ld+json">
    {"@type": "Organization", "name": "Example Corp"}
    </script>
    </head><body></body></html>'''
    has_product, has_offer = checker._detect_from_json_ld(html)
    assert has_product is False
    assert has_offer is False


def test_spa_trigger_detects_nextjs():
    """Should trigger Playwright for Next.js SPA with no e-commerce signals."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body></html>'
    assert checker._should_try_playwright(html, platform=None, score=0) is True


def test_spa_trigger_detects_react_app():
    """Should trigger for React app with minimal content."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="root"></div><script src="/static/js/bundle.js"></script></body></html>'
    assert checker._should_try_playwright(html, platform=None, score=0) is True


def test_spa_trigger_skips_when_platform_found():
    """Should NOT trigger when platform already detected."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="root"></div></body></html>'
    assert checker._should_try_playwright(html, platform="shopify", score=0) is False


def test_spa_trigger_skips_when_score_positive():
    """Should NOT trigger when e-commerce signals already found."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="root"></div></body></html>'
    assert checker._should_try_playwright(html, platform=None, score=4) is False


def test_spa_trigger_skips_content_rich_pages():
    """Should NOT trigger for pages with lots of visible text."""
    checker = EcommerceChecker()
    # Page with substantial text content (not a SPA shell)
    html = '<html><head></head><body>' + '<p>Lorem ipsum dolor sit amet. </p>' * 200 + '</body></html>'
    assert checker._should_try_playwright(html, platform=None, score=0) is False


@pytest.mark.asyncio
async def test_playwright_fallback_triggered_for_spa():
    """check() should use Playwright fallback for SPA sites with no signals."""
    checker = EcommerceChecker(playwright_fallback_enabled=True, playwright_timeout=15)

    # SPA shell with no e-commerce signals
    spa_html = '<html><head></head><body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body></html>'
    # Rendered HTML with Shopify signals
    rendered_html = '<html><body><div id="__next"><button class="add-to-cart">Add to Cart</button><script src="https://cdn.shopify.com/s/files/1/theme.js"></script></div></body></html>'

    mock_headers = httpx.Headers({"content-type": "text/html"})

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([spa_html], None, [mock_headers])
        with patch.object(checker, '_playwright_fetch', new_callable=AsyncMock) as mock_pw:
            mock_pw.return_value = rendered_html

            result = await checker.check("https://spa-store.com")

            mock_pw.assert_called_once()
            assert result.has_ecommerce is True
            assert result.platform == "shopify"


@pytest.mark.asyncio
async def test_playwright_fallback_not_triggered_when_disabled():
    """check() should skip Playwright when disabled."""
    checker = EcommerceChecker(playwright_fallback_enabled=False)

    spa_html = '<html><head></head><body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body></html>'
    mock_headers = httpx.Headers({"content-type": "text/html"})

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([spa_html], None, [mock_headers])

        result = await checker.check("https://spa-store.com")

        assert result.has_ecommerce is False
