# Discovery & E-commerce Detection Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve lead discovery by adding nearby search grid for suburb coverage, and reduce e-commerce false negatives by expanding platform detection from 7 to 15 platforms with header/meta/JSON-LD signals and Playwright fallback for JS-rendered stores.

**Architecture:** Two independent improvement tracks: (1) Discovery adds a nearby grid search step using the existing `nearby_search` method with auto-geocoded city coordinates and expanded retail type mappings. (2) E-commerce detection expands platform signatures, extracts detection signals from HTTP headers/meta tags/JSON-LD, and adds a conditional Playwright fallback for SPA sites.

**Tech Stack:** Python 3, httpx, asyncio, Playwright (existing dep), Google Places API (Nearby Search + Geocoding), pytest

---

## Task 1: Add Discovery Config Settings

**Files:**
- Modify: `config/cities.json` (add `discovery` section)
- Modify: `src/config.py` (add `DiscoverySettings` dataclass, load new config)
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
def test_discovery_settings_loaded():
    """Discovery nearby grid settings should load from config."""
    from src.config import Settings
    s = Settings()
    assert hasattr(s, 'discovery')
    assert s.discovery.nearby_grid_enabled is True
    assert s.discovery.nearby_grid_offset_km == 20
    assert s.discovery.nearby_grid_radius_meters == 15000
    assert s.discovery.nearby_grid_points == "cardinal"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_discovery_settings_loaded -v`
Expected: FAIL — `Settings` has no `discovery` attribute

**Step 3: Add config JSON and dataclass**

In `config/cities.json`, add before the closing `}`:

```json
"discovery": {
  "nearby_grid": {
    "enabled": true,
    "offset_km": 20,
    "radius_meters": 15000,
    "points": "cardinal"
  }
}
```

In `src/config.py`, add the dataclass:

```python
@dataclass
class DiscoverySettings:
    """Settings for discovery nearby grid search."""
    nearby_grid_enabled: bool = True
    nearby_grid_offset_km: int = 20
    nearby_grid_radius_meters: int = 15000
    nearby_grid_points: str = "cardinal"  # "cardinal" (5 points) or "full" (9 points)
```

In `Settings` dataclass, add the field:

```python
discovery: DiscoverySettings = field(default_factory=DiscoverySettings)
```

In `Settings.__post_init__`, add loading logic:

```python
# Load discovery settings
discovery_config = config.get("discovery", {})
nearby_grid = discovery_config.get("nearby_grid", {})
self.discovery = DiscoverySettings(
    nearby_grid_enabled=nearby_grid.get("enabled", True),
    nearby_grid_offset_km=nearby_grid.get("offset_km", 20),
    nearby_grid_radius_meters=nearby_grid.get("radius_meters", 15000),
    nearby_grid_points=nearby_grid.get("points", "cardinal"),
)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py::test_discovery_settings_loaded -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/config.py config/cities.json tests/test_config.py
git commit -m "feat: add discovery nearby grid config settings"
```

---

## Task 2: Add E-commerce Playwright Fallback Config

**Files:**
- Modify: `config/cities.json` (update `ecommerce` section)
- Modify: `src/config.py` (add playwright fallback fields)
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
def test_ecommerce_playwright_fallback_settings():
    """Playwright fallback settings should load from config."""
    from src.config import Settings
    s = Settings()
    assert s.ecommerce_playwright_fallback_enabled is True
    assert s.ecommerce_playwright_fallback_max_percent == 20
    assert s.ecommerce_playwright_fallback_timeout == 15
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_ecommerce_playwright_fallback_settings -v`
Expected: FAIL

**Step 3: Add config JSON and loading**

In `config/cities.json`, update the `ecommerce` section:

```json
"ecommerce": {
  "concurrency": 5,
  "pages_to_check": 3,
  "playwright_fallback": {
    "enabled": true,
    "max_percent": 20,
    "timeout_seconds": 15
  }
}
```

In `Settings` dataclass, add fields:

```python
ecommerce_playwright_fallback_enabled: bool = True
ecommerce_playwright_fallback_max_percent: int = 20
ecommerce_playwright_fallback_timeout: int = 15
```

In `__post_init__`, add:

```python
# Load playwright fallback settings
pw_config = config.get("ecommerce", {}).get("playwright_fallback", {})
self.ecommerce_playwright_fallback_enabled = pw_config.get("enabled", True)
self.ecommerce_playwright_fallback_max_percent = pw_config.get("max_percent", 20)
self.ecommerce_playwright_fallback_timeout = pw_config.get("timeout_seconds", 15)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py::test_ecommerce_playwright_fallback_settings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/config.py config/cities.json tests/test_config.py
git commit -m "feat: add ecommerce playwright fallback config"
```

---

## Task 3: Grid Point Generation Helper

**Files:**
- Modify: `src/places_search.py` (add `generate_grid_points` static method)
- Test: `tests/test_places_search.py`

**Step 1: Write the failing test**

```python
def test_generate_cardinal_grid_points():
    """Should generate center + 4 cardinal offset points."""
    points = PlacesSearcher.generate_grid_points(
        center_lat=41.8781,
        center_lng=-87.6298,
        offset_km=20,
        mode="cardinal"
    )
    assert len(points) == 5
    # First point should be center
    assert points[0] == (41.8781, -87.6298)
    # North point should have higher latitude
    assert points[1][0] > 41.8781
    assert abs(points[1][1] - (-87.6298)) < 0.001  # Same longitude
    # South point should have lower latitude
    assert points[2][0] < 41.8781
    # East point should have higher longitude (less negative)
    assert points[3][1] > -87.6298
    # West point should have lower longitude (more negative)
    assert points[4][1] < -87.6298


def test_generate_full_grid_points():
    """Should generate center + 8 surrounding points."""
    points = PlacesSearcher.generate_grid_points(
        center_lat=41.8781,
        center_lng=-87.6298,
        offset_km=20,
        mode="full"
    )
    assert len(points) == 9


def test_grid_points_offset_distance():
    """Offset points should be approximately the requested distance."""
    import math
    center_lat, center_lng = 41.8781, -87.6298
    points = PlacesSearcher.generate_grid_points(
        center_lat=center_lat,
        center_lng=center_lng,
        offset_km=20,
        mode="cardinal"
    )
    # Check north point is ~20km away
    north_lat, north_lng = points[1]
    # 1 degree latitude ~= 111km
    lat_diff_km = abs(north_lat - center_lat) * 111
    assert 18 < lat_diff_km < 22  # Allow ~10% tolerance
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_places_search.py::test_generate_cardinal_grid_points tests/test_places_search.py::test_generate_full_grid_points tests/test_places_search.py::test_grid_points_offset_distance -v`
Expected: FAIL — `generate_grid_points` not defined

