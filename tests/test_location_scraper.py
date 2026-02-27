# tests/test_location_scraper.py
import json
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.location_scraper import LocationScraper, DEFAULT_CACHE_TTL_DAYS, FALLBACK_PATHS


@pytest.fixture
def scraper(tmp_path):
    return LocationScraper(cache_dir=tmp_path / "location_cache")


# ═══════════════════════════════════════════════════════════════════
# Cache key generation
# ═══════════════════════════════════════════════════════════════════

def test_cache_key_strips_www_prefix(scraper):
    key1 = scraper._cache_key("https://www.example.com")
    key2 = scraper._cache_key("https://example.com")
    assert key1 == key2


def test_cache_key_ignores_path(scraper):
    key1 = scraper._cache_key("https://example.com/locations")
    key2 = scraper._cache_key("https://example.com/stores")
    assert key1 == key2


def test_cache_key_ignores_protocol(scraper):
    key1 = scraper._cache_key("http://example.com")
    key2 = scraper._cache_key("https://example.com")
    assert key1 == key2


def test_cache_key_case_insensitive(scraper):
    key1 = scraper._cache_key("https://Example.COM")
    key2 = scraper._cache_key("https://example.com")
    assert key1 == key2


def test_cache_key_different_domains_differ(scraper):
    key1 = scraper._cache_key("https://example.com")
    key2 = scraper._cache_key("https://other.com")
    assert key1 != key2


# ═══════════════════════════════════════════════════════════════════
# Cache read/write
# ═══════════════════════════════════════════════════════════════════

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


def test_cache_stores_empty_list(scraper):
    """Empty results should be cached (avoids retrying sites with no locations)."""
    scraper._set_cached("https://nolocs.com", [])
    result = scraper._get_cached("https://nolocs.com")
    assert result == []


def test_cache_not_expired_at_89_days(scraper):
    """Cache should still be valid at 89 days (TTL is 90)."""
    locations = [{"name": "Store", "address": "1 St", "city": "X", "state": "Y"}]
    scraper._set_cached("https://example.com", locations)

    cache_key = scraper._cache_key("https://example.com")
    cache_file = scraper.cache_dir / f"{cache_key}.json"
    data = json.loads(cache_file.read_text())
    data["_cached_at"] = time.time() - (89 * 86400)
    cache_file.write_text(json.dumps(data))

    result = scraper._get_cached("https://example.com")
    assert result == locations


def test_cache_corrupted_json_returns_none(scraper):
    cache_key = scraper._cache_key("https://example.com")
    cache_file = scraper.cache_dir / f"{cache_key}.json"
    cache_file.write_text("not valid json {{{")
    assert scraper._get_cached("https://example.com") is None


def test_cache_missing_locations_key_returns_none(scraper):
    cache_key = scraper._cache_key("https://example.com")
    cache_file = scraper.cache_dir / f"{cache_key}.json"
    cache_file.write_text(json.dumps({"_cached_at": time.time()}))
    assert scraper._get_cached("https://example.com") is None


def test_default_cache_ttl_is_90_days():
    assert DEFAULT_CACHE_TTL_DAYS == 90


def test_custom_cache_ttl(tmp_path):
    scraper = LocationScraper(cache_dir=tmp_path / "cache", cache_ttl_days=30)
    assert scraper.cache_ttl_seconds == 30 * 86400


def test_cache_dir_created_on_init(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    LocationScraper(cache_dir=cache_dir)
    assert cache_dir.exists()


# ═══════════════════════════════════════════════════════════════════
# URL discovery
# ═══════════════════════════════════════════════════════════════════

def test_build_fallback_urls():
    scraper = LocationScraper()
    urls = scraper._build_fallback_urls("https://www.fleetfeet.com")
    assert "https://www.fleetfeet.com/locations" in urls
    assert "https://www.fleetfeet.com/stores" in urls
    assert "https://www.fleetfeet.com/store-locator" in urls
    assert len(urls) == len(FALLBACK_PATHS)


def test_build_fallback_urls_adds_scheme_if_missing():
    scraper = LocationScraper()
    urls = scraper._build_fallback_urls("example.com")
    assert all(url.startswith("https://") for url in urls)


def test_build_fallback_urls_preserves_subdomain():
    scraper = LocationScraper()
    urls = scraper._build_fallback_urls("https://shop.example.com")
    assert "https://shop.example.com/locations" in urls


# ═══════════════════════════════════════════════════════════════════
# HTML link discovery
# ═══════════════════════════════════════════════════════════════════

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


def test_find_location_links_by_href_keyword(scraper):
    html = '<html><body><a href="/store-locator">Shop</a></body></html>'
    links = scraper._find_location_links(html, "https://example.com")
    assert any("store-locator" in link for link in links)


def test_find_location_links_by_text_keyword(scraper):
    html = '<html><body><a href="/go">Visit Our Stores</a></body></html>'
    links = scraper._find_location_links(html, "https://example.com")
    assert len(links) >= 1


def test_find_location_links_deduplicates(scraper):
    html = '''
    <html><body>
    <a href="/locations">Locations</a>
    <a href="/locations">Store Locations</a>
    </body></html>
    '''
    links = scraper._find_location_links(html, "https://example.com")
    assert links.count("https://example.com/locations") == 1


def test_find_location_links_resolves_relative_urls(scraper):
    html = '<html><body><a href="/stores">Stores</a></body></html>'
    links = scraper._find_location_links(html, "https://example.com/about")
    assert "https://example.com/stores" in links


def test_find_location_links_ignores_non_location_links(scraper):
    html = '''
    <html><body>
    <a href="/about">About Us</a>
    <a href="/careers">Careers</a>
    <a href="/blog">Blog</a>
    </body></html>
    '''
    links = scraper._find_location_links(html, "https://example.com")
    assert len(links) == 0


# ═══════════════════════════════════════════════════════════════════
# JSON-LD parsing
# ═══════════════════════════════════════════════════════════════════

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


def test_parse_json_ld_graph_container(scraper):
    """@graph containers should be expanded and searched."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@graph": [
      {"@type": "Store", "name": "G Store", "address": {"streetAddress": "1 St", "addressLocality": "Miami", "addressRegion": "FL"}}
    ]}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert len(locations) == 1
    assert locations[0]["city"] == "Miami"


def test_parse_json_ld_list_type(scraper):
    """@type as a list should be handled."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": ["Store", "LocalBusiness"], "name": "Multi-type", "address": {"streetAddress": "5 St", "addressLocality": "LA", "addressRegion": "CA"}}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert len(locations) == 1


