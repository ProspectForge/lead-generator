# tests/test_ecommerce_check.py
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker, EcommerceResult

@pytest.fixture
def ecommerce_page_content():
    return {
        "data": {
            "markdown": """
            # Welcome to Our Store

            Shop our latest collection

            [Add to Cart](/cart)
            [Checkout](/checkout)

            Free shipping on orders over $50
            """
        }
    }

@pytest.fixture
def non_ecommerce_page_content():
    return {
        "data": {
            "markdown": """
            # About Our Company

            Visit us at our store locations.
            Contact us for more information.
            """
        }
    }

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
