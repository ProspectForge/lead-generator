# Enhanced Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Increase lead discovery from ~170 to 700-1,000 qualified leads using hybrid Google Places + web scraping + brand expansion.

**Architecture:** Three-stage discovery funnel: (1) Enhanced Google Places with niche queries and Nearby Search, (2) Web scraping of franchise directories and industry associations, (3) Brand expansion to find all locations. Results merge through deduplication before entering existing pipeline.

**Tech Stack:** Python 3.12, httpx (async HTTP), BeautifulSoup4 (scraping), rapidfuzz (fuzzy matching), existing Firecrawl integration

---

## Task 1: Expand City Configuration

**Files:**
- Modify: `config/cities.json`

**Step 1: Add suburban US cities**

Add these cities to the `us` array in `config/cities.json`:

```json
"Scottsdale, AZ",
"Boulder, CO",
"Naperville, IL",
"Plano, TX",
"Bellevue, WA",
"Santa Monica, CA",
"Pasadena, CA",
"Irvine, CA",
"Newport Beach, CA",
"Stamford, CT",
"Greenwich, CT",
"White Plains, NY",
"Hoboken, NJ",
"Princeton, NJ",
"Bethesda, MD",
"Alexandria, VA",
"Arlington, VA",
"Boca Raton, FL",
"Naples, FL",
"Sarasota, FL"
```

**Step 2: Add suburban Canadian cities**

Add these cities to the `canada` array:

```json
"Coquitlam, BC",
"Port Coquitlam, BC",
"Burnaby, BC",
"Surrey, BC",
"Richmond, BC",
"North Vancouver, BC",
"Mississauga, ON",
"Markham, ON",
"Vaughan, ON",
"Oakville, ON",
"Burlington, ON",
"Laval, QC",
"Longueuil, QC",
"Brossard, QC",
"Saskatoon, SK",
"Regina, SK",
"Red Deer, AB"
```

**Step 3: Verify config loads**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -c "from src.config import settings; print(f'US: {len(settings.cities[\"us\"])} cities, Canada: {len(settings.cities[\"canada\"])} cities')"`

Expected: `US: 56 cities, Canada: 32 cities`

**Step 4: Commit**

```bash
git add config/cities.json
git commit -m "config: expand city coverage with suburban markets"
```

---

## Task 2: Create Niche Queries Configuration

**Files:**
- Modify: `config/cities.json`

**Step 1: Expand search_queries with niche terms**

Replace the `search_queries` section with expanded niche queries:

```json
"search_queries": {
  "health_wellness": [
    "supplement store",
    "vitamin shop",
    "health food store",
    "nutrition store",
    "natural health store",
    "organic grocery",
    "wellness store",
    "herbal supplement shop"
  ],
  "sporting_goods": [
    "sporting goods store",
    "outdoor gear store",
    "athletic store",
    "sports equipment store",
    "running shoe store",
    "golf shop",
    "tennis pro shop",
    "ski equipment store",
    "hockey store",
    "soccer store",
    "fishing tackle shop",
    "archery store",
    "climbing gear store",
    "surf shop",
    "lacrosse store"
  ],
  "apparel": [
    "clothing boutique",
    "fashion store",
    "apparel store",
    "clothing store",
    "yoga apparel store",
    "activewear store",
    "athleisure boutique",
    "workwear store",
    "denim shop",
    "outdoor clothing store"
  ],
  "outdoor_camping": [
    "camping store",
    "hiking gear store",
    "backpacking store",
    "kayak shop",
    "canoe outfitter",
    "outdoor adventure store",
    "mountaineering shop"
  ],
  "running_athletic": [
    "running store",
    "triathlon store",
    "marathon store",
    "track and field store"
  ],
  "cycling": [
    "bike shop",
    "bicycle store",
    "cycling store",
    "mountain bike shop"
  ]
}
```

**Step 2: Verify queries load**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -c "from src.config import settings; total = sum(len(q) for q in settings.search_queries.values()); print(f'Total queries: {total}')"`

Expected: `Total queries: ~45` (varies based on exact count)

**Step 3: Commit**

```bash
git add config/cities.json
git commit -m "config: expand search queries with niche retail terms"
```

---

## Task 3: Add Nearby Search to PlacesSearcher

**Files:**
- Modify: `src/places_search.py`
- Create: `tests/test_places_search.py`

**Step 1: Write the failing test**

