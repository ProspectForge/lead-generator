# Search Modes & Website Location Scraper — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add lean/extended search modes and replace SerpAPI brand expansion with a website location scraper to maximize lead quality within a 1000-search budget.

**Architecture:** Config-driven mode switch (`lean`/`extended`) controls which city list, query list, and discovery features are active. A new `LocationScraper` crawls brand websites for store-locator pages to find all locations (zero API cost), replacing the SerpAPI-based `BrandExpander`. All caches use 90-day TTL.

**Tech Stack:** Python 3, httpx, BeautifulSoup (bs4), pytest, existing pipeline infrastructure.

---

### Task 1: Bump SerpAPI cache TTL to 90 days

**Files:**
- Modify: `src/serpapi_search.py:57` (DEFAULT_CACHE_TTL_DAYS)
- Test: `tests/test_places_search.py`

**Step 1: Update the default**

In `src/serpapi_search.py` line 57, change:

```python
DEFAULT_CACHE_TTL_DAYS = 30
```

to:

```python
DEFAULT_CACHE_TTL_DAYS = 90
```

**Step 2: Run existing tests to verify nothing breaks**

Run: `python -m pytest tests/test_places_search.py -v`
Expected: All existing tests PASS

**Step 3: Commit**

```bash
git add src/serpapi_search.py
git commit -m "chore: bump SerpAPI cache TTL from 30 to 90 days"
```

---

### Task 2: Add lean_queries to config/cities.json

**Files:**
- Modify: `config/cities.json`

**Step 1: Add lean_queries block**

Add a new top-level key `"lean_queries"` to `config/cities.json` with 3-4 high-signal queries per vertical. These are the most distinct, highest-coverage queries from each vertical's full list:

```json
"lean_queries": {
  "health_wellness": [
    "supplement store",
    "health food store",
    "sports nutrition store"
  ],
  "sporting_goods": [
    "sporting goods store",
    "outdoor gear store",
    "running shoe store"
  ],
  "apparel": [
    "clothing boutique",
    "activewear store",
    "workwear store"
  ],
  "pet_supplies": [
    "pet supply store",
    "pet food store"
  ],
  "beauty_cosmetics": [
    "beauty supply store",
    "cosmetics store"
  ],
  "specialty_food": [
    "gourmet food store",
    "specialty grocery"
  ],
  "running_athletic": [
    "running store",
    "triathlon store"
  ],
  "cycling": [
    "bike shop",
    "cycling store"
  ],
  "outdoor_camping": [
    "camping store",
    "hiking gear store",
    "outdoor adventure store"
  ],
  "baby_kids": [
    "baby store",
    "children's clothing store"
  ],
  "home_goods": [
    "kitchenware store",
    "home goods store"
  ]
}
```

**Step 2: Add lean_cities block**

Add a new top-level key `"lean_cities"` with curated mid-tier metros:

```json
"lean_cities": {
  "us": [
    "Chicago, IL",
    "Houston, TX",
    "Phoenix, AZ",
    "Philadelphia, PA",
    "San Diego, CA",
    "Dallas, TX",
    "Austin, TX",
    "Jacksonville, FL",
    "Columbus, OH",
    "Charlotte, NC",
    "Indianapolis, IN",
    "Seattle, WA",
    "Denver, CO",
    "Boston, MA",
    "Nashville-Davidson, TN",
    "Portland, OR",
    "Las Vegas, NV",
    "Milwaukee, WI",
    "Sacramento, CA",
    "Atlanta, GA",
    "Kansas City, MO",
    "Raleigh, NC",
    "Miami, FL",
    "Minneapolis, MN",
    "Tampa, FL",
    "New Orleans, LA",
    "Cleveland, OH",
    "Pittsburgh, PA",
    "Cincinnati, OH",
    "St. Louis, MO",
    "Orlando, FL",
    "San Antonio, TX",
    "Salt Lake City, UT",
    "Richmond, VA",
    "Boise City, ID",
    "Birmingham, AL",
    "Grand Rapids, MI",
    "Greenville, SC",
    "Knoxville, TN",
    "Tucson, AZ",
    "Omaha, NE",
    "Des Moines, IA",
    "Charleston, SC",
    "Fort Collins, CO",
    "Asheville, NC",
    "Madison, WI",
    "Spokane, WA",
    "Bend, OR",
    "Boulder, CO",
    "Santa Barbara, CA"
  ],
  "canada": [
    "Toronto, ON",
    "Vancouver, BC",
    "Calgary, AB",
    "Edmonton, AB",
    "Ottawa, ON",
    "Montreal, QC",
    "Winnipeg, MB",
    "Halifax, NS",
    "Victoria, BC",
    "Hamilton, ON",
    "Kitchener, ON",
    "London, ON",
    "Kelowna, BC",
    "Saskatoon, SK",
    "Quebec City, QC"
  ]
}
```