**Step 3: Implement grid point generation**

Add to `PlacesSearcher` in `src/places_search.py`:

```python
import math

@staticmethod
def generate_grid_points(
    center_lat: float,
    center_lng: float,
    offset_km: int = 20,
    mode: str = "cardinal"
) -> list[tuple[float, float]]:
    """Generate grid points around a center coordinate.

    Args:
        center_lat: Center latitude
        center_lng: Center longitude
        offset_km: Distance from center to offset points in km
        mode: "cardinal" for 5 points (center + N/S/E/W),
              "full" for 9 points (center + 8 surrounding)

    Returns:
        List of (lat, lng) tuples
    """
    # 1 degree latitude ~= 111km everywhere
    lat_offset = offset_km / 111.0
    # 1 degree longitude varies by latitude
    lng_offset = offset_km / (111.0 * math.cos(math.radians(center_lat)))

    points = [(center_lat, center_lng)]  # Center

    # Cardinal directions: N, S, E, W
    points.append((center_lat + lat_offset, center_lng))  # North
    points.append((center_lat - lat_offset, center_lng))  # South
    points.append((center_lat, center_lng + lng_offset))  # East
    points.append((center_lat, center_lng - lng_offset))  # West

    if mode == "full":
        # Diagonal directions: NE, NW, SE, SW
        points.append((center_lat + lat_offset, center_lng + lng_offset))  # NE
        points.append((center_lat + lat_offset, center_lng - lng_offset))  # NW
        points.append((center_lat - lat_offset, center_lng + lng_offset))  # SE
        points.append((center_lat - lat_offset, center_lng - lng_offset))  # SW

    return points
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_places_search.py::test_generate_cardinal_grid_points tests/test_places_search.py::test_generate_full_grid_points tests/test_places_search.py::test_grid_points_offset_distance -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/places_search.py tests/test_places_search.py
git commit -m "feat: add grid point generation for metro area coverage"
```

---

## Task 4: Expand RETAIL_TYPES to All 11 Verticals

**Files:**
- Modify: `src/places_search.py` (expand `RETAIL_TYPES`)
- Test: `tests/test_places_search.py`

**Step 1: Write the failing test**

```python
def test_retail_types_covers_all_verticals():
    """RETAIL_TYPES should map all 11 verticals to Google Places types."""
    expected_verticals = {
        "sporting_goods", "health_wellness", "apparel", "outdoor_camping",
        "pet_supplies", "beauty_cosmetics", "specialty_food",
        "running_athletic", "cycling", "baby_kids", "home_goods"
    }
    assert set(PlacesSearcher.RETAIL_TYPES.keys()) == expected_verticals
    # Each vertical should have at least one type
    for vertical, types in PlacesSearcher.RETAIL_TYPES.items():
        assert len(types) >= 1, f"{vertical} has no types"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_places_search.py::test_retail_types_covers_all_verticals -v`
Expected: FAIL — only 4 verticals present

**Step 3: Expand RETAIL_TYPES**

Replace `RETAIL_TYPES` in `src/places_search.py`:

```python
RETAIL_TYPES = {
    "sporting_goods": ["sporting_goods_store", "bicycle_store"],
    "health_wellness": ["health_food_store", "drugstore"],
    "apparel": ["clothing_store", "shoe_store"],
    "outdoor_camping": ["camping_store", "outdoor_recreation_store"],
    "pet_supplies": ["pet_store"],
    "beauty_cosmetics": ["beauty_salon", "cosmetics_store"],
    "specialty_food": ["grocery_store", "gourmet_grocery_store"],
    "running_athletic": ["sporting_goods_store", "shoe_store"],
    "cycling": ["bicycle_store"],
    "baby_kids": ["childrens_clothing_store", "toy_store"],
    "home_goods": ["home_goods_store", "furniture_store"],
}
```

Note: Google Places types are limited. Some verticals share types with others. The type list uses Google's [Place Types](https://developers.google.com/maps/documentation/places/web-service/supported_types) — verify exact type strings against the API docs before implementation, as some may need adjustment (e.g., `cosmetics_store` may not exist; use `beauty_salon` as fallback). The implementer should check the Google Places API supported types list and use the closest available type for each vertical.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_places_search.py::test_retail_types_covers_all_verticals -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/places_search.py tests/test_places_search.py
git commit -m "feat: expand RETAIL_TYPES to cover all 11 verticals"
```

---

## Task 5: City Geocoding Cache

**Files:**
- Create: `src/geocoder.py`
- Test: `tests/test_geocoder.py`

This provides lat/lng for each city, needed by the grid search. Coordinates are cached to `data/city_coordinates.json` to avoid repeated API calls.

**Step 1: Write the failing test**

```python
# tests/test_geocoder.py
import pytest
from unittest.mock import AsyncMock, patch
from src.geocoder import CityGeocoder


@pytest.mark.asyncio
async def test_geocode_city_returns_coordinates():
    """Should return lat/lng for a city string."""
    geocoder = CityGeocoder(api_key="test_key")

    mock_response = {
        "results": [{
            "geometry": {"location": {"lat": 41.8781, "lng": -87.6298}}
        }]
    }

    with patch.object(geocoder, '_geocode_api', new_callable=AsyncMock) as mock_api:
        mock_api.return_value = mock_response
        lat, lng = await geocoder.geocode("Chicago, IL")

    assert abs(lat - 41.8781) < 0.01
    assert abs(lng - (-87.6298)) < 0.01