```python
# tests/test_places_search.py
import pytest
from unittest.mock import AsyncMock, patch
from src.places_search import PlacesSearcher, PlaceResult

@pytest.fixture
def mock_nearby_response():
    return {
        "places": [
            {
                "displayName": {"text": "Local Running Store"},
                "formattedAddress": "456 Suburb Ave, Chicago, IL 60601",
                "websiteUri": "https://localrunning.com",
                "id": "nearby123",
                "location": {"latitude": 41.8781, "longitude": -87.6298}
            }
        ]
    }

@pytest.mark.asyncio
async def test_nearby_search_returns_results(mock_nearby_response):
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_nearby_response

        results = await searcher.nearby_search(
            latitude=41.8781,
            longitude=-87.6298,
            radius_meters=5000,
            included_types=["sporting_goods_store"],
            vertical="sporting_goods"
        )

        assert len(results) == 1
        assert results[0].name == "Local Running Store"
        assert results[0].place_id == "nearby123"

@pytest.mark.asyncio
async def test_nearby_search_uses_correct_endpoint():
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"places": []}

        await searcher.nearby_search(
            latitude=41.8781,
            longitude=-87.6298,
            radius_meters=5000,
            included_types=["sporting_goods_store"]
        )

        # Verify the payload structure
        call_args = mock_request.call_args
        payload = call_args[0][0]
        assert "locationRestriction" in payload
        assert payload["locationRestriction"]["circle"]["radius"] == 5000
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_places_search.py -v`

Expected: FAIL with "PlacesSearcher has no attribute 'nearby_search'"

**Step 3: Add nearby_search method to PlacesSearcher**

Add to `src/places_search.py` after the `search` method:

```python
    NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

    # Google Places type mapping for retail
    RETAIL_TYPES = {
        "sporting_goods": ["sporting_goods_store", "bicycle_store"],
        "health_wellness": ["health_food_store", "drugstore"],
        "apparel": ["clothing_store", "shoe_store"],
        "outdoor_camping": ["camping_store", "outdoor_recreation_store"],
    }

    async def nearby_search(
        self,
        latitude: float,
        longitude: float,
        radius_meters: int = 5000,
        included_types: list[str] = None,
        vertical: str = ""
    ) -> list[PlaceResult]:
        """Search for places within a radius of a location."""
        payload = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters
                }
            },
            "maxResultCount": 20
        }

        if included_types:
            payload["includedTypes"] = included_types

        # Use nearby-specific headers
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri,places.id,places.location"
        }

        data = await self._make_request(payload, url=self.NEARBY_URL, headers=headers)
        places = data.get("places", [])

        results = []
        for place in places:
            # Derive city from address (last part before zip)
            address = place.get("formattedAddress", "")
            city = self._extract_city_from_address(address)

            results.append(PlaceResult(
                name=place.get("displayName", {}).get("text", ""),
                address=address,
                website=place.get("websiteUri"),
                place_id=place.get("id", ""),
                city=city,
                vertical=vertical
            ))

        return results

    def _extract_city_from_address(self, address: str) -> str:
        """Extract city name from formatted address."""
        parts = address.split(",")
        if len(parts) >= 2:
            # Usually: "123 Main St, City, State ZIP"
            return parts[-2].strip() if len(parts) >= 2 else ""
        return ""
```

**Step 4: Update _make_request to accept custom URL and headers**

Modify `_make_request` signature:

```python
    async def _make_request(self, payload: dict, url: str = None, headers: dict = None) -> dict:
        request_url = url or self.BASE_URL
        request_headers = headers or self.headers
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        request_url,
                        headers=request_headers,
                        json=payload
                    )
                    response.raise_for_status()
                    return response.json()
            # ... rest unchanged
```

**Step 5: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_places_search.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add src/places_search.py tests/test_places_search.py
git commit -m "feat: add nearby search API to PlacesSearcher"
```

---

## Task 4: Create Deduplicator Module

**Files:**
- Create: `src/deduplicator.py`
- Create: `tests/test_deduplicator.py`

**Step 1: Write the failing test**

```python
# tests/test_deduplicator.py
import pytest
from src.deduplicator import Deduplicator, MergedPlace

@pytest.fixture
def duplicate_places():
    return [
        {"name": "Fleet Feet Boston", "address": "123 Main St", "website": "https://fleetfeet.com", "place_id": "abc123", "city": "Boston, MA", "vertical": "running", "source": "google_places"},
        {"name": "Fleet Feet", "address": "123 Main Street", "website": "https://fleetfeet.com", "place_id": None, "city": "Boston, MA", "vertical": "sporting_goods", "source": "franchise_scrape"},
        {"name": "Nike Store", "address": "456 Broadway", "website": "https://nike.com", "place_id": "def456", "city": "Boston, MA", "vertical": "apparel", "source": "google_places"},
    ]

