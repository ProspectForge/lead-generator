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

    with patch.object(checker, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ecommerce_page_content

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.confidence > 0.5

@pytest.mark.asyncio
async def test_detects_non_ecommerce_site(non_ecommerce_page_content):
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = non_ecommerce_page_content

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