**Step 3: Add search.mode field**

In the existing `"search"` block, add the mode field:

```json
"search": {
  "concurrency": 10,
  "mode": "lean"
}
```

**Step 4: Commit**

```bash
git add config/cities.json
git commit -m "feat: add lean_queries, lean_cities, and search mode to config"
```

---

### Task 3: Add search mode to Settings dataclass

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_settings_loads_search_mode():
    settings = Settings()
    assert settings.search_mode in ("lean", "extended")

def test_settings_loads_lean_cities():
    settings = Settings()
    assert "us" in settings.lean_cities
    assert "canada" in settings.lean_cities
    assert len(settings.lean_cities["us"]) >= 40
    assert len(settings.lean_cities["canada"]) >= 10

def test_settings_loads_lean_queries():
    settings = Settings()
    assert "health_wellness" in settings.lean_queries
    assert len(settings.lean_queries["health_wellness"]) >= 2
    assert len(settings.lean_queries["health_wellness"]) <= 5

def test_settings_get_cities_for_mode_lean():
    settings = Settings()
    settings.search_mode = "lean"
    cities = settings.get_cities_for_mode()
    # Should return lean cities
    assert len(cities["us"]) < len(settings.cities["us"])

def test_settings_get_cities_for_mode_extended():
    settings = Settings()
    settings.search_mode = "extended"
    cities = settings.get_cities_for_mode()
    # Should return all cities
    assert cities["us"] == settings.cities["us"]

def test_settings_get_queries_for_mode_lean():
    settings = Settings()
    settings.search_mode = "lean"
    queries = settings.get_queries_for_mode()
    assert len(queries["health_wellness"]) <= 5

def test_settings_get_queries_for_mode_extended():
    settings = Settings()
    settings.search_mode = "extended"
    queries = settings.get_queries_for_mode()
    assert len(queries["health_wellness"]) >= 10
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py::test_settings_loads_search_mode -v`
Expected: FAIL (AttributeError: no attribute 'search_mode')

**Step 3: Implement — add fields to Settings dataclass**

In `src/config.py`, add three new fields to the `Settings` dataclass (after `discovery`):

```python
search_mode: str = "lean"
lean_cities: dict = field(default_factory=dict)
lean_queries: dict = field(default_factory=dict)
```

In `__post_init__`, after the discovery settings block, add:

```python
# Load search mode
search_config = config.get("search", {})
self.search_mode = search_config.get("mode", "lean")

# Load lean cities
self.lean_cities = {
    "us": config.get("lean_cities", {}).get("us", []),
    "canada": config.get("lean_cities", {}).get("canada", []),
}

# Load lean queries
self.lean_queries = config.get("lean_queries", {})
```

Add two helper methods to `Settings`:

```python
def get_cities_for_mode(self) -> dict:
    """Return city lists based on current search mode."""
    if self.search_mode == "lean":
        return self.lean_cities
    return self.cities