@pytest.mark.asyncio
async def test_geocode_uses_cache():
    """Should return cached coordinates without API call."""
    geocoder = CityGeocoder(api_key="test_key")
    geocoder._cache = {"Chicago, IL": (41.8781, -87.6298)}

    with patch.object(geocoder, '_geocode_api', new_callable=AsyncMock) as mock_api:
        lat, lng = await geocoder.geocode("Chicago, IL")
        mock_api.assert_not_called()

    assert lat == 41.8781


@pytest.mark.asyncio
async def test_geocode_batch():
    """Should geocode a list of cities, using cache when available."""
    geocoder = CityGeocoder(api_key="test_key")
    geocoder._cache = {"Boston, MA": (42.3601, -71.0589)}

    mock_response = {
        "results": [{
            "geometry": {"location": {"lat": 40.7128, "lng": -74.0060}}
        }]
    }

    with patch.object(geocoder, '_geocode_api', new_callable=AsyncMock) as mock_api:
        mock_api.return_value = mock_response
        results = await geocoder.geocode_batch(["Boston, MA", "New York, NY"])

    assert "Boston, MA" in results
    assert "New York, NY" in results
    # Only New York should have triggered an API call
    mock_api.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_geocoder.py -v`
Expected: FAIL — module not found

**Step 3: Implement geocoder**

Create `src/geocoder.py`:

```python
# src/geocoder.py
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent.parent / "data" / "city_coordinates.json"


class CityGeocoder:
    """Geocodes city names to lat/lng using Google Geocoding API with file cache."""

    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

    def __init__(self, api_key: str, concurrency: int = 5):
        self.api_key = api_key
        self.concurrency = concurrency
        self._cache: dict[str, tuple[float, float]] = {}
        self._load_cache()

    def _load_cache(self):
        """Load cached coordinates from file."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE) as f:
                    data = json.load(f)
                self._cache = {k: tuple(v) for k, v in data.items()}
            except (json.JSONDecodeError, ValueError):
                self._cache = {}

    def _save_cache(self):
        """Save coordinates cache to file."""
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({k: list(v) for k, v in self._cache.items()}, f, indent=2)

    async def _geocode_api(self, city: str) -> dict:
        """Call Google Geocoding API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.GEOCODE_URL,
                params={"address": city, "key": self.api_key},
            )
            response.raise_for_status()
            return response.json()

    async def geocode(self, city: str) -> Optional[tuple[float, float]]:
        """Get lat/lng for a city. Returns cached result if available."""
        if city in self._cache:
            return self._cache[city]

        try:
            data = await self._geocode_api(city)
            results = data.get("results", [])
            if results:
                loc = results[0]["geometry"]["location"]
                coords = (loc["lat"], loc["lng"])
                self._cache[city] = coords
                return coords
        except Exception as e:
            logger.warning("Geocoding failed for %s: %s", city, e)

        return None

    async def geocode_batch(
        self, cities: list[str]
    ) -> dict[str, tuple[float, float]]:
        """Geocode a list of cities with concurrency control."""
        semaphore = asyncio.Semaphore(self.concurrency)
        results = {}

        async def geocode_one(city: str):
            async with semaphore:
                coords = await self.geocode(city)
                if coords:
                    results[city] = coords

        tasks = [geocode_one(city) for city in cities]
        await asyncio.gather(*tasks)

        # Save any new entries to cache
        self._save_cache()

        return results
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_geocoder.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/geocoder.py tests/test_geocoder.py
git commit -m "feat: add city geocoder with file cache for grid search"
```

---

## Task 6: Nearby Grid Search in Discovery

**Files:**
- Modify: `src/discovery.py` (add `_run_nearby_grid_search` method, wire into `run()`)
- Test: `tests/test_discovery.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_discovery_runs_nearby_grid_search(mock_settings):
    """Discovery should run nearby grid search when enabled."""
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True
    mock_settings.discovery.nearby_grid_offset_km = 20
    mock_settings.discovery.nearby_grid_radius_meters = 15000
    mock_settings.discovery.nearby_grid_points = "cardinal"

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_google_places', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = [
                {"name": "Suburb Store", "city": "Suburb, MA", "website": "https://suburb.com",
                 "place_id": "grid123", "vertical": "running", "address": "789 Suburb Rd", "source": "nearby_grid"}
            ]
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    results = await discovery.run(verticals=["running"], countries=["us"])

                    mock_grid.assert_called_once()
                    assert len(results) >= 1
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_discovery.py::test_discovery_runs_nearby_grid_search -v`
Expected: FAIL — `_run_nearby_grid_search` doesn't exist or isn't called

**Step 3: Implement nearby grid search**

In `src/discovery.py`, add import at top:

```python
from src.geocoder import CityGeocoder
from src.places_search import PlacesSearcher
```

Add method to `Discovery` class:

```python
async def _run_nearby_grid_search(
    self,
    verticals: list[str],
    countries: list[str]
) -> list[dict]:
    """Run nearby search at grid points around each city for suburb coverage."""
    if not self.settings.discovery.nearby_grid_enabled:
        return []

    results = []
    semaphore = asyncio.Semaphore(self.settings.search_concurrency)
    cities = self._build_city_list(countries)

    # Geocode all cities
    geocoder = CityGeocoder(api_key=self.settings.google_places_api_key)
    city_coords = await geocoder.geocode_batch(cities)

    if not city_coords:
        console.print("  [yellow]No city coordinates available, skipping grid search[/yellow]")
        return []

    offset_km = self.settings.discovery.nearby_grid_offset_km
    radius = self.settings.discovery.nearby_grid_radius_meters
    grid_mode = self.settings.discovery.nearby_grid_points

    # Build search tasks: (lat, lng, types, vertical, city)
    tasks = []
    for city, (lat, lng) in city_coords.items():
        grid_points = PlacesSearcher.generate_grid_points(lat, lng, offset_km, grid_mode)
        for point_lat, point_lng in grid_points:
            for vertical in verticals:
                types = PlacesSearcher.RETAIL_TYPES.get(vertical, [])
                if types:
                    tasks.append((point_lat, point_lng, types, vertical, city))

    console.print(f"  [dim]• {len(city_coords)} geocoded cities × grid points × {len(verticals)} verticals = {len(tasks)} nearby searches[/dim]")

    async def search(lat: float, lng: float, types: list[str], vertical: str, city: str) -> list[dict]:
        async with semaphore:
            try:
                places = await self.searcher.nearby_search(
                    latitude=lat,
                    longitude=lng,
                    radius_meters=radius,
                    included_types=types,
                    vertical=vertical
                )
                return [
                    {
                        "name": p.name,
                        "address": p.address,
                        "website": p.website,
                        "place_id": p.place_id,
                        "city": p.city or city,
                        "vertical": p.vertical,
                        "source": "nearby_grid"
                    }
                    for p in places
                ]
            except Exception as e:
                if not _is_transient_error(e):
                    logger.warning("Nearby grid search failed at (%s, %s): %s", lat, lng, e)
                return []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]Grid searching {len(tasks)} points...", total=len(tasks))

        coros = []
        for lat, lng, types, vertical, city in tasks:
            coros.append(search(lat, lng, types, vertical, city))

        for coro in asyncio.as_completed(coros):
            result = await coro
            results.extend(result)
            progress.advance(task)

    return results
