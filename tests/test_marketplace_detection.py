# tests/test_marketplace_detection.py
"""Integration tests for marketplace detection feature."""
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker


@pytest.mark.asyncio
async def test_full_marketplace_detection_flow():
    """Test complete marketplace detection from website content."""
    checker = EcommerceChecker(api_key="test_key")

    # Simulate a website with Shopify e-commerce AND Amazon/eBay presence
    mock_content = """
    # Welcome to Acme Supplements

    ## Shop Our Products

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Price: $29.99

    ## Also Available On

    - [Shop on Amazon](https://amazon.com/stores/AcmeSupplements)
    - [Our eBay Store](https://ebay.com/str/acmesupplements)

    Free shipping via Shopify!
    cdn.shopify.com/assets/store.js
    """

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_content]

        result = await checker.check("https://acmesupplements.com")

        # Should detect e-commerce
        assert result.has_ecommerce is True
        assert result.platform == "shopify"

        # Should detect marketplaces
        assert "amazon" in result.marketplaces
        assert "ebay" in result.marketplaces
        assert len(result.marketplaces) == 2

        # Should have high priority
        assert result.priority == "high"

        # Should capture links
        assert "amazon" in result.marketplace_links
        assert "amazon.com/stores/AcmeSupplements" in result.marketplace_links["amazon"]


@pytest.mark.asyncio
async def test_ecommerce_without_marketplace():
    """Test e-commerce site without marketplace presence."""
    checker = EcommerceChecker(api_key="test_key")

    mock_content = """
    # Local Fitness Store

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Price: $49.99

    Powered by Shopify
    cdn.shopify.com/assets/store.js
    """

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_content]

        result = await checker.check("https://localfitness.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"


@pytest.mark.asyncio
async def test_detects_walmart_and_etsy():
    """Test detection of Walmart and Etsy marketplaces."""
    checker = EcommerceChecker(api_key="test_key")

    mock_content = """
    # Handmade Crafts

    [Buy Now](/shop)
    $19.99

    Available on Walmart marketplace!
    Visit our Etsy shop: https://etsy.com/shop/HandmadeCrafts
    """

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_content]

        result = await checker.check("https://handmadecrafts.com")

        assert "walmart" in result.marketplaces
        assert "etsy" in result.marketplaces
        assert result.priority == "high"