def get_queries_for_mode(self) -> dict:
    """Return query lists based on current search mode."""
    if self.search_mode == "lean":
        return self.lean_queries
    return self.search_queries
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add search_mode, lean_cities, lean_queries to Settings"
```

---

### Task 4: Build the LocationScraper

**Files:**
- Create: `src/location_scraper.py`
- Create: `tests/test_location_scraper.py`

**Step 1: Write the failing tests**

Create `tests/test_location_scraper.py`:

```python
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

    # Should not make any HTTP request — returned from cache
    locations = await scraper.scrape("https://www.example.com")
    assert locations == cached
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_location_scraper.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'src.location_scraper')

**Step 3: Implement LocationScraper**

Create `src/location_scraper.py`:

```python
# src/location_scraper.py
"""Scrape brand websites for store location pages.

Finds location/store-finder pages on a brand's website and extracts
addresses from JSON-LD structured data, schema.org microdata, or HTML.
Results are cached for 90 days per domain.
"""
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Common paths where retailers list their store locations
LOCATION_PATHS = [
    "/locations",
    "/stores",
    "/store-locator",
    "/find-a-store",
    "/our-stores",
    "/store-finder",
    "/find-store",
    "/storelocator",
    "/all-locations",
    "/retail-locations",
]

# Keywords in nav links that suggest a location page
LOCATION_LINK_KEYWORDS = [
    "location", "store", "find", "visit", "near",
    "branch", "dealer", "retailer", "showroom",
]

# JSON-LD types that represent physical locations
LOCATION_SCHEMA_TYPES = {
    "Store", "LocalBusiness", "Restaurant", "RetailStore",
    "SportingGoodsStore", "HealthAndBeautyBusiness",
    "ShoppingCenter", "GroceryStore",
}

DEFAULT_CACHE_TTL_DAYS = 90


class LocationScraper:
    """Scrapes brand websites for store location data."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
        timeout: float = 15.0,
    ):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "location_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_seconds = cache_ttl_days * 86400
        self.timeout = timeout

    # ── Cache ────────────────────────────────────────────────────────

    def _cache_key(self, url: str) -> str:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return hashlib.sha256(domain.encode()).hexdigest()[:16]

    def _get_cached(self, url: str) -> Optional[list[dict]]:
        key = self._cache_key(url)
        cache_file = self.cache_dir / f"{key}.json"
        if not cache_file.exists():
            return None
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("_cached_at", 0) > self.cache_ttl_seconds:
                return None
            return data.get("locations")
        except (json.JSONDecodeError, KeyError):
            return None

    def _set_cached(self, url: str, locations: list[dict]):
        key = self._cache_key(url)
        cache_file = self.cache_dir / f"{key}.json"
        domain = urlparse(url).netloc.lower().lstrip("www.")
        cache_file.write_text(json.dumps({
            "_cached_at": time.time(),
            "_domain": domain,
            "locations": locations,
        }, indent=2))

    # ── URL Discovery ────────────────────────────────────────────────

    def _build_candidate_urls(self, base_url: str) -> list[str]:
        """Build list of candidate location page URLs to try."""
        parsed = urlparse(base_url if base_url.startswith(("http://", "https://")) else f"https://{base_url}")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return [f"{origin}{path}" for path in LOCATION_PATHS]

    def _find_location_links(self, html: str, base_url: str) -> list[str]:
        """Parse HTML for nav/footer links that point to location pages."""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            text = (a_tag.get_text() or "").lower().strip()
            href_lower = href.lower()

            if any(kw in text or kw in href_lower for kw in LOCATION_LINK_KEYWORDS):
                full_url = urljoin(base_url, href)
                if full_url not in links:
                    links.append(full_url)
        return links

    # ── HTML Parsing ─────────────────────────────────────────────────

    def _parse_locations_from_html(self, html: str) -> list[dict]:
        """Extract location data from HTML using JSON-LD, then fallback to address patterns."""
        locations = []

        # Try JSON-LD first (most reliable)
        locations = self._parse_json_ld(html)
        if locations:
            return locations

        # Try address-pattern extraction as fallback
        locations = self._parse_address_patterns(html)
        return locations

    def _parse_json_ld(self, html: str) -> list[dict]:
        """Extract locations from JSON-LD structured data."""
        soup = BeautifulSoup(html, "html.parser")
        locations = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            items = data if isinstance(data, list) else [data]

            # Handle @graph containers
            expanded = []
            for item in items:
                if isinstance(item, dict) and "@graph" in item:
                    expanded.extend(item["@graph"])
                else:
                    expanded.append(item)

            for item in expanded:
                if not isinstance(item, dict):
                    continue
                schema_type = item.get("@type", "")
                if isinstance(schema_type, list):
                    schema_type = schema_type[0] if schema_type else ""

                if schema_type in LOCATION_SCHEMA_TYPES:
                    loc = self._extract_address_from_schema(item)
                    if loc:
                        locations.append(loc)

        return locations

    def _extract_address_from_schema(self, item: dict) -> Optional[dict]:
        """Extract address dict from a schema.org JSON-LD item."""
        address = item.get("address", {})
        if isinstance(address, str):
            return {"name": item.get("name", ""), "address": address, "city": "", "state": ""}

        if isinstance(address, dict):
            street = address.get("streetAddress", "")
            city = address.get("addressLocality", "")
            state = address.get("addressRegion", "")
            if city or street:
                full_address = ", ".join(filter(None, [street, city, state]))
                return {
                    "name": item.get("name", ""),
                    "address": full_address,
                    "city": city,
                    "state": state,
                }
        return None

    def _parse_address_patterns(self, html: str) -> list[dict]:
        """Fallback: extract US/CA addresses via regex patterns."""
        # Match patterns like: 123 Main St, Boston, MA 02101
        us_pattern = r'(\d{1,5}\s+[\w\s.]+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Hwy|Circle|Loop|Trail)\.?)\s*,?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*,?\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?'
        locations = []
        seen = set()

        for match in re.finditer(us_pattern, html):
            street, city, state, zipcode = match.groups()
            key = f"{street.strip().lower()}|{city.strip().lower()}"
            if key not in seen:
                seen.add(key)
                locations.append({
                    "name": "",
                    "address": f"{street.strip()}, {city.strip()}, {state}",
                    "city": city.strip(),
                    "state": state,
                })

        return locations

    # ── Main Entry Point ─────────────────────────────────────────────

    async def scrape(self, website_url: str) -> list[dict]:
        """Scrape a brand's website for store locations.

        Returns list of {name, address, city, state} dicts, or [] if no
        locations found. Results are cached for 90 days by domain.
        """
        # Cache first
        cached = self._get_cached(website_url)
        if cached is not None:
            return cached

        if not website_url.startswith(("http://", "https://")):
            website_url = f"https://{website_url}"

        locations = []

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; LeadGen/1.0)"},
            ) as client:
                # Step 1: Try common location paths
                candidate_urls = self._build_candidate_urls(website_url)
                for url in candidate_urls:
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            locations = self._parse_locations_from_html(resp.text)
                            if locations:
                                break
                    except (httpx.TimeoutException, httpx.ConnectError):
                        continue

                # Step 2: If nothing found, check homepage for location nav links
                if not locations:
                    try:
                        resp = await client.get(website_url)
                        if resp.status_code == 200:
                            link_urls = self._find_location_links(resp.text, website_url)
                            for link_url in link_urls[:5]:  # Cap to avoid crawling entire site
                                try:
                                    resp2 = await client.get(link_url)
                                    if resp2.status_code == 200:
                                        locations = self._parse_locations_from_html(resp2.text)
                                        if locations:
                                            break
                                except (httpx.TimeoutException, httpx.ConnectError):
                                    continue
                    except (httpx.TimeoutException, httpx.ConnectError):
                        pass

        except Exception as e:
            logger.warning("Location scrape failed for %s: %s", website_url, e)

        # Cache result (even empty — avoids retrying sites with no locations)
        self._set_cached(website_url, locations)
        return locations
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_location_scraper.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/location_scraper.py tests/test_location_scraper.py
git commit -m "feat: add LocationScraper for website-based store location discovery"
```