def test_parse_json_ld_string_address(scraper):
    """String addresses (not objects) should be captured."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "Simple", "address": "123 Main St, City, ST 12345"}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert len(locations) == 1
    assert "123 Main St" in locations[0]["address"]


def test_parse_json_ld_malformed_json_skipped(scraper):
    """Invalid JSON in LD+JSON script tags should not crash."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {not valid json}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert locations == []


def test_parse_json_ld_non_location_types_ignored(scraper):
    """Non-location schema types should be skipped."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "WebSite", "name": "Example Site"}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert locations == []


def test_parse_json_ld_multiple_script_tags(scraper):
    """Multiple LD+JSON script tags should all be parsed."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "A", "address": {"streetAddress": "1 St", "addressLocality": "X", "addressRegion": "Y"}}
    </script>
    <script type="application/ld+json">
    {"@type": "Store", "name": "B", "address": {"streetAddress": "2 St", "addressLocality": "Z", "addressRegion": "W"}}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert len(locations) == 2


def test_parse_json_ld_empty_address_object_skipped(scraper):
    """Address with no city and no street should be skipped."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "Empty", "address": {"@type": "PostalAddress"}}
    </script>
    </head><body></body></html>
    '''
    locations = scraper._parse_json_ld(html)
    assert locations == []


def test_parse_json_ld_all_location_types(scraper):
    """All supported schema types should be recognized."""
    types = ["Store", "LocalBusiness", "Restaurant", "RetailStore",
             "SportingGoodsStore", "HealthAndBeautyBusiness",
             "ShoppingCenter", "GroceryStore"]
    for schema_type in types:
        html = f'''
        <html><head>
        <script type="application/ld+json">
        {{"@type": "{schema_type}", "name": "Test", "address": {{"streetAddress": "1 St", "addressLocality": "City", "addressRegion": "ST"}}}}
        </script>
        </head><body></body></html>
        '''
        locations = scraper._parse_json_ld(html)
        assert len(locations) == 1, f"Failed for type: {schema_type}"


# ═══════════════════════════════════════════════════════════════════
# Address pattern regex fallback
# ═══════════════════════════════════════════════════════════════════

def test_parse_address_patterns_basic(scraper):
    html = '<html><body>Visit us at 123 Main St, Boston, MA 02101</body></html>'
    locations = scraper._parse_address_patterns(html)
    assert len(locations) == 1
    assert locations[0]["city"] == "Boston"
    assert locations[0]["state"] == "MA"


def test_parse_address_patterns_multi_word_city(scraper):
    html = '<html><body>456 Oak Ave, Salt Lake City, UT 84101</body></html>'
    locations = scraper._parse_address_patterns(html)
    assert len(locations) == 1
    assert locations[0]["city"] == "Salt Lake City"


def test_parse_address_patterns_without_zip(scraper):
    html = '<html><body>789 Elm Dr, Portland, OR</body></html>'
    locations = scraper._parse_address_patterns(html)
    assert len(locations) == 1
    assert locations[0]["state"] == "OR"


def test_parse_address_patterns_deduplicates(scraper):
    html = '''<html><body>
    <p>123 Main St, Boston, MA 02101</p>
    <p>123 Main St, Boston, MA 02101</p>
    </body></html>'''
    locations = scraper._parse_address_patterns(html)
    assert len(locations) == 1


def test_parse_address_patterns_multiple_addresses(scraper):
    html = '''<html><body>
    <p>123 Main St, Boston, MA 02101</p>
    <p>456 Oak Ave, Denver, CO 80202</p>
    </body></html>'''
    locations = scraper._parse_address_patterns(html)
    assert len(locations) == 2


def test_parse_no_locations_returns_empty(scraper):
    html = '<html><body><p>Just a normal page</p></body></html>'
    locations = scraper._parse_locations_from_html(html)
    assert locations == []


def test_parse_locations_prefers_json_ld_over_regex(scraper):
    """If JSON-LD has locations, regex should not run."""
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "LD Store", "address": {"streetAddress": "1 LD St", "addressLocality": "LDCity", "addressRegion": "LD"}}
    </script>
    </head><body>
    <p>999 Regex Ave, RegexTown, RT 99999</p>
    </body></html>
    '''
    locations = scraper._parse_locations_from_html(html)
    assert len(locations) == 1
    assert locations[0]["city"] == "LDCity"


# ═══════════════════════════════════════════════════════════════════
# Full scrape integration (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════

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


@pytest.mark.asyncio
async def test_scrape_cache_hit_with_schemeless_url(scraper):
    """URLs without scheme should still hit cache (normalize before lookup)."""
    cached = [{"name": "Cached Store", "address": "1 Cache St", "city": "Boston", "state": "MA"}]
    # Write cache with normalized URL
    scraper._set_cached("https://www.example.com", cached)

    # Read cache with schemeless URL — should still hit
    locations = await scraper.scrape("www.example.com")
    assert locations == cached


@pytest.mark.asyncio
async def test_scrape_caches_empty_result(scraper):
    """Even when no locations found, result should be cached."""
    plain_html = '<html><body><p>Nothing</p></body></html>'

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

        await scraper.scrape("https://nolocs.example.com")

    # Verify cache was written
    cached = scraper._get_cached("https://nolocs.example.com")
    assert cached == []


@pytest.mark.asyncio
async def test_scrape_handles_connection_error_gracefully(scraper):
    """Connection errors should not crash, return empty and cache."""
    import httpx

    async def mock_get(url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        locations = await scraper.scrape("https://down.example.com")

    assert locations == []
    # Should be cached so next call doesn't retry
    assert scraper._get_cached("https://down.example.com") == []


@pytest.mark.asyncio
async def test_scrape_handles_timeout_gracefully(scraper):
    """Timeouts on all candidate URLs should return empty."""
    import httpx

    async def mock_get(url, **kwargs):
        raise httpx.TimeoutException("Timeout")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        locations = await scraper.scrape("https://slow.example.com")

    assert locations == []


@pytest.mark.asyncio
async def test_scrape_falls_back_to_homepage_links(scraper):
    """If candidate paths fail, should check homepage for nav links."""
    location_html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "Found via Link", "address": {"streetAddress": "1 St", "addressLocality": "City", "addressRegion": "ST"}}
    </script>
    </head><body></body></html>
    '''
    homepage_html = '''
    <html><body>
    <nav><a href="/our-locations-page">Find a Store</a></nav>
    </body></html>
    '''

    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_404.text = ""

    mock_homepage = MagicMock()
    mock_homepage.status_code = 200
    mock_homepage.text = homepage_html

    mock_location_page = MagicMock()
    mock_location_page.status_code = 200
    mock_location_page.text = location_html

    async def mock_get(url, **kwargs):
        if "our-locations-page" in url:
            return mock_location_page
        if url.rstrip("/") == "https://example.com":
            return mock_homepage
        return mock_404

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        locations = await scraper.scrape("https://example.com")

    assert len(locations) == 1
    assert locations[0]["city"] == "City"


@pytest.mark.asyncio
async def test_scrape_stops_after_first_successful_candidate(scraper):
    """Should stop trying candidate URLs once one yields results."""
    call_count = 0

    json_ld_html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "Found", "address": {"streetAddress": "1 St", "addressLocality": "City", "addressRegion": "ST"}}
    </script>
    </head><body></body></html>
    '''

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json_ld_html

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        locations = await scraper.scrape("https://example.com")

    assert len(locations) == 1
    # Should have stopped after first successful URL
    assert call_count == 1


@pytest.mark.asyncio
async def test_scrape_second_call_uses_cache(scraper):
    """Second call to same domain should use cache, not HTTP."""
    json_ld_html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Store", "name": "Cached", "address": {"streetAddress": "1 St", "addressLocality": "City", "addressRegion": "ST"}}
    </script>
    </head><body></body></html>
    '''

    http_call_count = 0
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json_ld_html

    async def mock_get(url, **kwargs):
        nonlocal http_call_count
        http_call_count += 1
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # First call — hits HTTP
        result1 = await scraper.scrape("https://example.com")
        first_call_count = http_call_count

        # Second call — should use cache
        result2 = await scraper.scrape("https://example.com")

    assert result1 == result2
    assert http_call_count == first_call_count  # No new HTTP calls
