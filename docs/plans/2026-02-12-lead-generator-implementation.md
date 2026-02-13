# Lead Generator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated pipeline that finds omnichannel retailers (3-10 locations + e-commerce) and extracts owner/executive LinkedIn contacts.

**Architecture:** Pipeline of 4 stages: (1) Google Places search by city/vertical, (2) group by brand name and filter by location count, (3) check websites for e-commerce indicators using Firecrawl, (4) enrich with LinkedIn company/people data. Each stage saves intermediate results for resumability.

**Tech Stack:** Python 3.11+, httpx (async HTTP), pandas (data processing), Firecrawl API, Google Places API, typer (CLI), rich (output formatting)

---

## Task 1: Core Configuration Module

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from src.config import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test_google_key")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test_firecrawl_key")

    settings = Settings()

    assert settings.google_places_api_key == "test_google_key"
    assert settings.firecrawl_api_key == "test_firecrawl_key"

def test_settings_loads_cities_config():
    settings = Settings()

    assert "us" in settings.cities
    assert "canada" in settings.cities
    assert len(settings.cities["us"]) == 35
    assert len(settings.cities["canada"]) == 15

def test_settings_loads_search_queries():
    settings = Settings()

    assert "health_wellness" in settings.search_queries
    assert "sporting_goods" in settings.search_queries
    assert "apparel" in settings.search_queries
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.config'"

**Step 3: Write minimal implementation**

```python
# src/config.py
import json
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    google_places_api_key: str = ""
    firecrawl_api_key: str = ""
    cities: dict = None
    search_queries: dict = None

    def __post_init__(self):
        self.google_places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "")

        config_path = Path(__file__).parent.parent / "config" / "cities.json"
        with open(config_path) as f:
            config = json.load(f)

        self.cities = {
            "us": config.get("us", []),
            "canada": config.get("canada", [])
        }
        self.search_queries = config.get("search_queries", {})

settings = Settings()
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/config.py tests/test_config.py
git commit -m "feat: add configuration module with settings loader"
```

---

## Task 2: Google Places Search Module

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
def mock_places_response():
    return {
        "places": [
            {
                "displayName": {"text": "Lululemon Athletica"},
                "formattedAddress": "123 Main St, New York, NY 10001",
                "websiteUri": "https://lululemon.com",
                "id": "place123"
            },
            {
                "displayName": {"text": "Nike Store"},
                "formattedAddress": "456 Broadway, New York, NY 10002",
                "websiteUri": "https://nike.com",
                "id": "place456"
            }
        ]
    }

@pytest.mark.asyncio
async def test_search_places_returns_results(mock_places_response):
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_places_response

        results = await searcher.search("clothing boutique", "New York, NY")

        assert len(results) == 2
        assert results[0].name == "Lululemon Athletica"
        assert results[0].website == "https://lululemon.com"

@pytest.mark.asyncio
async def test_search_places_handles_empty_response():
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"places": []}

        results = await searcher.search("rare store type", "Small Town, USA")

        assert len(results) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_places_search.py -v`
Expected: FAIL with "cannot import name 'PlacesSearcher'"

**Step 3: Write minimal implementation**

```python
# src/places_search.py
import httpx
from dataclasses import dataclass
from typing import Optional

@dataclass
class PlaceResult:
    name: str
    address: str
    website: Optional[str]
    place_id: str
    city: str
    vertical: str