---

### Task 5: Rewrite BrandExpander to use LocationScraper

**Files:**
- Modify: `src/brand_expander.py`
- Modify: `tests/test_brand_expander.py`

**Step 1: Write the failing tests**

Replace `tests/test_brand_expander.py` entirely:

```python
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


def test_should_expand_multi_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston", "Denver"], location_count=2) is True


def test_should_expand_many_locations_one_city():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=3) is True


def test_should_not_expand_single_location():
    expander = BrandExpander()
    assert expander.should_expand("Brand", cities_found=["Boston"], location_count=1) is False
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_brand_expander.py -v`
Expected: FAIL

**Step 3: Rewrite brand_expander.py**

Replace `src/brand_expander.py`:

```python
# src/brand_expander.py
"""Expand discovered brands by scraping their website for store locations.

Instead of burning SerpAPI searches to find a brand in every city,
we scrape the brand's own website for their store locator page.
Zero API cost.
"""
from pathlib import Path
from typing import Optional
from src.location_scraper import LocationScraper


class BrandExpander:
    """Expands discovered brands by scraping their website for all locations."""

    def __init__(self, cache_dir: Optional[Path] = None, **kwargs):
        # Accept and ignore api_key/concurrency for backwards compat during transition
        self.scraper = LocationScraper(cache_dir=cache_dir)

    async def expand_brand(
        self,
        brand_name: str,
        known_website: str,
        vertical: str = "",
        **kwargs,
    ) -> list[dict]:
        """Find all locations for a brand by scraping their website.

        Returns list of dicts matching pipeline format, or [] if no locations found.
        """
        if not known_website:
            return []

        locations = await self.scraper.scrape(known_website)

        return [
            {
                "name": loc.get("name") or brand_name,
                "address": loc.get("address", ""),
                "website": known_website,
                "place_id": None,
                "city": loc.get("city", ""),
                "vertical": vertical,
                "source": "location_scrape",
            }
            for loc in locations
        ]

    @staticmethod
    def should_expand(
        brand_name: str,
        cities_found: list[str],
        location_count: int,
        from_scrape: bool = False,
    ) -> bool:
        """Determine if a brand should be expanded."""
        if from_scrape:
            return True
        if len(cities_found) >= 2:
            return True
        if location_count >= 3:
            return True
        return False
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brand_expander.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/brand_expander.py tests/test_brand_expander.py
git commit -m "feat: rewrite BrandExpander to use LocationScraper instead of SerpAPI"
```

