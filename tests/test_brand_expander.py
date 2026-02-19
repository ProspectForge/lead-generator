# tests/test_brand_expander.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.brand_expander import BrandExpander


@pytest.fixture
def expander(tmp_path):
    return BrandExpander(cache_dir=tmp_path / "loc_cache")


@pytest.mark.asyncio
async def test_expand_brand_uses_location_scraper(expander):
    """BrandExpander should call LocationScraper, not SerpAPI."""
    mock_locations = [
        {"name": "Store Boston", "address": "123 Main St, Boston, MA", "city": "Boston", "state": "MA"},
        {"name": "Store Denver", "address": "456 Oak Ave, Denver, CO", "city": "Denver", "state": "CO"},
    ]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="Test Brand",
            known_website="https://testbrand.com",
            vertical="running"
        )

    assert len(results) == 2
    assert results[0]["source"] == "location_scrape"
    assert results[0]["city"] == "Boston"


@pytest.mark.asyncio
async def test_expand_brand_returns_empty_when_no_locations(expander):
    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=[]):
        results = await expander.expand_brand(
            brand_name="Test Brand",
            known_website="https://testbrand.com",
            vertical="running"
        )

    assert results == []


@pytest.mark.asyncio
async def test_expand_brand_returns_empty_when_no_website(expander):
    results = await expander.expand_brand(
        brand_name="Test Brand",
        known_website="",
        vertical="running"
    )
    assert results == []


def test_should_expand_multi_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston", "Denver"], location_count=2) is True


def test_should_expand_many_locations_one_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=3) is True


def test_should_not_expand_single_location():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=1) is False