def test_deduplicates_by_website_and_city(duplicate_places):
    deduplicator = Deduplicator()
    merged = deduplicator.deduplicate(duplicate_places)

    # Should merge the two Fleet Feet entries
    assert len(merged) == 2

    fleet_feet = next(m for m in merged if "fleet" in m.name.lower())
    assert fleet_feet.place_id == "abc123"  # Prefers Google Places data
    assert "google_places" in fleet_feet.sources
    assert "franchise_scrape" in fleet_feet.sources

def test_preserves_unique_places(duplicate_places):
    deduplicator = Deduplicator()
    merged = deduplicator.deduplicate(duplicate_places)

    nike = next(m for m in merged if "nike" in m.name.lower())
    assert nike.place_id == "def456"
    assert len(nike.sources) == 1

def test_normalizes_website_domains():
    deduplicator = Deduplicator()

    assert deduplicator._normalize_domain("https://www.fleetfeet.com/store") == "fleetfeet.com"
    assert deduplicator._normalize_domain("http://fleetfeet.com") == "fleetfeet.com"
    assert deduplicator._normalize_domain("fleetfeet.com/about") == "fleetfeet.com"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_deduplicator.py -v`

Expected: FAIL with "No module named 'src.deduplicator'"

**Step 3: Create deduplicator module**

```python
# src/deduplicator.py
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

@dataclass
class MergedPlace:
    name: str
    address: str
    website: Optional[str]
    place_id: Optional[str]
    city: str
    vertical: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 1.0

