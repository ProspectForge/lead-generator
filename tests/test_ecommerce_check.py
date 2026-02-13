# tests/test_ecommerce_check.py
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker, EcommerceResult

@pytest.fixture
def ecommerce_page_content():
    # _fetch_page returns markdown string directly
    return """
    # Welcome to Our Store

    Shop our latest collection

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Free shipping on orders over $50.00
    """

@pytest.fixture
def non_ecommerce_page_content():
    # _fetch_page returns markdown string directly
    return """
    # About Our Company

    Visit us at our store locations.
    Contact us for more information.
    """

@pytest.mark.asyncio
async def test_detects_ecommerce_site(ecommerce_page_content):
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [ecommerce_page_content]

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.confidence >= 0.5

@pytest.mark.asyncio
async def test_detects_non_ecommerce_site(non_ecommerce_page_content):
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [non_ecommerce_page_content]

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
    checker = EcommerceChecker(api_key="test_key")

    content = """
    # Our Store

    Find us online:
    - [Amazon Store](https://amazon.com/stores/ExampleBrand)
    - [eBay Shop](https://ebay.com/str/examplebrand)

    Visit our locations for in-person shopping.
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert "amazon" in marketplaces
    assert "ebay" in marketplaces
    assert "amazon" in links
    assert "amazon.com/stores/ExampleBrand" in links["amazon"]


def test_detect_marketplaces_from_text():
    """Should detect marketplace presence from text mentions."""
    checker = EcommerceChecker(api_key="test_key")

    content = """
    # Welcome

    Shop on Amazon for fast Prime shipping!
    Also available on Walmart marketplace.
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert "amazon" in marketplaces
    assert "walmart" in marketplaces


def test_detect_no_marketplaces():
    """Should return empty when no marketplace signals found."""
    checker = EcommerceChecker(api_key="test_key")

    content = """
    # Our Store

    Shop directly on our website for the best prices.
    Free shipping on orders over $50.
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert marketplaces == []
    assert links == {}


@pytest.fixture
def ecommerce_with_marketplace_content():
    return """
    # Welcome to Our Store

    Shop our latest collection

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Also find us on [Amazon](https://amazon.com/stores/OurBrand)!

    Free shipping on orders over $50.00
    """


@pytest.mark.asyncio
async def test_check_returns_marketplace_data(ecommerce_with_marketplace_content):
    """check() should return marketplace detection results."""
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [ecommerce_with_marketplace_content]

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert "amazon" in result.marketplaces
        assert result.priority == "high"


@pytest.mark.asyncio
async def test_check_returns_medium_priority_without_marketplace(ecommerce_page_content):
    """check() should return medium priority when no marketplace found."""
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [ecommerce_page_content]

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"