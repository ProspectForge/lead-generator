# tests/test_location_scraper.py
import json
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.location_scraper import LocationScraper


@pytest.fixture
def scraper(tmp_path):
    return LocationScraper(cache_dir=tmp_path / "location_cache")


# --- Cache tests ---

def test_cache_miss_returns_none(scraper):
    result = scraper._get_cached("https://example.com")
    assert result is None


def test_cache_set_and_get(scraper):
    locations = [{"name": "Store 1", "address": "123 Main St", "city": "Boston", "state": "MA"}]
    scraper._set_cached("https://example.com", locations)
    result = scraper._get_cached("https://example.com")
    assert result == locations


def test_cache_expired_returns_none(scraper):
    locations = [{"name": "Store 1", "address": "123 Main St", "city": "Boston", "state": "MA"}]
    scraper._set_cached("https://example.com", locations)

    # Manually expire the cache entry
    cache_key = scraper._cache_key("https://example.com")
    cache_file = scraper.cache_dir / f"{cache_key}.json"
    data = json.loads(cache_file.read_text())
    data["_cached_at"] = time.time() - (91 * 86400)  # 91 days ago
    cache_file.write_text(json.dumps(data))

    result = scraper._get_cached("https://example.com")
    assert result is None


# --- URL discovery tests ---

def test_build_candidate_urls():
    scraper = LocationScraper()
    urls = scraper._build_candidate_urls("https://www.fleetfeet.com")
    assert "https://www.fleetfeet.com/locations" in urls
    assert "https://www.fleetfeet.com/stores" in urls
    assert "https://www.fleetfeet.com/store-locator" in urls


# --- HTML parsing tests ---

def test_parse_json_ld_locations(scraper):
    html = '''
    <html><head>
    <script type="application/ld+json">
    [
      {"@type": "Store", "name": "Store A", "address": {"@type": "PostalAddress", "streetAddress": "123 Main St", "addressLocality": "Boston", "addressRegion": "MA"}},
      {"@type": "Store", "name": "Store B", "address": {"@type": "PostalAddress", "streetAddress": "456 Oak Ave", "addressLocality": "Denver", "addressRegion": "CO"}}
    ]
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_locations_from_html(html)
    assert len(locations) >= 2
    assert any(loc["city"] == "Boston" for loc in locations)
    assert any(loc["city"] == "Denver" for loc in locations)


def test_parse_json_ld_single_object(scraper):
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "LocalBusiness", "name": "My Store", "address": {"@type": "PostalAddress", "streetAddress": "789 Elm St", "addressLocality": "Austin", "addressRegion": "TX"}}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_locations_from_html(html)
    assert len(locations) >= 1
    assert locations[0]["city"] == "Austin"


def test_parse_nav_links_for_locations(scraper):
    html = '''
    <html><body>
    <nav>
      <a href="/about">About</a>
      <a href="/find-a-store">Find a Store</a>
      <a href="/contact">Contact</a>
    </nav>
    </body></html>
    '''
    links = scraper._find_location_links(html, "https://example.com")
    assert any("/find-a-store" in link for link in links)


def test_parse_no_locations_returns_empty(scraper):
    html = '<html><body><p>Just a normal page</p></body></html>'
    locations = scraper._parse_locations_from_html(html)
    assert locations == []


# --- Integration test (mocked HTTP) ---

@pytest.mark.asyncio
async def test_scrape_locations_from_json_ld(scraper):
    json_ld_html = '''
    <html><head>
    <script type="application/ld+json">
    [
      {"@type": "Store", "name": "Location 1", "address": {"@type": "PostalAddress", "streetAddress": "100 First St", "addressLocality": "Portland", "addressRegion": "OR"}},
      {"@type": "Store", "name": "Location 2", "address": {"@type": "PostalAddress", "streetAddress": "200 Second St", "addressLocality": "Seattle", "addressRegion": "WA"}}
    ]
    </script>
    </head><body></body></html>
    '''
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json_ld_html

    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_404.text = ""

    async def mock_get(url, **kwargs):
        if "/locations" in url:
            return mock_response
        return mock_404

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        locations = await scraper.scrape("https://www.example.com")

    assert len(locations) >= 2
    assert any(loc["city"] == "Portland" for loc in locations)


@pytest.mark.asyncio
async def test_scrape_returns_empty_on_no_locations(scraper):
    plain_html = '<html><body><p>No locations here</p></body></html>'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = plain_html

    async def mock_get(url, **kwargs):
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        locations = await scraper.scrape("https://www.example.com")

    assert locations == []


@pytest.mark.asyncio
async def test_scrape_uses_cache(scraper):
    cached = [{"name": "Cached Store", "address": "1 Cache St", "city": "Boston", "state": "MA"}]
    scraper._set_cached("https://www.example.com", cached)

    # Should not make any HTTP request -- returned from cache
    locations = await scraper.scrape("https://www.example.com")
    assert locations == cached