class PlacesSearcher:
    BASE_URL = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri,places.id"
        }

    async def _make_request(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.BASE_URL,
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()

    async def search(self, query: str, city: str, vertical: str = "") -> list[PlaceResult]:
        payload = {
            "textQuery": f"{query} in {city}",
            "maxResultCount": 20
        }

        data = await self._make_request(payload)
        places = data.get("places", [])

        results = []
        for place in places:
            results.append(PlaceResult(
                name=place.get("displayName", {}).get("text", ""),
                address=place.get("formattedAddress", ""),
                website=place.get("websiteUri"),
                place_id=place.get("id", ""),
                city=city,
                vertical=vertical
            ))

        return results
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_places_search.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/places_search.py tests/test_places_search.py
git commit -m "feat: add Google Places search module"
```

---

## Task 3: Brand Grouper Module

**Files:**
- Modify: `src/brand_grouper.py`
- Create: `tests/test_brand_grouper.py`

**Step 1: Write the failing test**

```python
# tests/test_brand_grouper.py
import pytest
from src.brand_grouper import BrandGrouper, BrandGroup

@pytest.fixture
def sample_places():
    return [
        {"name": "Lululemon Athletica", "address": "NYC", "website": "https://lululemon.com", "city": "New York, NY"},
        {"name": "Lululemon", "address": "LA", "website": "https://lululemon.com", "city": "Los Angeles, CA"},
        {"name": "Lululemon Athletica Store", "address": "Chicago", "website": "https://lululemon.com", "city": "Chicago, IL"},
        {"name": "Nike Store", "address": "NYC", "website": "https://nike.com", "city": "New York, NY"},
        {"name": "Nike", "address": "Boston", "website": "https://nike.com", "city": "Boston, MA"},
        {"name": "Local Boutique", "address": "Austin", "website": "https://local.com", "city": "Austin, TX"},
    ]

def test_group_by_brand_normalizes_names(sample_places):
    grouper = BrandGrouper()
    groups = grouper.group(sample_places)

    # Lululemon variations should be grouped together
    lulu_group = next((g for g in groups if "lululemon" in g.normalized_name.lower()), None)
    assert lulu_group is not None
    assert lulu_group.location_count == 3

def test_filter_by_location_count(sample_places):
    grouper = BrandGrouper(min_locations=3, max_locations=10)
    groups = grouper.group(sample_places)
    filtered = grouper.filter(groups)

    # Only Lululemon has 3+ locations
    assert len(filtered) == 1
    assert filtered[0].location_count == 3

def test_excludes_over_max_locations():
    places = [{"name": f"BigChain Store {i}", "address": f"City {i}", "website": "https://bigchain.com", "city": f"City {i}"} for i in range(15)]

    grouper = BrandGrouper(min_locations=3, max_locations=10)
    groups = grouper.group(places)
    filtered = grouper.filter(groups)

    assert len(filtered) == 0  # 15 locations exceeds max of 10
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py -v`
Expected: FAIL with "cannot import name 'BrandGrouper'"

**Step 3: Write minimal implementation**

```python
# src/brand_grouper.py
import re
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

@dataclass
class BrandGroup:
    normalized_name: str
    original_names: list[str] = field(default_factory=list)
    location_count: int = 0
    locations: list[dict] = field(default_factory=list)
    website: Optional[str] = None
    cities: list[str] = field(default_factory=list)

class BrandGrouper:
    # Common suffixes to strip for normalization
    STRIP_PATTERNS = [
        r'\s+(inc\.?|llc\.?|ltd\.?|corp\.?)$',
        r'\s+(store|shop|boutique|outlet)$',
        r'\s+(athletica|athletics)$',
        r'\s+#?\d+$',  # Store numbers
    ]

    def __init__(self, min_locations: int = 3, max_locations: int = 10):
        self.min_locations = min_locations
        self.max_locations = max_locations

    def _normalize_name(self, name: str) -> str:
        normalized = name.lower().strip()
        for pattern in self.STRIP_PATTERNS:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        return normalized.strip()

    def group(self, places: list[dict]) -> list[BrandGroup]:
        groups: dict[str, BrandGroup] = defaultdict(lambda: BrandGroup(normalized_name=""))

        for place in places:
            name = place.get("name", "")
            normalized = self._normalize_name(name)

            if not normalized:
                continue

            if groups[normalized].normalized_name == "":
                groups[normalized].normalized_name = normalized

            groups[normalized].original_names.append(name)
            groups[normalized].location_count += 1
            groups[normalized].locations.append(place)

            if place.get("website") and not groups[normalized].website:
                groups[normalized].website = place["website"]

            city = place.get("city", "")
            if city and city not in groups[normalized].cities:
                groups[normalized].cities.append(city)

        return list(groups.values())

    def filter(self, groups: list[BrandGroup]) -> list[BrandGroup]:
        return [
            g for g in groups
            if self.min_locations <= g.location_count <= self.max_locations
        ]
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/brand_grouper.py tests/test_brand_grouper.py
git commit -m "feat: add brand grouper with name normalization and filtering"
```

---

## Task 4: E-commerce Detection Module

**Files:**
- Modify: `src/ecommerce_check.py`
- Create: `tests/test_ecommerce_check.py`

**Step 1: Write the failing test**

```python
# tests/test_ecommerce_check.py
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker

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
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py -v`
Expected: FAIL with "cannot import name 'EcommerceChecker'"

**Step 3: Write minimal implementation**

```python
# src/ecommerce_check.py
import httpx
from dataclasses import dataclass
from typing import Optional
import re

@dataclass
class EcommerceResult:
    url: str
    has_ecommerce: bool
    confidence: float
    indicators_found: list[str]

class EcommerceChecker:
    FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

    # Patterns indicating e-commerce functionality
    ECOMMERCE_PATTERNS = [
        r'add.to.cart',
        r'checkout',
        r'shopping.cart',
        r'buy.now',
        r'shop.now',
        r'add.to.bag',
        r'/cart',
        r'/checkout',
        r'/shop',
        r'/store',
        r'price:\s*\$',
        r'\$\d+\.\d{2}',
        r'free.shipping',
        r'add.to.wishlist',
    ]

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def _fetch_page(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.FIRECRAWL_URL,
                headers=self.headers,
                json={"url": url, "formats": ["markdown"]}
            )
            response.raise_for_status()
            return response.json()

    async def check(self, url: str) -> EcommerceResult:
        try:
            data = await self._fetch_page(url)
            content = data.get("data", {}).get("markdown", "").lower()

            indicators_found = []
            for pattern in self.ECOMMERCE_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    indicators_found.append(pattern)

            confidence = min(len(indicators_found) / 5, 1.0)  # Max confidence at 5+ indicators
            has_ecommerce = len(indicators_found) >= 2

            return EcommerceResult(
                url=url,
                has_ecommerce=has_ecommerce,
                confidence=confidence,
                indicators_found=indicators_found
            )
        except Exception as e:
            return EcommerceResult(
                url=url,
                has_ecommerce=False,
                confidence=0.0,
                indicators_found=[f"error: {str(e)}"]
            )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add e-commerce detection with Firecrawl"
```

---

## Task 5: LinkedIn Enrichment Module

**Files:**
- Modify: `src/linkedin_enrich.py`
- Create: `tests/test_linkedin_enrich.py`

**Step 1: Write the failing test**

```python
# tests/test_linkedin_enrich.py
import pytest
from unittest.mock import AsyncMock, patch
from src.linkedin_enrich import LinkedInEnricher, Contact

@pytest.fixture
def mock_company_page():
    return {
        "data": {
            "markdown": """
            # Lululemon on LinkedIn

            linkedin.com/company/lululemon

            ## People
            - John Smith - CEO
            - Jane Doe - COO
            - Bob Wilson - Operations Manager
            """
        }
    }

@pytest.mark.asyncio
async def test_finds_company_linkedin_page(mock_company_page):
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_search_linkedin', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = "https://linkedin.com/company/lululemon"

        result = await enricher.find_company("Lululemon", "https://lululemon.com")

        assert result == "https://linkedin.com/company/lululemon"

@pytest.mark.asyncio
async def test_finds_contacts_by_title():
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            Contact(name="John Smith", title="CEO", linkedin_url="https://linkedin.com/in/johnsmith"),
            Contact(name="Jane Doe", title="COO", linkedin_url="https://linkedin.com/in/janedoe"),
        ]

        contacts = await enricher.find_contacts("Lululemon", max_contacts=4)

        assert len(contacts) == 2
        assert contacts[0].title == "CEO"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_linkedin_enrich.py -v`
Expected: FAIL with "cannot import name 'LinkedInEnricher'"

**Step 3: Write minimal implementation**

```python
# src/linkedin_enrich.py
import httpx
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class Contact:
    name: str
    title: str
    linkedin_url: str