---

### Task 6: Update Discovery to use search modes

**Files:**
- Modify: `src/discovery.py`
- Modify: `tests/test_discovery.py`

**Step 1: Write the failing test**

Add to `tests/test_discovery.py`:

```python
@pytest.mark.asyncio
async def test_discovery_lean_mode_uses_lean_cities(mock_settings):
    """In lean mode, discovery should use lean city/query lists."""
    mock_settings.search_mode = "lean"
    mock_settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    mock_settings.lean_queries = {"running": ["running store"]}
    mock_settings.cities = {"us": ["Boston, MA", "New York, NY", "Chicago, IL"], "canada": []}
    mock_settings.search_queries = {"running": ["running store", "shoe store", "athletic store"]}
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    await discovery.run(verticals=["running"], countries=["us"])

                    # In lean mode, grid search should be skipped
                    mock_grid.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_extended_mode_uses_all_cities(mock_settings):
    """In extended mode, discovery should use full city/query lists and grid search."""
    mock_settings.search_mode = "extended"
    mock_settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    mock_settings.lean_queries = {"running": ["running store"]}
    mock_settings.cities = {"us": ["Boston, MA", "New York, NY"], "canada": []}
    mock_settings.search_queries = {"running": ["running store", "shoe store"]}
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True
    mock_settings.discovery.nearby_grid_offset_km = 20
    mock_settings.discovery.nearby_grid_radius_meters = 15000
    mock_settings.discovery.nearby_grid_points = "cardinal"

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    await discovery.run(verticals=["running"], countries=["us"])

                    # In extended mode, grid search SHOULD be called
                    mock_grid.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery.py::test_discovery_lean_mode_uses_lean_cities -v`