```

Wire into `run()` method — add between Google Places and scraping:

```python
# In Discovery.run(), after Stage 1 (Google Places) and before Stage 2 (scraping):

# Stage 1b: Nearby grid search
console.print("[bold cyan]Discovery Stage 1b:[/bold cyan] Nearby Grid Search")
grid_results = await self._run_nearby_grid_search(verticals, countries)
all_places.extend(grid_results)
console.print(f"  [green]Found {len(grid_results)} places from grid search[/green]")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_discovery.py::test_discovery_runs_nearby_grid_search -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discovery.py tests/test_discovery.py
git commit -m "feat: add nearby grid search for metro suburb coverage"
```

---

## Task 7: Add 8 New E-commerce Platform Signatures

**Files:**
- Modify: `src/ecommerce_check.py` (expand `PLATFORM_SIGNATURES`)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("platform,html_snippet", [
    ("wix", '<script src="https://static.wixstatic.com/something.js"></script>'),
    ("ecwid", '<script src="https://app.ecwid.com/script.js"></script>'),
    ("volusion", '<link href="/v/vspfiles/templates/style.css">'),
    ("shift4shop", '<script src="https://cdn.3dcart.com/js/main.js"></script>'),
    ("opencart", '<a href="index.php?route=product/category">Shop</a>'),
    ("salesforce_commerce", '<script src="https://example.demandware.net/script.js"></script>'),
    ("sap_commerce", '<link href="/yacceleratorstorefront/style.css">'),
    ("snipcart", '<button class="snipcart-add-item" data-item-id="prod1">Buy</button>'),
])
def test_detect_new_platforms(platform, html_snippet):
    """Should detect new e-commerce platforms from HTML signatures."""
    checker = EcommerceChecker()
    detected = checker._detect_platform(html_snippet)
    assert detected == platform, f"Expected {platform}, got {detected}"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ecommerce_check.py::test_detect_new_platforms -v`
Expected: FAIL — returns `None` for new platforms

**Step 3: Add platform signatures**

In `src/ecommerce_check.py`, expand `PLATFORM_SIGNATURES`:

```python
PLATFORM_SIGNATURES = {
    # Existing
    "shopify": [r'cdn\.shopify\.com', r'myshopify\.com', r'shopify-assets'],
    "woocommerce": [r'wp-content/plugins/woocommerce', r'woocommerce', r'wc-add-to-cart', r'wp-json/wc/'],
    "bigcommerce": [r'bigcommerce\.com', r'cdn\.bc'],
    "squarespace": [r'squarespace-commerce', r'sqs-add-to-cart', r'squarespace\.com/commerce'],
    "magento": [r'Mage\.Cookies', r'mage/cookies', r'/static/version\d+/', r'Magento_Ui', r'magento-init', r'data-mage-init', r'varien/js'],
    "shopware": [r'shopware'],
    "prestashop": [r'prestashop'],
    # New platforms
    "wix": [r'wixsite\.com', r'static\.wixstatic\.com', r'wix-ecommerce', r'_api/wix-ecommerce'],
    "ecwid": [r'ecwid\.com', r'app\.ecwid\.com', r'Ecwid\.Cart'],
    "volusion": [r'volusion\.com', r'stor\.vo\.llnwd\.net', r'/v/vspfiles/'],
    "shift4shop": [r'shift4shop\.com', r'3dcart\.com', r'3dcartstores\.com'],
    "opencart": [r'route=product', r'route=checkout'],
    "salesforce_commerce": [r'demandware\.net', r'demandware\.static', r'dw/shop/v'],
    "sap_commerce": [r'/yacceleratorstorefront/'],
    "snipcart": [r'snipcart\.com', r'snipcart-add-item', r'class="snipcart-'],
}
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ecommerce_check.py::test_detect_new_platforms -v`
Expected: PASS

**Step 5: Also run existing tests to confirm no regressions**

Run: `python -m pytest tests/test_ecommerce_check.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add 8 new e-commerce platform signatures"
```

---

## Task 8: Modify _fetch_page to Return Headers