@dataclass
class CompanyEnrichment:
    company_name: str
    linkedin_company_url: Optional[str]
    contacts: list[Contact]

class LinkedInEnricher:
    FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

    TARGET_TITLES = [
        "owner", "founder", "co-founder",
        "ceo", "chief executive",
        "coo", "chief operating",
        "president",
        "operations manager", "director of operations",
        "inventory manager", "supply chain manager",
        "retail manager", "store manager"
    ]

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def _fetch_page(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.FIRECRAWL_URL,
                headers=self.headers,
                json={"url": url, "formats": ["markdown"]}
            )
            response.raise_for_status()
            return response.json()

    async def _search_linkedin(self, company_name: str, website: str) -> Optional[str]:
        # Use Google search via Firecrawl to find LinkedIn company page
        search_url = f"https://www.google.com/search?q=site:linkedin.com/company+{company_name.replace(' ', '+')}"
        try:
            data = await self._fetch_page(search_url)
            content = data.get("data", {}).get("markdown", "")

            # Extract LinkedIn company URL from results
            match = re.search(r'linkedin\.com/company/[\w-]+', content)
            if match:
                return f"https://{match.group(0)}"
        except Exception:
            pass
        return None

    async def _search_people(self, company_name: str) -> list[Contact]:
        contacts = []
        search_url = f"https://www.google.com/search?q=site:linkedin.com/in+{company_name.replace(' ', '+')}+CEO+OR+COO+OR+founder+OR+operations"

        try:
            data = await self._fetch_page(search_url)
            content = data.get("data", {}).get("markdown", "")

            # Extract LinkedIn profile URLs and try to parse names/titles
            profile_matches = re.findall(r'linkedin\.com/in/([\w-]+)', content)

            for profile_id in profile_matches[:4]:  # Max 4 contacts
                contacts.append(Contact(
                    name=profile_id.replace("-", " ").title(),
                    title="(to be verified)",
                    linkedin_url=f"https://linkedin.com/in/{profile_id}"
                ))
        except Exception:
            pass

        return contacts

    async def find_company(self, company_name: str, website: str) -> Optional[str]:
        return await self._search_linkedin(company_name, website)

    async def find_contacts(self, company_name: str, max_contacts: int = 4) -> list[Contact]:
        contacts = await self._search_people(company_name)
        return contacts[:max_contacts]

    async def enrich(self, company_name: str, website: str) -> CompanyEnrichment:
        linkedin_url = await self.find_company(company_name, website)
        contacts = await self.find_contacts(company_name)

        return CompanyEnrichment(
            company_name=company_name,
            linkedin_company_url=linkedin_url,
            contacts=contacts
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_linkedin_enrich.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/linkedin_enrich.py tests/test_linkedin_enrich.py
git commit -m "feat: add LinkedIn enrichment module"
```

---

## Task 6: Main Pipeline Orchestrator

**Files:**
- Modify: `src/pipeline.py`
- Create: `tests/test_pipeline.py`

**Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline import Pipeline

@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    pipeline = Pipeline()

    with patch.object(pipeline, 'stage_1_search', new_callable=AsyncMock) as mock_search, \
         patch.object(pipeline, 'stage_2_group', new_callable=MagicMock) as mock_group, \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock) as mock_ecom, \
         patch.object(pipeline, 'stage_4_linkedin', new_callable=AsyncMock) as mock_linkedin, \
         patch.object(pipeline, 'stage_5_export', new_callable=MagicMock) as mock_export:

        mock_search.return_value = [{"name": "Test Store"}]
        mock_group.return_value = [MagicMock(location_count=5)]
        mock_ecom.return_value = [MagicMock(has_ecommerce=True)]
        mock_linkedin.return_value = [MagicMock()]
        mock_export.return_value = "output.csv"

        result = await pipeline.run(verticals=["apparel"], countries=["us"])

        mock_search.assert_called_once()
        mock_group.assert_called_once()
        mock_ecom.assert_called_once()
        mock_linkedin.assert_called_once()
        mock_export.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py -v`
Expected: FAIL with "cannot import name 'Pipeline'"

**Step 3: Write minimal implementation**

```python
# src/pipeline.py
import asyncio
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress

from src.config import settings
from src.places_search import PlacesSearcher, PlaceResult
from src.brand_grouper import BrandGrouper, BrandGroup
from src.ecommerce_check import EcommerceChecker
from src.linkedin_enrich import LinkedInEnricher

console = Console()

class Pipeline:
    def __init__(self):
        self.data_dir = Path(__file__).parent.parent / "data"
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.output_dir = self.data_dir / "output"

        # Ensure directories exist
        for d in [self.raw_dir, self.processed_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def stage_1_search(self, verticals: list[str], countries: list[str]) -> list[dict]:
        """Search Google Places for businesses."""
        searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        all_results = []

        cities = []
        for country in countries:
            cities.extend(settings.cities.get(country, []))

        queries = []
        for vertical in verticals:
            queries.extend(settings.search_queries.get(vertical, []))

        console.print(f"[bold]Stage 1:[/bold] Searching {len(cities)} cities x {len(queries)} queries")

        for city in cities:
            for query in queries:
                try:
                    results = await searcher.search(query, city, vertical=vertical)
                    for r in results:
                        all_results.append({
                            "name": r.name,
                            "address": r.address,
                            "website": r.website,
                            "place_id": r.place_id,
                            "city": r.city,
                            "vertical": r.vertical
                        })
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    console.print(f"[red]Error searching {query} in {city}: {e}[/red]")

        # Save raw results
        raw_file = self.raw_dir / f"places_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(raw_file, 'w') as f:
            json.dump(all_results, f, indent=2)

        console.print(f"[green]Found {len(all_results)} places[/green]")
        return all_results

    def stage_2_group(self, places: list[dict]) -> list[BrandGroup]:
        """Group places by brand and filter by location count."""
        grouper = BrandGrouper(min_locations=3, max_locations=10)
        groups = grouper.group(places)
        filtered = grouper.filter(groups)

        console.print(f"[bold]Stage 2:[/bold] Grouped into {len(groups)} brands, {len(filtered)} have 3-10 locations")
        return filtered

    async def stage_3_ecommerce(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Check each brand for e-commerce presence."""
        checker = EcommerceChecker(api_key=settings.firecrawl_api_key)
        ecommerce_brands = []

        console.print(f"[bold]Stage 3:[/bold] Checking {len(brands)} brands for e-commerce")

        for brand in brands:
            if not brand.website:
                continue
            try:
                result = await checker.check(brand.website)
                if result.has_ecommerce:
                    ecommerce_brands.append(brand)
                await asyncio.sleep(0.5)  # Rate limiting
            except Exception as e:
                console.print(f"[red]Error checking {brand.website}: {e}[/red]")

        console.print(f"[green]{len(ecommerce_brands)} brands have e-commerce[/green]")
        return ecommerce_brands

    async def stage_4_linkedin(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich brands with LinkedIn data."""
        enricher = LinkedInEnricher(api_key=settings.firecrawl_api_key)
        enriched = []

        console.print(f"[bold]Stage 4:[/bold] Enriching {len(brands)} brands with LinkedIn data")

        for brand in brands:
            try:
                result = await enricher.enrich(brand.normalized_name, brand.website or "")

                enriched.append({
                    "brand_name": brand.normalized_name.title(),
                    "location_count": brand.location_count,
                    "website": brand.website,
                    "has_ecommerce": True,
                    "cities": ", ".join(brand.cities[:5]),
                    "linkedin_company": result.linkedin_company_url or "",
                    "contact_1_name": result.contacts[0].name if len(result.contacts) > 0 else "",
                    "contact_1_title": result.contacts[0].title if len(result.contacts) > 0 else "",
                    "contact_1_linkedin": result.contacts[0].linkedin_url if len(result.contacts) > 0 else "",
                    "contact_2_name": result.contacts[1].name if len(result.contacts) > 1 else "",
                    "contact_2_title": result.contacts[1].title if len(result.contacts) > 1 else "",
                    "contact_2_linkedin": result.contacts[1].linkedin_url if len(result.contacts) > 1 else "",
                    "contact_3_name": result.contacts[2].name if len(result.contacts) > 2 else "",
                    "contact_3_title": result.contacts[2].title if len(result.contacts) > 2 else "",
                    "contact_3_linkedin": result.contacts[2].linkedin_url if len(result.contacts) > 2 else "",
                    "contact_4_name": result.contacts[3].name if len(result.contacts) > 3 else "",
                    "contact_4_title": result.contacts[3].title if len(result.contacts) > 3 else "",
                    "contact_4_linkedin": result.contacts[3].linkedin_url if len(result.contacts) > 3 else "",
                })
                await asyncio.sleep(1.0)  # Rate limiting
            except Exception as e:
                console.print(f"[red]Error enriching {brand.normalized_name}: {e}[/red]")

        console.print(f"[green]Enriched {len(enriched)} brands[/green]")
        return enriched

    def stage_5_export(self, data: list[dict]) -> str:
        """Export to CSV."""
        df = pd.DataFrame(data)
        output_file = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(output_file, index=False)

        console.print(f"[bold green]Exported {len(data)} leads to {output_file}[/bold green]")
        return str(output_file)

    async def run(
        self,
        verticals: list[str] = ["health_wellness", "sporting_goods", "apparel"],
        countries: list[str] = ["us", "canada"]
    ) -> str:
        """Run the full pipeline."""
        console.print("[bold blue]Starting Lead Generator Pipeline[/bold blue]")

        # Stage 1: Search
        places = await self.stage_1_search(verticals, countries)

        # Stage 2: Group and filter
        brands = self.stage_2_group(places)

        # Stage 3: E-commerce check
        ecommerce_brands = await self.stage_3_ecommerce(brands)

        # Stage 4: LinkedIn enrichment
        enriched = await self.stage_4_linkedin(ecommerce_brands)

        # Stage 5: Export
        output_file = self.stage_5_export(enriched)

        console.print("[bold green]Pipeline complete![/bold green]")
        return output_file
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/pipeline.py tests/test_pipeline.py
git commit -m "feat: add main pipeline orchestrator"
```

---

## Task 7: CLI Interface

**Files:**
- Create: `src/__main__.py`

**Step 1: Write the CLI**

```python
# src/__main__.py
import asyncio
import typer
from typing import Optional
from rich.console import Console

from src.pipeline import Pipeline

app = typer.Typer(help="Lead Generator - Find omnichannel retail leads")
console = Console()

@app.command()
def run(
    verticals: str = typer.Option(
        "all",
        "--verticals", "-v",
        help="Verticals to search: all, health_wellness, sporting_goods, apparel (comma-separated)"
    ),
    countries: str = typer.Option(
        "us,ca",
        "--countries", "-c",
        help="Countries to search: us, ca (comma-separated)"
    ),
):
    """Run the full lead generation pipeline."""

    # Parse verticals
    if verticals == "all":
        vertical_list = ["health_wellness", "sporting_goods", "apparel"]
    else:
        vertical_list = [v.strip() for v in verticals.split(",")]

    # Parse countries
    country_list = [c.strip() for c in countries.split(",")]
    country_list = ["canada" if c == "ca" else c for c in country_list]

    console.print(f"[bold]Verticals:[/bold] {vertical_list}")
    console.print(f"[bold]Countries:[/bold] {country_list}")

    pipeline = Pipeline()
    output_file = asyncio.run(pipeline.run(verticals=vertical_list, countries=country_list))

    console.print(f"\n[bold green]Done! Output: {output_file}[/bold green]")

@app.command()
def search(
    vertical: str = typer.Argument(..., help="Vertical to search"),
    country: str = typer.Option("us", "--country", "-c", help="Country to search"),
):
    """Run only the Google Places search stage."""
    pipeline = Pipeline()
    country = "canada" if country == "ca" else country
    results = asyncio.run(pipeline.stage_1_search([vertical], [country]))
    console.print(f"[green]Found {len(results)} places[/green]")

if __name__ == "__main__":
    app()
```

**Step 2: Test CLI works**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src --help`
Expected: Shows help with `run` and `search` commands

**Step 3: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/__main__.py
git commit -m "feat: add CLI interface with typer"
```

---

## Task 8: Create tests/__init__.py and Final Cleanup

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create test setup files**

```python
# tests/__init__.py
# Test package
```

```python
# tests/conftest.py
import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def sample_brand_data():
    return {
        "brand_name": "Test Brand",
        "location_count": 5,
        "website": "https://testbrand.com",
        "has_ecommerce": True,
    }
```

**Step 2: Run all tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit and push**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add tests/__init__.py tests/conftest.py
git commit -m "feat: add test configuration"
git push origin master
```

---

## Summary

| Task | Component | Purpose |
|------|-----------|---------|
| 1 | config.py | Load API keys and city/query config |
| 2 | places_search.py | Google Places API integration |
| 3 | brand_grouper.py | Normalize names, group, filter 3-10 locations |
| 4 | ecommerce_check.py | Firecrawl e-commerce detection |
| 5 | linkedin_enrich.py | Firecrawl LinkedIn company/people search |
| 6 | pipeline.py | Orchestrate all stages |
| 7 | __main__.py | CLI interface |
| 8 | tests/ | Test configuration |

**Total estimated time:** 2-3 hours

**To run after implementation:**
```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
cp .env.example .env
# Add your API keys to .env
python -m src --verticals all --countries us,ca
```