Expected: FAIL

**Step 3: Update discovery.py**

Key changes to `src/discovery.py`:

1. In `_build_city_list`, use `settings.get_cities_for_mode()` instead of `settings.cities`.
2. In `_run_search`, use `settings.get_queries_for_mode()` instead of `settings.search_queries`.
3. In `run()`, skip grid search when `settings.search_mode == "lean"`.
4. In `_run_brand_expansion`, remove the SerpAPI searcher — use `self.expander.expand_brand()` which now uses `LocationScraper` internally. Remove the `cities` parameter since expansion no longer searches city-by-city.
5. Remove `self.searcher` from `__init__` if it's only used for brand expansion (check: it's also used in `_run_search` and `_run_nearby_grid_search`, so keep it).

Update `_build_city_list`:
```python
def _build_city_list(self, countries: list[str]) -> list[str]:
    """Build list of cities based on current search mode."""
    mode_cities = self.settings.get_cities_for_mode()
    cities = []
    for country in countries:
        cities.extend(mode_cities.get(country, []))
    return cities
```

Update `_run_search` to use mode queries:
```python
async def _run_search(self, verticals, countries):
    # ... existing code but change:
    queries = self.settings.get_queries_for_mode()
    # ... use queries instead of self.settings.search_queries
```

Update `run()` to skip grid in lean mode:
```python
# Stage 1b: Nearby grid search (extended mode only)
if self.settings.search_mode == "extended":
    console.print("[bold cyan]Discovery Stage 1b:[/bold cyan] Nearby Grid Search")
    grid_results = await self._run_nearby_grid_search(verticals, countries)
    all_places.extend(grid_results)
    console.print(f"  [green]Found {len(grid_results)} places from grid search[/green]")
else:
    console.print("[dim]  Skipping grid search (lean mode)[/dim]")
```

Update `_run_brand_expansion` — simplify since no longer city-by-city:
```python
async def _run_brand_expansion(self, places, countries):
    results = []
    # Group by website domain to find multi-location brands
    from collections import defaultdict
    by_domain = defaultdict(list)

    for place in places:
        if place.get("website"):
            domain = self.deduplicator._normalize_domain(place["website"])
            if domain:
                by_domain[domain].append(place)

    brands_to_expand = []
    for domain, domain_places in by_domain.items():
        cities_found = list(set(p["city"] for p in domain_places))
        if self.expander.should_expand(
            brand_name=domain_places[0]["name"],
            cities_found=cities_found,
            location_count=len(domain_places)
        ):
            brands_to_expand.append({
                "name": domain_places[0]["name"],
                "website": domain_places[0]["website"],
                "vertical": domain_places[0]["vertical"],
            })

    brands_to_process = brands_to_expand[:BRANDS_TO_EXPAND_LIMIT]
    console.print(f"  [dim]Expanding {len(brands_to_process)} promising brands via website scraping...[/dim]")

    if not brands_to_process:
        return results

    with Progress(...) as progress:
        task = progress.add_task(...)
        for brand in brands_to_process:
            progress.update(task, description=f"[cyan]Scraping[/cyan] {brand['name']}")
            try:
                expanded = await self.expander.expand_brand(
                    brand_name=brand["name"],
                    known_website=brand["website"],
                    vertical=brand["vertical"],
                )
                results.extend(expanded)
            except Exception as e:
                if not _is_transient_error(e):
                    logger.warning("Brand expansion failed for %s: %s", brand["name"], e)
            progress.advance(task)

    return results
```

