# tests/test_brand_expander.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.brand_expander import BrandExpander


@pytest.fixture
def expander(tmp_path):
    return BrandExpander(cache_dir=tmp_path / "loc_cache")


# ═══════════════════════════════════════════════════════════════════
# expand_brand — basic behavior
# ═══════════════════════════════════════════════════════════════════

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


@pytest.mark.asyncio
async def test_expand_brand_returns_empty_when_website_is_none(expander):
    results = await expander.expand_brand(
        brand_name="Test Brand",
        known_website=None,
        vertical="running"
    )
    assert results == []


# ═══════════════════════════════════════════════════════════════════
# expand_brand — field mapping
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_expand_brand_uses_brand_name_as_fallback(expander):
    """When a location has no name, brand_name should be used."""
    mock_locations = [
        {"address": "1 St, City, ST", "city": "City", "state": "ST"},
    ]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="My Brand",
            known_website="https://mybrand.com",
            vertical="running"
        )

    assert results[0]["name"] == "My Brand"


@pytest.mark.asyncio
async def test_expand_brand_uses_location_name_when_present(expander):
    mock_locations = [
        {"name": "Location Name", "address": "1 St", "city": "City", "state": "ST"},
    ]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="Brand",
            known_website="https://brand.com",
            vertical="running"
        )

    assert results[0]["name"] == "Location Name"


@pytest.mark.asyncio
async def test_expand_brand_uses_brand_name_when_name_empty_string(expander):
    mock_locations = [
        {"name": "", "address": "1 St", "city": "City", "state": "ST"},
    ]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="Fallback",
            known_website="https://brand.com",
            vertical="running"
        )

    assert results[0]["name"] == "Fallback"


@pytest.mark.asyncio
async def test_expand_brand_propagates_vertical(expander):
    mock_locations = [{"name": "S", "address": "1 St", "city": "C", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://b.com",
            vertical="health_wellness"
        )

    assert results[0]["vertical"] == "health_wellness"


@pytest.mark.asyncio
async def test_expand_brand_sets_source_field(expander):
    mock_locations = [{"name": "S", "address": "1 St", "city": "C", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://b.com",
            vertical="running"
        )

    assert results[0]["source"] == "location_scrape"


@pytest.mark.asyncio
async def test_expand_brand_sets_website_field(expander):
    mock_locations = [{"name": "S", "address": "1 St", "city": "C", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://mysite.com",
            vertical="running"
        )

    assert results[0]["website"] == "https://mysite.com"


@pytest.mark.asyncio
async def test_expand_brand_sets_place_id_none(expander):
    mock_locations = [{"name": "S", "address": "1 St", "city": "C", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://b.com",
            vertical="running"
        )

    assert results[0]["place_id"] is None


@pytest.mark.asyncio
async def test_expand_brand_handles_missing_address(expander):
    mock_locations = [{"name": "S", "city": "C", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://b.com",
            vertical="running"
        )

    assert results[0]["address"] == ""


@pytest.mark.asyncio
async def test_expand_brand_handles_missing_city(expander):
    mock_locations = [{"name": "S", "address": "1 St", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://b.com",
            vertical="running"
        )

    assert results[0]["city"] == ""


# ═══════════════════════════════════════════════════════════════════
# expand_brand — backwards compatibility
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_expand_brand_ignores_extra_kwargs(expander):
    """Extra kwargs like api_key, cities should be ignored."""
    mock_locations = [{"name": "S", "address": "1 St", "city": "C", "state": "S"}]

    with patch.object(expander.scraper, 'scrape', new_callable=AsyncMock, return_value=mock_locations):
        results = await expander.expand_brand(
            brand_name="B",
            known_website="https://b.com",
            vertical="running",
            api_key="old_key",
            cities=["Boston", "Denver"],
            concurrency=5,
        )

    assert len(results) == 1


def test_init_ignores_api_key_kwarg():
    """Constructor should accept and ignore api_key for backwards compat."""
    expander = BrandExpander(api_key="some_key", concurrency=10)
    assert hasattr(expander, 'scraper')


# ═══════════════════════════════════════════════════════════════════
# should_expand — decision logic
# ═══════════════════════════════════════════════════════════════════

def test_should_expand_multi_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston", "Denver"], location_count=2) is True


def test_should_expand_many_locations_one_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=3) is True


def test_should_not_expand_single_location():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=1) is False


def test_should_not_expand_two_locations_one_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=2) is False


def test_should_expand_from_scrape_always_true():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=1, from_scrape=True) is True


def test_should_expand_empty_cities():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=[], location_count=0) is False


def test_should_expand_exact_threshold_two_cities():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["A", "B"], location_count=2) is True


def test_should_expand_exact_threshold_three_locations():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["A"], location_count=3) is True


def test_should_not_expand_below_all_thresholds():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["A"], location_count=2) is False