class Deduplicator:
    """Merges places from multiple sources, removing duplicates."""

    def _normalize_domain(self, url: str) -> str:
        """Extract and normalize domain from URL."""
        if not url:
            return ""

        # Add scheme if missing
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _normalize_name(self, name: str) -> str:
        """Normalize business name for comparison."""
        name = name.lower().strip()
        # Remove common suffixes
        suffixes = [" inc", " llc", " ltd", " corp", " store", " shop", " boutique"]
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.strip()

    def _create_key(self, place: dict) -> str:
        """Create a deduplication key for a place."""
        domain = self._normalize_domain(place.get("website", ""))
        city = place.get("city", "").lower().strip()

        if domain and city:
            return f"{domain}|{city}"

        # Fallback to normalized name + city
        name = self._normalize_name(place.get("name", ""))
        return f"{name}|{city}"

    def deduplicate(self, places: list[dict]) -> list[MergedPlace]:
        """Deduplicate and merge places from multiple sources."""
        grouped: dict[str, list[dict]] = {}

        for place in places:
            key = self._create_key(place)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(place)

        merged = []
        for key, group in grouped.items():
            merged.append(self._merge_group(group))

        return merged

    def _merge_group(self, group: list[dict]) -> MergedPlace:
        """Merge a group of duplicate places into one."""
        # Sort by source priority: google_places > brand_expansion > scraped
        priority = {"google_places": 0, "brand_expansion": 1}
        group.sort(key=lambda p: priority.get(p.get("source", ""), 2))

        # Take best values from each field
        primary = group[0]
        sources = list(set(p.get("source", "unknown") for p in group))

        # Find best place_id (prefer non-None)
        place_id = next((p.get("place_id") for p in group if p.get("place_id")), None)

        # Find best website
        website = next((p.get("website") for p in group if p.get("website")), None)

        return MergedPlace(
            name=primary.get("name", ""),
            address=primary.get("address", ""),
            website=website,
            place_id=place_id,
            city=primary.get("city", ""),
            vertical=primary.get("vertical", ""),
            sources=sources,
            confidence=1.0 if len(group) == 1 else 0.95
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_deduplicator.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/deduplicator.py tests/test_deduplicator.py
git commit -m "feat: add deduplicator module for multi-source merging"
```

---

## Task 5: Create Brand Expander Module

**Files:**
- Create: `src/brand_expander.py`
- Create: `tests/test_brand_expander.py`

**Step 1: Write the failing test**

```python
# tests/test_brand_expander.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.brand_expander import BrandExpander
from src.places_search import PlaceResult

@pytest.fixture
def mock_search_results():
    return {
        "Toronto, ON": [
            PlaceResult(name="Fleet Feet Toronto", address="123 Queen St", website="https://fleetfeet.com", place_id="tor1", city="Toronto, ON", vertical="running")
        ],
        "Vancouver, BC": [
            PlaceResult(name="Fleet Feet Vancouver", address="456 Robson St", website="https://fleetfeet.com", place_id="van1", city="Vancouver, BC", vertical="running")
        ],
        "Montreal, QC": []  # No results
    }

@pytest.mark.asyncio
async def test_expand_brand_searches_all_cities(mock_search_results):
    expander = BrandExpander(api_key="test_key")
    cities = ["Toronto, ON", "Vancouver, BC", "Montreal, QC"]

    async def mock_search(query, city, vertical=""):
        return mock_search_results.get(city, [])

    with patch.object(expander.searcher, 'search', side_effect=mock_search):
        results = await expander.expand_brand(
            brand_name="Fleet Feet",
            known_website="https://fleetfeet.com",
            cities=cities,
            vertical="running"
        )

        assert len(results) == 2  # Found in 2 of 3 cities
        assert all("fleet" in r["name"].lower() for r in results)

@pytest.mark.asyncio
async def test_expand_brand_filters_by_domain():
    expander = BrandExpander(api_key="test_key")

    mixed_results = [
        PlaceResult(name="Fleet Feet", address="123 St", website="https://fleetfeet.com", place_id="a", city="NYC", vertical="running"),
        PlaceResult(name="Other Running Store", address="456 St", website="https://other.com", place_id="b", city="NYC", vertical="running"),
    ]

    with patch.object(expander.searcher, 'search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mixed_results

        results = await expander.expand_brand(
            brand_name="Fleet Feet",
            known_website="https://fleetfeet.com",
            cities=["New York, NY"],
            vertical="running"
        )

        # Should only return the Fleet Feet result
        assert len(results) == 1
        assert "fleetfeet.com" in results[0]["website"]
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_expander.py -v`

Expected: FAIL with "No module named 'src.brand_expander'"

**Step 3: Create brand expander module**

```python
# src/brand_expander.py
import asyncio
from urllib.parse import urlparse
from src.places_search import PlacesSearcher, PlaceResult

class BrandExpander:
    """Expands discovered brands to find all their locations."""

    def __init__(self, api_key: str, concurrency: int = 5):
        self.searcher = PlacesSearcher(api_key=api_key)
        self.concurrency = concurrency
        self.delay_ms = 100

    def _normalize_domain(self, url: str) -> str:
        """Extract domain from URL for comparison."""
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs have the same domain."""
        d1 = self._normalize_domain(url1)
        d2 = self._normalize_domain(url2)
        return d1 and d2 and d1 == d2

    async def expand_brand(
        self,
        brand_name: str,
        known_website: str,
        cities: list[str],
        vertical: str = ""
    ) -> list[dict]:
        """Search for a brand across all cities and return matching locations."""
        semaphore = asyncio.Semaphore(self.concurrency)
        all_results = []

        async def search_city(city: str) -> list[dict]:
            async with semaphore:
                try:
                    results = await self.searcher.search(brand_name, city, vertical=vertical)
                    # Filter to only matching domain
                    matching = []
                    for r in results:
                        if self._same_domain(r.website, known_website):
                            matching.append({
                                "name": r.name,
                                "address": r.address,
                                "website": r.website,
                                "place_id": r.place_id,
                                "city": r.city,
                                "vertical": r.vertical,
                                "source": "brand_expansion"
                            })
                    await asyncio.sleep(self.delay_ms / 1000)
                    return matching
                except Exception:
                    return []

        # Run searches in parallel
        tasks = [search_city(city) for city in cities]
        results_lists = await asyncio.gather(*tasks)

        # Flatten
        for result_list in results_lists:
            all_results.extend(result_list)

        return all_results

    def should_expand(
        self,
        brand_name: str,
        cities_found: list[str],
        location_count: int,
        from_scrape: bool = False
    ) -> bool:
        """Determine if a brand should be expanded to all cities."""
        # Expand if found via scraping (franchise directory, etc.)
        if from_scrape:
            return True

        # Expand if found in 2+ cities
        if len(cities_found) >= 2:
            return True

        # Expand if 3+ locations in a single city
        if location_count >= 3:
            return True

        return False
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_expander.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/brand_expander.py tests/test_brand_expander.py
git commit -m "feat: add brand expander to find all brand locations"
```

---

## Task 6: Create Base Scraper Infrastructure

**Files:**
- Create: `src/scraper/__init__.py`
- Create: `src/scraper/base.py`
- Create: `tests/test_scraper_base.py`

**Step 1: Write the failing test**

```python
# tests/test_scraper_base.py
import pytest
from unittest.mock import AsyncMock, patch
from src.scraper.base import BaseScraper, ScrapedBrand

@pytest.mark.asyncio
async def test_scraper_fetches_and_parses():
    class TestScraper(BaseScraper):
        async def scrape(self) -> list[ScrapedBrand]:
            html = await self._fetch("https://example.com")
            return [ScrapedBrand(name="Test Brand", category="sporting_goods", website="https://test.com", source="test")]

    scraper = TestScraper(firecrawl_api_key="test_key")

    with patch.object(scraper, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "<html><body>Test</body></html>"

        results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].name == "Test Brand"

def test_scraped_brand_to_dict():
    brand = ScrapedBrand(
        name="Fleet Feet",
        category="running",
        website="https://fleetfeet.com",
        source="franchise_directory",
        estimated_locations=50
    )

    d = brand.to_dict()

    assert d["name"] == "Fleet Feet"
    assert d["source"] == "franchise_directory"
    assert d["estimated_locations"] == 50
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_scraper_base.py -v`

Expected: FAIL with "No module named 'src.scraper'"

**Step 3: Create scraper package and base module**

```python
# src/scraper/__init__.py
from .base import BaseScraper, ScrapedBrand

__all__ = ["BaseScraper", "ScrapedBrand"]
```

```python
# src/scraper/base.py
import httpx
from dataclasses import dataclass, asdict
from typing import Optional
from abc import ABC, abstractmethod

@dataclass
class ScrapedBrand:
    name: str
    category: str
    website: Optional[str]
    source: str
    estimated_locations: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

class BaseScraper(ABC):
    """Base class for web scrapers using Firecrawl."""

    FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

    def __init__(self, firecrawl_api_key: str):
        self.api_key = firecrawl_api_key
        self.headers = {
            "Authorization": f"Bearer {firecrawl_api_key}",
            "Content-Type": "application/json"
        }

    async def _fetch(self, url: str) -> str:
        """Fetch a URL using Firecrawl and return markdown content."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.FIRECRAWL_URL,
                headers=self.headers,
                json={"url": url, "formats": ["markdown"]}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("markdown", "")

    @abstractmethod
    async def scrape(self) -> list[ScrapedBrand]:
        """Scrape and return list of discovered brands."""
        pass
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_scraper_base.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/scraper/__init__.py src/scraper/base.py tests/test_scraper_base.py
git commit -m "feat: add base scraper infrastructure"
```

---

## Task 7: Create Best-Of Article Scraper

**Files:**
- Create: `src/scraper/bestof_scraper.py`
- Create: `tests/test_bestof_scraper.py`

**Step 1: Write the failing test**

```python
# tests/test_bestof_scraper.py
import pytest
from unittest.mock import AsyncMock, patch
from src.scraper.bestof_scraper import BestOfScraper

@pytest.fixture
def mock_search_results():
    return """
    # Best Running Stores in Boston

    1. **Marathon Sports** - The premier running store in New England
       Located at 123 Boylston St. marathonsports.com

    2. **Fleet Feet Boston** - Great selection of shoes
       Visit fleetfeet.com for more info

    3. **Heartbreak Hill Running** - Local favorite
       heartbreakhill.com
    """

@pytest.mark.asyncio
async def test_extracts_brand_names_from_article(mock_search_results):
    scraper = BestOfScraper(firecrawl_api_key="test_key")

    with patch.object(scraper, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_search_results

        results = await scraper.scrape_city("Boston, MA", "running store")

        assert len(results) >= 2
        names = [r.name.lower() for r in results]
        assert any("marathon" in n for n in names)

@pytest.mark.asyncio
async def test_extracts_websites_from_article(mock_search_results):
    scraper = BestOfScraper(firecrawl_api_key="test_key")

    with patch.object(scraper, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_search_results

        results = await scraper.scrape_city("Boston, MA", "running store")

        websites = [r.website for r in results if r.website]
        assert any("marathonsports.com" in w for w in websites)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_bestof_scraper.py -v`

Expected: FAIL with "No module named 'src.scraper.bestof_scraper'"

**Step 3: Create best-of scraper**

```python
# src/scraper/bestof_scraper.py
import re
from typing import Optional
from .base import BaseScraper, ScrapedBrand

class BestOfScraper(BaseScraper):
    """Scrapes 'best of' articles to find local retailers."""

    SEARCH_TEMPLATES = [
        "best {query} in {city}",
        "top {query} {city}",
        "independent {query} {city}",
    ]

    # Patterns to extract business names
    NAME_PATTERNS = [
        r'\*\*([^*]+)\*\*',  # **Bold Name**
        r'^\d+\.\s+(.+?)(?:\s*[-–—]|$)',  # 1. Name - description
        r'^#+\s+(.+?)$',  # # Header Name
    ]

    # Pattern to extract URLs
    URL_PATTERN = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)'

    async def scrape_city(self, city: str, query: str) -> list[ScrapedBrand]:
        """Scrape best-of articles for a specific city and query."""
        brands = []

        # Build search URL
        search_query = f"best {query} in {city}"
        search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"

        try:
            content = await self._fetch(search_url)
            brands.extend(self._extract_brands(content, city, query))
        except Exception:
            pass

        return brands

    def _extract_brands(self, content: str, city: str, query: str) -> list[ScrapedBrand]:
        """Extract brand names and websites from article content."""
        brands = []
        seen_names = set()

        lines = content.split('\n')

        for i, line in enumerate(lines):
            # Try to extract a business name
            name = self._extract_name(line)
            if not name or len(name) < 3 or len(name) > 100:
                continue

            # Skip if already seen
            normalized = name.lower().strip()
            if normalized in seen_names:
                continue
            seen_names.add(normalized)

            # Try to find a website in nearby lines
            context = '\n'.join(lines[max(0, i-1):min(len(lines), i+3)])
            website = self._extract_website(context)

            # Skip generic terms
            if self._is_generic(name):
                continue

            brands.append(ScrapedBrand(
                name=name,
                category=query,
                website=website,
                source="bestof_article"
            ))

        return brands

    def _extract_name(self, line: str) -> Optional[str]:
        """Extract a business name from a line."""
        for pattern in self.NAME_PATTERNS:
            match = re.search(pattern, line, re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Clean up
                name = re.sub(r'\[.*?\]', '', name)  # Remove markdown links
                name = re.sub(r'\(.*?\)', '', name)  # Remove parentheticals
                return name.strip()
        return None

    def _extract_website(self, content: str) -> Optional[str]:
        """Extract a website URL from content."""
        match = re.search(self.URL_PATTERN, content)
        if match:
            domain = match.group(1)
            # Skip common non-business domains
            skip_domains = ['google.com', 'facebook.com', 'instagram.com', 'twitter.com', 'yelp.com']
            if not any(skip in domain for skip in skip_domains):
                return f"https://{domain}"
        return None

    def _is_generic(self, name: str) -> bool:
        """Check if a name is too generic to be a business."""
        generic = ['store', 'shop', 'best', 'top', 'list', 'guide', 'review']
        name_lower = name.lower()
        return any(name_lower == g or name_lower == f"the {g}" for g in generic)

    async def scrape(self) -> list[ScrapedBrand]:
        """Not used - use scrape_city instead."""
        return []
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_bestof_scraper.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/scraper/bestof_scraper.py tests/test_bestof_scraper.py
git commit -m "feat: add best-of article scraper"
```

---

## Task 8: Create Discovery Orchestrator

**Files:**
- Create: `src/discovery.py`
- Create: `tests/test_discovery.py`

**Step 1: Write the failing test**

```python
# tests/test_discovery.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.discovery import Discovery

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.google_places_api_key = "test_key"
    settings.firecrawl_api_key = "test_key"
    settings.cities = {"us": ["Boston, MA"], "canada": ["Toronto, ON"]}
    settings.search_queries = {"running": ["running store"]}
    settings.search_concurrency = 2
    return settings

@pytest.mark.asyncio
async def test_discovery_runs_google_places(mock_settings):
    discovery = Discovery(mock_settings)

    mock_results = [{"name": "Test Store", "city": "Boston, MA", "website": "https://test.com", "source": "google_places"}]

    with patch.object(discovery, '_run_google_places', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = mock_results
        with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = []
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                results = await discovery.run(verticals=["running"], countries=["us"])

                mock_gp.assert_called_once()
                assert len(results) >= 1

@pytest.mark.asyncio
async def test_discovery_deduplicates_results(mock_settings):
    discovery = Discovery(mock_settings)

    # Same store from two sources
    gp_results = [{"name": "Fleet Feet", "city": "Boston, MA", "website": "https://fleetfeet.com", "place_id": "abc", "source": "google_places", "vertical": "running", "address": "123 St"}]
    scrape_results = [{"name": "Fleet Feet Boston", "city": "Boston, MA", "website": "https://fleetfeet.com", "place_id": None, "source": "bestof", "vertical": "running", "address": ""}]

    with patch.object(discovery, '_run_google_places', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = gp_results
        with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = scrape_results
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                results = await discovery.run(verticals=["running"], countries=["us"])

                # Should dedupe to 1 result
                assert len(results) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_discovery.py -v`

Expected: FAIL with "No module named 'src.discovery'"

**Step 3: Create discovery orchestrator**

```python
# src/discovery.py
import asyncio
from dataclasses import asdict
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.places_search import PlacesSearcher
from src.brand_expander import BrandExpander
from src.deduplicator import Deduplicator, MergedPlace
from src.scraper.bestof_scraper import BestOfScraper

console = Console()

class Discovery:
    """Orchestrates multi-source lead discovery."""

    def __init__(self, settings):
        self.settings = settings
        self.searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        self.expander = BrandExpander(api_key=settings.google_places_api_key)
        self.deduplicator = Deduplicator()
        self.bestof_scraper = BestOfScraper(firecrawl_api_key=settings.firecrawl_api_key)

    async def run(
        self,
        verticals: list[str],
        countries: list[str]
    ) -> list[dict]:
        """Run full discovery pipeline."""
        all_places = []

        # Stage 1: Google Places search
        console.print("[bold cyan]Discovery Stage 1:[/bold cyan] Google Places Search")
        gp_results = await self._run_google_places(verticals, countries)
        all_places.extend(gp_results)
        console.print(f"  [green]Found {len(gp_results)} places from Google[/green]")

        # Stage 2: Web scraping
        console.print("[bold cyan]Discovery Stage 2:[/bold cyan] Web Scraping")
        scrape_results = await self._run_scraping(verticals, countries)
        all_places.extend(scrape_results)
        console.print(f"  [green]Found {len(scrape_results)} places from scraping[/green]")

        # Stage 3: Brand expansion
        console.print("[bold cyan]Discovery Stage 3:[/bold cyan] Brand Expansion")
        expand_results = await self._run_brand_expansion(all_places, countries)
        all_places.extend(expand_results)
        console.print(f"  [green]Found {len(expand_results)} additional locations[/green]")

        # Stage 4: Deduplicate
        console.print("[bold cyan]Discovery Stage 4:[/bold cyan] Deduplication")
        merged = self.deduplicator.deduplicate(all_places)
        console.print(f"  [green]Merged to {len(merged)} unique places[/green]")

        # Convert MergedPlace to dict for pipeline compatibility
        return [self._merged_to_dict(m) for m in merged]

    def _merged_to_dict(self, merged: MergedPlace) -> dict:
        """Convert MergedPlace to dict matching pipeline expectations."""
        return {
            "name": merged.name,
            "address": merged.address,
            "website": merged.website,
            "place_id": merged.place_id,
            "city": merged.city,
            "vertical": merged.vertical,
        }

    async def _run_google_places(
        self,
        verticals: list[str],
        countries: list[str]
    ) -> list[dict]:
        """Run enhanced Google Places searches."""
        results = []
        semaphore = asyncio.Semaphore(self.settings.search_concurrency)

        # Build city list
        cities = []
        for country in countries:
            cities.extend(self.settings.cities.get(country, []))

        # Build search tasks
        tasks = []
        for vertical in verticals:
            for query in self.settings.search_queries.get(vertical, []):
                for city in cities:
                    tasks.append((city, query, vertical))

        async def search(city: str, query: str, vertical: str) -> list[dict]:
            async with semaphore:
                try:
                    places = await self.searcher.search(query, city, vertical=vertical)
                    return [
                        {
                            "name": p.name,
                            "address": p.address,
                            "website": p.website,
                            "place_id": p.place_id,
                            "city": p.city,
                            "vertical": p.vertical,
                            "source": "google_places"
                        }
                        for p in places
                    ]
                except Exception:
                    return []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Searching {len(tasks)} combinations...", total=len(tasks))

            coros = []
            for city, query, vertical in tasks:
                coros.append(search(city, query, vertical))

            for coro in asyncio.as_completed(coros):
                result = await coro
                results.extend(result)
                progress.advance(task)

        return results

    async def _run_scraping(
        self,
        verticals: list[str],
        countries: list[str]
    ) -> list[dict]:
        """Run web scraping for additional leads."""
        results = []

        # Build city list
        cities = []
        for country in countries:
            cities.extend(self.settings.cities.get(country, []))

        # Sample cities for best-of scraping (limit to avoid too many requests)
        sample_cities = cities[:10]

        for vertical in verticals:
            queries = self.settings.search_queries.get(vertical, [])
            if not queries:
                continue

            query = queries[0]  # Use first query as representative

            for city in sample_cities:
                try:
                    brands = await self.bestof_scraper.scrape_city(city, query)
                    for brand in brands:
                        results.append({
                            "name": brand.name,
                            "address": "",
                            "website": brand.website,
                            "place_id": None,
                            "city": city,
                            "vertical": vertical,
                            "source": "bestof_scrape"
                        })
                except Exception:
                    pass

        return results

    async def _run_brand_expansion(
        self,
        places: list[dict],
        countries: list[str]
    ) -> list[dict]:
        """Expand promising brands to all cities."""
        results = []

        # Build full city list
        all_cities = []
        for country in countries:
            all_cities.extend(self.settings.cities.get(country, []))

        # Group by website domain to find multi-location brands
        from collections import defaultdict
        by_domain = defaultdict(list)

        for place in places:
            if place.get("website"):
                domain = self.deduplicator._normalize_domain(place["website"])
                if domain:
                    by_domain[domain].append(place)

        # Find brands worth expanding
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
                    "cities_found": cities_found
                })

        console.print(f"  [dim]Expanding {len(brands_to_expand)} promising brands...[/dim]")

        # Expand each brand
        for brand in brands_to_expand[:20]:  # Limit to avoid too many API calls
            # Only search cities we haven't already found
            cities_to_search = [c for c in all_cities if c not in brand["cities_found"]]

            expanded = await self.expander.expand_brand(
                brand_name=brand["name"],
                known_website=brand["website"],
                cities=cities_to_search,
                vertical=brand["vertical"]
            )
            results.extend(expanded)

        return results
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_discovery.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/discovery.py tests/test_discovery.py
git commit -m "feat: add discovery orchestrator for multi-source search"
```

---

## Task 9: Integrate Discovery into Pipeline

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Import Discovery**

Add to imports at top of `src/pipeline.py`:

```python
from src.discovery import Discovery
```

**Step 2: Replace stage_1_search in run() method**

Find this section in the `run()` method:

```python
        # Stage 1: Search
        if start_stage < 1:
            places = await self.stage_1_search(verticals, countries)
```

Replace the stage 1 block with:

```python
        # Stage 1: Discovery (enhanced multi-source search)
        if start_stage < 1:
            discovery = Discovery(settings)
            places = await discovery.run(verticals, countries)
            searched_cities = []
            for country in countries:
                searched_cities.extend(settings.cities.get(country, []))
            checkpoint.places = places
            checkpoint.searched_cities = searched_cities
            checkpoint.stage = 1
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 1 complete)[/dim]")
```

**Step 3: Run tests to verify nothing broke**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v --ignore=tests/.venv`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/pipeline.py
git commit -m "feat: integrate multi-source discovery into pipeline"
```

---

## Task 10: Run Full Pipeline Test

**Step 1: Run the pipeline with limited scope**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src --verticals running_athletic --countries canada`

Expected: Pipeline completes with more leads than before

**Step 2: Verify output**

Check: `ls -la data/output/`

Look at the most recent CSV file and verify:
- More leads than the previous ~170
- Leads from multiple sources (check if diversity improved)

**Step 3: Commit any final adjustments**

```bash
git add -A
git commit -m "test: verify enhanced discovery pipeline"
```

---

## Summary

| Task | Component | Purpose |
|------|-----------|---------|
| 1 | cities.json | Add 37 suburban cities |
| 2 | cities.json | Expand to 45+ niche queries |
| 3 | places_search.py | Add Nearby Search API |
| 4 | deduplicator.py | Multi-source merging |
| 5 | brand_expander.py | Find all brand locations |
| 6 | scraper/base.py | Scraper infrastructure |
| 7 | scraper/bestof_scraper.py | Best-of article scraping |
| 8 | discovery.py | Orchestrate all sources |
| 9 | pipeline.py | Integrate discovery |
| 10 | Integration test | Verify full pipeline |

**Estimated time:** 3-4 hours

**Expected result:** 700-1,000 leads (4-6x improvement)