**Step 4: Run all discovery tests**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/discovery.py tests/test_discovery.py
git commit -m "feat: wire search modes into Discovery, use LocationScraper for expansion"
```

---

### Task 7: Add search mode to Pipeline.run() and checkpoint

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Update Pipeline.run() signature**

Add `search_mode` parameter to `Pipeline.run()`:

```python
async def run(
    self,
    verticals: list[str] = ["health_wellness", "sporting_goods", "apparel"],
    countries: list[str] = ["us", "canada"],
    resume_checkpoint: Optional[Path] = None,
    search_mode: Optional[str] = None,
) -> str:
```

At the top of `run()`, before any stage runs, apply the mode:

```python
if search_mode:
    settings.search_mode = search_mode
```

Also save `search_mode` in `_snapshot_settings()` and restore in `apply_settings()`.

**Step 2: Run existing pipeline tests**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: All PASS (signature change is backwards-compatible)

**Step 3: Commit**

```bash
git add src/pipeline.py
git commit -m "feat: add search_mode parameter to Pipeline.run()"
```

---

### Task 8: Add search mode to interactive menu and CLI

**Files:**
- Modify: `src/__main__.py`

**Step 1: Add mode selection to _interactive_new_run()**

Between Step 2 (countries) and Step 3 (advanced settings), add a new step:

```python
# Step 2b: Search mode
console.print("\n[bold cyan]Step 2b:[/bold cyan] Search scope\n")

mode_choice = inquirer.select(
    message="Select search mode:",
    choices=[
        {"name": "Lean — ~50 major cities, 3-4 queries/vertical (budget-friendly)", "value": "lean"},
        {"name": "Extended — all 890+ cities, full query lists (comprehensive)", "value": "extended"},
        Separator(),
        {"name": BACK_OPTION, "value": "back"},
        {"name": MAIN_MENU_OPTION, "value": "main_menu"},
    ],
    default="lean",
).execute()

if mode_choice == "main_menu":
    nav.clear()
    return
if mode_choice == "back":
    nav.clear()
    return _interactive_new_run()

settings.search_mode = mode_choice
```

Pass `search_mode` to `pipeline.run()`:

```python
output_file = asyncio.run(pipeline.run(
    verticals=vertical_list,
    countries=country_list,
    search_mode=mode_choice,
))
```

**Step 2: Add --mode flag to CLI run command**

Add to the `run()` command's parameters:

```python
mode: str = typer.Option(
    "lean",
    "--mode", "-m",
    help="Search mode: lean (~50 cities, 3-4 queries) or extended (all cities, full queries)"
),
```

And pass it through:

```python
output_file = asyncio.run(pipeline.run(
    verticals=vertical_list,
    countries=country_list,
    search_mode=mode,
))
```

**Step 3: Update show_summary() to display mode info**

Add mode and estimated search count to `show_summary()`:

```python
# Search mode
table.add_row("Search Mode", settings.search_mode.capitalize())

# Use mode-appropriate city/query counts
mode_cities = settings.get_cities_for_mode()
cities = []
for country in countries:
    cities.extend(mode_cities.get(country, []))
cities_count = len(cities)

mode_queries = settings.get_queries_for_mode()
queries = []
for vertical in verticals:
    queries.extend(mode_queries.get(vertical, []))
queries_count = len(queries)

total_searches = cities_count * queries_count
table.add_row("Cities", str(cities_count))
table.add_row("Queries per city", str(queries_count))
table.add_row("Est. SerpAPI Calls", f"~{total_searches}")
```

**Step 4: Run the app to verify menu works**

Run: `python -m src --help`
Expected: Shows `--mode` flag in help text

**Step 5: Commit**

```bash
git add src/__main__.py
git commit -m "feat: add search mode selection to interactive menu and CLI"
```

---

### Task 9: Run full test suite and fix any breakage

**Files:**
- All test files

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

**Step 2: Fix any failures**

Common issues to watch for:
- `BrandExpander` constructor changed — tests that pass `api_key=` still work (accepted via `**kwargs`)
- `discovery.py` tests that mock `_run_search` may need `mock_settings.search_mode` set
- Import errors if `beautifulsoup4` isn't installed

**Step 3: Install bs4 if needed**

Run: `pip install beautifulsoup4` (and add to requirements.txt if it exists)

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: test suite passing after search mode + location scraper changes"
```