**Files:**
- Modify: `src/ecommerce_check.py` (`_fetch_page` returns headers, update callers)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_fetch_site_pages_returns_headers():
    """_fetch_site_pages should return page headers alongside HTML."""
    checker = EcommerceChecker()

    mock_headers = httpx.Headers({"x-powered-by": "Shopify", "content-type": "text/html"})

    with patch.object(checker, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body>Shop</body></html>", None, mock_headers)
        pages, fail_reason, all_headers = await checker._fetch_site_pages("https://example.com")

    assert len(pages) == 1
    assert len(all_headers) == 1
    assert all_headers[0].get("x-powered-by") == "Shopify"
```

Note: This requires importing `httpx` at the top of the test file.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ecommerce_check.py::test_fetch_site_pages_returns_headers -v`
Expected: FAIL — `_fetch_page` returns 2-tuple, not 3-tuple

**Step 3: Update _fetch_page and _fetch_site_pages**

In `src/ecommerce_check.py`:

Update `_fetch_page` to return `(html, error_reason, headers)`:

```python
async def _fetch_page(self, url: str, client: httpx.AsyncClient) -> tuple[Optional[str], Optional[str], Optional[httpx.Headers]]:
    """Fetch a single page's HTML with retries. Returns (html, error_reason, headers)."""
    for attempt in range(self.MAX_RETRIES):
        try:
            ua = random.choice(self.USER_AGENTS)
            response = await client.get(
                url,
                follow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )
            if response.status_code == 429:
                if attempt < self.MAX_RETRIES - 1:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        delay = min(int(retry_after), 30)
                    else:
                        delay = self.RETRY_DELAYS[attempt]
                    jitter = random.uniform(0.5, 2.0)
                    await asyncio.sleep(delay + jitter)
                    continue
                return None, "HTTP 429", None
            if response.status_code >= 400:
                return None, f"HTTP {response.status_code}", None
            return response.text, None, response.headers
        except httpx.TimeoutException:
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(self.RETRY_DELAYS[attempt])
                continue
            return None, "Timeout", None
        except httpx.ConnectError:
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(self.RETRY_DELAYS[attempt])
                continue
            return None, "Connection failed", None
        except Exception as e:
            return None, str(type(e).__name__), None
    return None, "Max retries", None
```

Update `_fetch_site_pages` signature to return `(pages, fail_reason, all_headers)`:

```python
async def _fetch_site_pages(self, url: str) -> tuple[list[str], Optional[str], list[httpx.Headers]]:
    """Fetch homepage + shop pages. Returns (pages, fail_reason, all_headers)."""
    all_headers = []
    async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
        homepage, fail_reason, headers = await self._fetch_page(url, client)
        if not homepage:
            return [], fail_reason, []

        pages = [homepage]
        if headers:
            all_headers.append(headers)

        if self._detect_platform(homepage):
            return pages, None, all_headers

        pages_needed = self.pages_to_check - 1
        if pages_needed <= 0:
            return pages, None, all_headers

        discovered_paths = self._find_shop_links(homepage, url)
        paths_to_try = discovered_paths + [
            p for p in self.SHOP_PATHS if p not in discovered_paths
        ]

        for path in paths_to_try[:pages_needed * 2]:
            page_url = urljoin(url + "/", path.lstrip("/"))
            html, _, page_headers = await self._fetch_page(page_url, client)
            if html and len(html) > 500:
                pages.append(html)
                if page_headers:
                    all_headers.append(page_headers)
                if len(pages) >= self.pages_to_check:
                    break

        return pages, None, all_headers
```

Update `check()` to unpack the new return value:

```python
# In check(), change:
page_contents, fail_reason = await self._fetch_site_pages(base_url)
# To:
page_contents, fail_reason, page_headers = await self._fetch_site_pages(base_url)
```

The `page_headers` variable is collected but not yet used — that comes in Task 9.

**Step 4: Run all ecommerce tests to verify they pass**

Run: `python -m pytest tests/test_ecommerce_check.py -v`
Expected: All PASS (existing tests still work since they mock `_fetch_site_pages`)

**Step 5: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "refactor: _fetch_page returns HTTP headers for platform detection"
```

---

## Task 9: Header-Based Platform Detection

**Files:**
- Modify: `src/ecommerce_check.py` (add `_detect_platform_from_headers`)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing test**

```python
import httpx

@pytest.mark.parametrize("headers_dict,expected_platform", [
    ({"x-powered-by": "Shopify"}, "shopify"),
    ({"x-shopid": "12345"}, "shopify"),
    ({"x-powered-by": "WP Engine", "set-cookie": "woocommerce_items_in_cart=0"}, "woocommerce"),
    ({"set-cookie": "_shopify_s=abc123; path=/"}, "shopify"),
    ({"set-cookie": "frontend=abc123; path=/", "x-powered-by": "Magento"}, "magento"),
    ({"server": "BigCommerce"}, "bigcommerce"),
    ({"content-type": "text/html"}, None),  # No platform signal
])
def test_detect_platform_from_headers(headers_dict, expected_platform):
    """Should detect platform from HTTP response headers."""
    checker = EcommerceChecker()
    headers = httpx.Headers(headers_dict)
    result = checker._detect_platform_from_headers(headers)
    assert result == expected_platform
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ecommerce_check.py::test_detect_platform_from_headers -v`
Expected: FAIL — method doesn't exist

**Step 3: Implement header detection**

Add to `EcommerceChecker`:

```python
# Header-based platform detection rules
HEADER_PLATFORM_RULES = {
    "shopify": {
        "x-powered-by": [r"shopify"],
        "x-shopid": [r".+"],
        "x-shopify-stage": [r".+"],
        "set-cookie": [r"_shopify_s=", r"_shopify_y="],
    },
    "woocommerce": {
        "set-cookie": [r"woocommerce_items_in_cart", r"wp_woocommerce_session"],
    },
    "magento": {
        "x-powered-by": [r"magento"],
        "set-cookie": [r"^frontend="],
    },
    "bigcommerce": {
        "server": [r"bigcommerce"],
        "x-bc-": [r".+"],
    },
}

def _detect_platform_from_headers(self, headers: httpx.Headers) -> Optional[str]:
    """Detect e-commerce platform from HTTP response headers."""
    for platform, rules in self.HEADER_PLATFORM_RULES.items():
        for header_name, patterns in rules.items():
            # Check exact header name match
            header_value = headers.get(header_name, "")
            if header_value:
                for pattern in patterns:
                    if re.search(pattern, header_value, re.IGNORECASE):
                        return platform
            # Also check headers that start with the key (e.g., x-bc-*)
            if header_name.endswith("-"):
                for key in headers.keys():
                    if key.lower().startswith(header_name.lower()):
                        return platform
    return None
```

**Step 4: Wire into `check()` method**

In the `check()` method, after checking all pages for platform detection and before calculating the final result, add:

```python
# Try header-based detection if no platform found from HTML
if not platform and page_headers:
    for headers in page_headers:
        platform = self._detect_platform_from_headers(headers)
        if platform:
            break
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ecommerce_check.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add HTTP header-based platform detection"
```

---

## Task 10: Meta Tag, Script Src, and JSON-LD Detection

**Files:**
- Modify: `src/ecommerce_check.py` (add `_detect_from_meta_tags`, `_detect_from_json_ld`)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing tests**

```python
def test_detect_platform_from_meta_generator():
    """Should detect platform from meta generator tag."""
    checker = EcommerceChecker()
    html = '<html><head><meta name="generator" content="WooCommerce 8.0"></head><body></body></html>'
    result = checker._detect_from_meta_tags(html)
    assert result == "woocommerce"


def test_detect_platform_from_script_src():
    """Should detect platform from script CDN URLs."""
    checker = EcommerceChecker()
    html = '<html><head><script src="https://cdn.shopify.com/s/files/1/0123/theme.js"></script></head><body></body></html>'
    result = checker._detect_from_meta_tags(html)
    assert result == "shopify"


def test_detect_product_from_og_type():
    """Should detect product pages from og:type meta."""
    checker = EcommerceChecker()
    html = '<html><head><meta property="og:type" content="product"></head><body></body></html>'
    indicators = checker._detect_from_meta_tags(html)
    # og:type product doesn't identify a platform, but should add an indicator
    # This returns a platform string or "product_page" sentinel
    assert indicators == "product_page"


def test_detect_ecommerce_from_json_ld_product():
    """Should detect e-commerce from JSON-LD Product structured data."""
    checker = EcommerceChecker()
    html = '''<html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Running Shoes", "offers": {"@type": "Offer", "price": "99.99"}}
    </script>
    </head><body></body></html>'''
    has_product, has_offer = checker._detect_from_json_ld(html)
    assert has_product is True
    assert has_offer is True


def test_no_json_ld_product():
    """Should return False when no Product JSON-LD found."""
    checker = EcommerceChecker()
    html = '''<html><head>
    <script type="application/ld+json">
    {"@type": "Organization", "name": "Example Corp"}
    </script>
    </head><body></body></html>'''
    has_product, has_offer = checker._detect_from_json_ld(html)
    assert has_product is False
    assert has_offer is False
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ecommerce_check.py::test_detect_platform_from_meta_generator tests/test_ecommerce_check.py::test_detect_platform_from_script_src tests/test_ecommerce_check.py::test_detect_product_from_og_type tests/test_ecommerce_check.py::test_detect_ecommerce_from_json_ld_product tests/test_ecommerce_check.py::test_no_json_ld_product -v`
Expected: FAIL

**Step 3: Implement detection methods**

Add to `EcommerceChecker`:

```python
import json as json_module

# Meta tag and script src detection patterns
META_GENERATOR_PLATFORMS = {
    "woocommerce": [r"woocommerce"],
    "shopify": [r"shopify"],
    "prestashop": [r"prestashop"],
    "magento": [r"magento"],
    "opencart": [r"opencart"],
}

SCRIPT_SRC_PLATFORMS = {
    "shopify": [r"cdn\.shopify\.com"],
    "bigcommerce": [r"cdn\d*\.bigcommerce\.com"],
    "squarespace": [r"static\d*\.squarespace\.com"],
    "ecwid": [r"app\.ecwid\.com"],
    "snipcart": [r"cdn\.snipcart\.com"],
    "wix": [r"static\.wixstatic\.com"],
}

def _detect_from_meta_tags(self, html: str) -> Optional[str]:
    """Detect platform from meta tags and script src attributes.

    Returns platform name, "product_page" for og:type=product, or None.
    """
    # Check meta generator
    generator_match = re.search(
        r'<meta\s+name=["\']generator["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if generator_match:
        generator = generator_match.group(1).lower()
        for platform, patterns in self.META_GENERATOR_PLATFORMS.items():
            for pattern in patterns:
                if re.search(pattern, generator):
                    return platform

    # Check script src attributes
    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    for src in script_srcs:
        for platform, patterns in self.SCRIPT_SRC_PLATFORMS.items():
            for pattern in patterns:
                if re.search(pattern, src, re.IGNORECASE):
                    return platform

    # Check og:type for product pages
    og_match = re.search(
        r'<meta\s+property=["\']og:type["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if og_match and og_match.group(1).lower() in ("product", "product.item"):
        return "product_page"

    return None


def _detect_from_json_ld(self, html: str) -> tuple[bool, bool]:
    """Detect Product/Offer structured data from JSON-LD.

    Returns (has_product, has_offer).
    """
    has_product = False
    has_offer = False

    json_ld_blocks = re.findall(
        r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    )

    for block in json_ld_blocks:
        try:
            data = json_module.loads(block.strip())
            # Handle both single objects and arrays
            items = data if isinstance(data, list) else [data]
            for item in items:
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    types = [t.lower() for t in item_type]
                else:
                    types = [item_type.lower()]

                if "product" in types:
                    has_product = True
                if "offer" in types or "aggregateoffer" in types:
                    has_offer = True

                # Check nested offers
                offers = item.get("offers", {})
                if isinstance(offers, dict):
                    offer_type = offers.get("@type", "").lower()
                    if offer_type in ("offer", "aggregateoffer"):
                        has_offer = True
                elif isinstance(offers, list):
                    has_offer = True
        except (json_module.JSONDecodeError, AttributeError):
            continue

    return has_product, has_offer
```

**Step 4: Wire into `check()` method**

In `check()`, after the header detection block and before calculating the final result, add:

```python
# Try meta tag / script src detection if no platform found
if not platform:
    for content in page_contents:
        meta_result = self._detect_from_meta_tags(content)
        if meta_result and meta_result != "product_page":
            platform = meta_result
            break
        elif meta_result == "product_page":
            all_indicators.append("meta:og_type_product")
            total_score += 3

# Check JSON-LD structured data for product signals
for content in page_contents:
    has_product, has_offer = self._detect_from_json_ld(content)
    if has_product:
        all_indicators.append("jsonld:Product")
        total_score += 3
    if has_offer:
        all_indicators.append("jsonld:Offer")
        total_score += 2
```

**Step 5: Run all tests to verify they pass**

Run: `python -m pytest tests/test_ecommerce_check.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add meta tag, script src, and JSON-LD e-commerce detection"
```

---

## Task 11: Playwright Fallback — SPA Trigger Detection

**Files:**
- Modify: `src/ecommerce_check.py` (add `_should_try_playwright`)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing tests**

```python
def test_spa_trigger_detects_nextjs():
    """Should trigger Playwright for Next.js SPA with no e-commerce signals."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body></html>'
    assert checker._should_try_playwright(html, platform=None, score=0) is True


def test_spa_trigger_detects_react_app():
    """Should trigger for React app with minimal content."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="root"></div><script src="/static/js/bundle.js"></script></body></html>'
    assert checker._should_try_playwright(html, platform=None, score=0) is True


def test_spa_trigger_skips_when_platform_found():
    """Should NOT trigger when platform already detected."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="root"></div></body></html>'
    assert checker._should_try_playwright(html, platform="shopify", score=0) is False


def test_spa_trigger_skips_when_score_positive():
    """Should NOT trigger when e-commerce signals already found."""
    checker = EcommerceChecker()
    html = '<html><head></head><body><div id="root"></div></body></html>'
    assert checker._should_try_playwright(html, platform=None, score=4) is False


def test_spa_trigger_skips_content_rich_pages():
    """Should NOT trigger for pages with lots of visible text."""
    checker = EcommerceChecker()
    # Page with substantial text content (not a SPA shell)
    html = '<html><head></head><body>' + '<p>Lorem ipsum dolor sit amet. </p>' * 200 + '</body></html>'
    assert checker._should_try_playwright(html, platform=None, score=0) is False
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ecommerce_check.py -k "spa_trigger" -v`
Expected: FAIL

**Step 3: Implement SPA trigger detection**

Add to `EcommerceChecker`:

```python
# JS framework markers that indicate SPA rendering
SPA_MARKERS = [
    r'__NEXT_DATA__',
    r'__NUXT__',
    r'id=["\']root["\']',
    r'id=["\']app["\']',
    r'id=["\']__next["\']',
    r'/_next/static/',
    r'/_nuxt/',
    r'bundle\.js',
    r'chunk\.js',
]

def _should_try_playwright(self, html: str, platform: Optional[str], score: int) -> bool:
    """Determine if Playwright fallback should be attempted.

    Triggers when: HTML returned successfully, no platform detected,
    no e-commerce score, SPA markers present, and minimal visible text.
    """
    # Don't retry if we already found signals
    if platform is not None:
        return False
    if score > 0:
        return False

    # Check for SPA markers
    has_spa_marker = False
    for marker in self.SPA_MARKERS:
        if re.search(marker, html, re.IGNORECASE):
            has_spa_marker = True
            break

    if not has_spa_marker:
        return False

    # Check visible text content — strip tags and measure
    visible_text = re.sub(r'<[^>]+>', '', html)
    visible_text = re.sub(r'\s+', ' ', visible_text).strip()

    # If page has substantial visible text, it's not a JS shell
    if len(visible_text) > 2000:
        return False

    return True
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ecommerce_check.py -k "spa_trigger" -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add SPA trigger detection for Playwright fallback"
```

---

## Task 12: Playwright Fallback Execution

**Files:**
- Modify: `src/ecommerce_check.py` (add `_playwright_fetch`, update `check()`)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_playwright_fallback_triggered_for_spa():
    """check() should use Playwright fallback for SPA sites with no signals."""
    checker = EcommerceChecker(playwright_fallback_enabled=True, playwright_timeout=15)

    # SPA shell with no e-commerce signals
    spa_html = '<html><head></head><body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body></html>'
    # Rendered HTML with Shopify signals
    rendered_html = '<html><body><div id="__next"><button class="add-to-cart">Add to Cart</button><script src="https://cdn.shopify.com/s/files/1/theme.js"></script></div></body></html>'

    mock_headers = httpx.Headers({"content-type": "text/html"})

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([spa_html], None, [mock_headers])
        with patch.object(checker, '_playwright_fetch', new_callable=AsyncMock) as mock_pw:
            mock_pw.return_value = rendered_html

            result = await checker.check("https://spa-store.com")

            mock_pw.assert_called_once()
            assert result.has_ecommerce is True
            assert result.platform == "shopify"


@pytest.mark.asyncio
async def test_playwright_fallback_not_triggered_when_disabled():
    """check() should skip Playwright when disabled."""
    checker = EcommerceChecker(playwright_fallback_enabled=False)

    spa_html = '<html><head></head><body><div id="__next"></div><script src="/_next/static/chunks/main.js"></script></body></html>'
    mock_headers = httpx.Headers({"content-type": "text/html"})

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([spa_html], None, [mock_headers])

        result = await checker.check("https://spa-store.com")

        assert result.has_ecommerce is False
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ecommerce_check.py::test_playwright_fallback_triggered_for_spa tests/test_ecommerce_check.py::test_playwright_fallback_not_triggered_when_disabled -v`
Expected: FAIL

**Step 3: Implement Playwright fallback**

Update `EcommerceChecker.__init__`:

```python
def __init__(self, pages_to_check: int = None, playwright_fallback_enabled: bool = False, playwright_timeout: int = 15, **kwargs):
    self.pages_to_check = pages_to_check or self.DEFAULT_PAGES_TO_CHECK
    self.playwright_fallback_enabled = playwright_fallback_enabled
    self.playwright_timeout = playwright_timeout
    self._playwright_count = 0  # Track how many times Playwright was used
    self._total_checked = 0  # Track total sites checked
```

Add `_playwright_fetch` method:

```python
async def _playwright_fetch(self, url: str) -> Optional[str]:
    """Fetch a page using Playwright for JS rendering. Returns rendered HTML."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=self.playwright_timeout * 1000)
            html = await page.content()
            await browser.close()
            return html
    except Exception:
        return None
```

Update `check()` — at the end, before the final return, add Playwright fallback logic:

```python
# After initial analysis, before final return:
self._total_checked += 1

# Playwright fallback for SPA sites
if (
    self.playwright_fallback_enabled
    and not has_ecommerce
    and page_contents
    and self._should_try_playwright(page_contents[0], platform, total_score)
):
    # Check rate cap: max_percent of total sites
    max_pw = max(1, int(self._total_checked * 0.2))  # 20% cap
    if self._playwright_count < max_pw:
        self._playwright_count += 1
        rendered_html = await self._playwright_fetch(base_url)
        if rendered_html:
            # Re-analyze with rendered content
            pw_platform = self._detect_platform(rendered_html)
            if not pw_platform:
                pw_platform = self._detect_from_meta_tags(rendered_html)
                if pw_platform == "product_page":
                    pw_platform = None
                    all_indicators.append("meta:og_type_product")
                    total_score += 3

            pw_indicators, pw_score = self._count_indicators(rendered_html)
            all_indicators.extend(pw_indicators)
            total_score += pw_score

            if pw_platform:
                platform = pw_platform

            pw_marketplaces, pw_links = self._detect_marketplaces(rendered_html)
            all_marketplaces.update(pw_marketplaces)
            for mp, link in pw_links.items():
                if mp not in all_marketplace_links:
                    all_marketplace_links[mp] = link

            # Recalculate
            has_payment_or_price = any(
                "payment:" in i or "price:" in i for i in all_indicators
            )
            has_ecommerce = (
                platform is not None
                or (total_score >= 4 and has_payment_or_price)
                or total_score >= 8
            )
            confidence = min(total_score / 10, 1.0) if has_ecommerce else total_score / 15
            final_marketplaces = sorted(list(all_marketplaces))
            priority = "high" if final_marketplaces else "medium"

            if platform:
                return EcommerceResult(
                    url=url,
                    has_ecommerce=True,
                    confidence=0.95,
                    indicators_found=[f"platform:{platform}", "playwright_fallback"] + list(set(all_indicators)),
                    platform=platform,
                    pages_checked=pages_checked + 1,
                    marketplaces=final_marketplaces,
                    marketplace_links=all_marketplace_links,
                    priority=priority
                )

            if has_ecommerce:
                return EcommerceResult(
                    url=url,
                    has_ecommerce=True,
                    confidence=confidence,
                    indicators_found=["playwright_fallback"] + list(set(all_indicators)),
                    platform=platform,
                    pages_checked=pages_checked + 1,
                    marketplaces=final_marketplaces,
                    marketplace_links=all_marketplace_links,
                    priority=priority
                )
```

**Step 4: Update pipeline to pass Playwright settings to EcommerceChecker**

In `src/pipeline.py`, update `stage_3_ecommerce` where `EcommerceChecker` is constructed:

```python
checker = EcommerceChecker(
    pages_to_check=settings.ecommerce_pages_to_check,
    playwright_fallback_enabled=settings.ecommerce_playwright_fallback_enabled,
    playwright_timeout=settings.ecommerce_playwright_fallback_timeout,
)
```

**Step 5: Run all tests to verify they pass**

Run: `python -m pytest tests/test_ecommerce_check.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/ecommerce_check.py src/pipeline.py tests/test_ecommerce_check.py
git commit -m "feat: add Playwright fallback for JS-rendered e-commerce stores"
```

---

## Task 13: Full Integration Test

**Files:**
- Test: `tests/test_ecommerce_check.py`
- Test: `tests/test_discovery.py`

**Step 1: Write integration test for enhanced e-commerce detection**

```python
@pytest.mark.asyncio
async def test_full_enhanced_ecommerce_detection():
    """Integration test: platform expansion + headers + meta + JSON-LD all work together."""
    checker = EcommerceChecker()

    # Page with Wix platform (new), JSON-LD product, and marketplace
    html = '''<html>
    <head>
        <script src="https://static.wixstatic.com/something.js"></script>
        <meta property="og:type" content="product">
        <script type="application/ld+json">
        {"@type": "Product", "name": "Widget", "offers": {"@type": "Offer", "price": "29.99"}}
        </script>
    </head>
    <body>
        <button>Add to Cart</button>
        <span>$29.99</span>
        <a href="https://amazon.com/stores/WidgetCo">Amazon Store</a>
    </body>
    </html>'''

    mock_headers = httpx.Headers({"content-type": "text/html"})

    with patch.object(checker, '_fetch_site_pages', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([html], None, [mock_headers])
        result = await checker.check("https://widgetco.com")

    assert result.has_ecommerce is True
    assert result.platform == "wix"
    assert result.confidence >= 0.9
    assert "amazon" in result.marketplaces
```

**Step 2: Write integration test for discovery grid search flow**

```python
@pytest.mark.asyncio
async def test_discovery_full_flow_with_grid_search(mock_settings):
    """Integration test: grid search results merge with text search results."""
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True
    mock_settings.discovery.nearby_grid_offset_km = 20
    mock_settings.discovery.nearby_grid_radius_meters = 15000
    mock_settings.discovery.nearby_grid_points = "cardinal"

    discovery = Discovery(mock_settings)

    text_results = [
        {"name": "Downtown Store", "city": "Boston, MA", "website": "https://downtown.com",
         "place_id": "text1", "vertical": "running", "address": "1 Main St", "source": "google_places"}
    ]
    grid_results = [
        {"name": "Suburb Store", "city": "Cambridge, MA", "website": "https://suburb.com",
         "place_id": "grid1", "vertical": "running", "address": "2 Suburb Rd", "source": "nearby_grid"}
    ]

    with patch.object(discovery, '_run_google_places', new_callable=AsyncMock, return_value=text_results):
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock, return_value=grid_results):
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock, return_value=[]):
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock, return_value=[]):
                    results = await discovery.run(verticals=["running"], countries=["us"])

    assert len(results) == 2
    names = [r["name"] for r in results]
    assert "Downtown Store" in names
    assert "Suburb Store" in names
```

**Step 3: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/test_ecommerce_check.py tests/test_discovery.py
git commit -m "test: add integration tests for enhanced discovery and e-commerce"
```

---

## Task 14: Final Run — Full Test Suite

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS with no regressions

**Step 2: If any failures, fix them**

Address any test failures found in the full suite run.

**Step 3: Final commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: address test regressions from discovery/ecommerce improvements"
```
