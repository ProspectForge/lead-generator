# tests/test_marketplace_detection.py
"""Integration tests for marketplace detection feature."""
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker


@pytest.mark.asyncio
async def test_full_marketplace_detection_flow():
    """Test complete marketplace detection from website content."""
    checker = EcommerceChecker()

    # Simulate a website with Shopify e-commerce AND Amazon/eBay presence
    mock_content = """
    <html><body>
    <a href="/cart">Add to Cart</a>
    <a href="/checkout">Checkout</a>
    <span>$29.99</span>
    <a href="https://amazon.com/stores/AcmeSupplements">Shop on Amazon</a>
    <a href="https://ebay.com/str/acmesupplements">Our eBay Store</a>
    <script src="https://cdn.shopify.com/assets/store.js"></script>
    </body></html>
    """

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([mock_content], None, [])

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
    checker = EcommerceChecker()

    mock_content = """
    <html><body>
    <a href="/cart">Add to Cart</a>
    <a href="/checkout">Checkout</a>
    <span>$49.99</span>
    <script src="https://cdn.shopify.com/assets/store.js"></script>
    </body></html>
    """

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([mock_content], None, [])

        result = await checker.check("https://localfitness.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"


@pytest.mark.asyncio
async def test_detects_walmart_and_etsy():
    """Test detection of Walmart and Etsy marketplaces."""
    checker = EcommerceChecker()

    mock_content = """
    <html><body>
    <a href="/shop">Buy Now</a>
    <span>$19.99</span>
    <p>Available on Walmart marketplace!</p>
    <a href="https://etsy.com/shop/HandmadeCrafts">Visit our Etsy shop</a>
    </body></html>
    """

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([mock_content], None, [])

        result = await checker.check("https://handmadecrafts.com")

        assert "walmart" in result.marketplaces
        assert "etsy" in result.marketplaces
        assert result.priority == "high"
