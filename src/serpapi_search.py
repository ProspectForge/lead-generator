# src/serpapi_search.py
"""SerpAPI Google Maps search — cost-effective replacement for Google Places API.

Uses SerpAPI's Google Maps engine to get the same business data at ~$50-130/month
instead of $4000+ via direct Google Places API.

Docs: https://serpapi.com/google-maps-api
"""
import asyncio
import hashlib
import json
import math
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PlaceResult:
    name: str
    address: str
    website: Optional[str]
    place_id: str
    city: str
    vertical: str


class SerpApiSearcher:
    """Searches for businesses via SerpAPI Google Maps engine."""

    BASE_URL = "https://serpapi.com/search.json"
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]

    # Map verticals to search keywords (used for nearby search queries)
    RETAIL_TYPES = {
        "sporting_goods": ["sporting goods store", "sports store"],
        "health_wellness": ["health food store", "vitamin store", "wellness store"],
        "apparel": ["clothing store", "boutique", "shoe store"],
        "outdoor_camping": ["outdoor store", "camping store"],
        "pet_supplies": ["pet store", "pet supply"],
        "beauty_cosmetics": ["beauty store", "cosmetics store"],
        "specialty_food": ["specialty food store", "gourmet store", "organic store"],
        "running_athletic": ["running store", "athletic store"],
        "cycling": ["bicycle store", "bike shop"],
        "baby_kids": ["baby store", "kids store"],
        "home_goods": ["home goods store", "furniture store", "housewares store"],
    }

    CACHE_DIR = Path(__file__).parent.parent / "data" / "search_cache"
    DEFAULT_CACHE_TTL_DAYS = 90

    def __init__(self, api_key: str, cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS):
        self.api_key = api_key
        self.cache_ttl_seconds = cache_ttl_days * 86400
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, params: dict) -> str:
        """Generate a deterministic cache key from request params."""
        # Exclude api_key from cache key (not relevant to results)
        cache_params = {k: v for k, v in sorted(params.items()) if k != "api_key"}
        raw = json.dumps(cache_params, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _get_cached(self, params: dict) -> Optional[dict]:
        """Return cached response if fresh enough, else None."""
        key = self._cache_key(params)
        cache_file = self.CACHE_DIR / f"{key}.json"
        if not cache_file.exists():
            return None
        try:
            data = json.loads(cache_file.read_text())
            cached_at = data.get("_cached_at", 0)
            if time.time() - cached_at > self.cache_ttl_seconds:
                return None  # Expired
            return data.get("response")
        except (json.JSONDecodeError, KeyError):
            return None

    def _set_cached(self, params: dict, response: dict):
        """Write response to cache."""
        key = self._cache_key(params)
        cache_file = self.CACHE_DIR / f"{key}.json"
        cache_file.write_text(json.dumps({
            "_cached_at": time.time(),
            "_params": {k: v for k, v in params.items() if k != "api_key"},
            "response": response,
        }, indent=2))

    async def _make_request(self, params: dict) -> dict:
        """Make a request to SerpAPI with caching and retries."""
        params["engine"] = "google_maps"

        # Check cache first
        cached = self._get_cached(params)
        if cached is not None:
            return cached

        params["api_key"] = self.api_key

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(self.BASE_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                    # Cache the response (strip api_key before caching)
                    cache_params = {k: v for k, v in params.items() if k != "api_key"}
                    self._set_cached(cache_params, data)
                    return data
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (429, 503, 500):
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(self.RETRY_DELAYS[attempt])
                        continue
                raise
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise
        raise last_error

    async def search(self, query: str, city: str, vertical: str = "") -> list[PlaceResult]:
        """Search for businesses by query in a city.

        Args:
            query: Search query (e.g., "running store")
            city: City name (e.g., "Boston, MA")
            vertical: Vertical category key

        Returns:
            List of PlaceResult matching the query in the city.
        """
        params = {
            "q": f"{query} in {city}",
            "type": "search",
        }

        data = await self._make_request(params)
        return self._parse_results(data, city, vertical)

    async def nearby_search(
        self,
        latitude: float,
        longitude: float,
        radius_meters: int = 5000,
        included_types: list[str] = None,
        vertical: str = ""
    ) -> list[PlaceResult]:
        """Search for places within a radius of coordinates.

        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_meters: Search radius in meters
            included_types: Search keywords for this vertical
            vertical: Vertical category key
        """
        zoom = self._radius_to_zoom(radius_meters)

        # Build query from types or vertical
        if included_types:
            query = included_types[0]
        elif vertical and vertical in self.RETAIL_TYPES:
            query = self.RETAIL_TYPES[vertical][0]
        else:
            query = "retail store"

        params = {
            "q": query,
            "ll": f"@{latitude},{longitude},{zoom}z",
            "type": "search",
        }

        data = await self._make_request(params)
        return self._parse_results(data, "", vertical)

    def _parse_results(self, data: dict, city: str, vertical: str) -> list[PlaceResult]:
        """Parse SerpAPI Google Maps response into PlaceResult list."""
        results = []
        local_results = data.get("local_results", [])

        for place in local_results:
            address = place.get("address", "")
            result_city = city or self._extract_city_from_address(address)

            results.append(PlaceResult(
                name=place.get("title", ""),
                address=address,
                website=place.get("website"),
                place_id=place.get("place_id", ""),
                city=result_city,
                vertical=vertical,
            ))

        return results

    @staticmethod
    def _radius_to_zoom(radius_meters: int) -> int:
        """Convert radius in meters to approximate Google Maps zoom level."""
        if radius_meters <= 1000:
            return 15
        elif radius_meters <= 3000:
            return 14
        elif radius_meters <= 5000:
            return 13
        elif radius_meters <= 10000:
            return 12
        elif radius_meters <= 25000:
            return 11
        elif radius_meters <= 50000:
            return 10
        else:
            return 9

    @staticmethod
    def _extract_city_from_address(address: str) -> str:
        """Extract city name from formatted address."""
        parts = address.split(",")
        if len(parts) >= 2:
            return parts[-2].strip()
        return ""

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
        """
        lat_offset = offset_km / 111.0
        lng_offset = offset_km / (111.0 * math.cos(math.radians(center_lat)))

        points = [(center_lat, center_lng)]

        # Cardinal directions
        points.append((center_lat + lat_offset, center_lng))  # North
        points.append((center_lat - lat_offset, center_lng))  # South
        points.append((center_lat, center_lng + lng_offset))  # East
        points.append((center_lat, center_lng - lng_offset))  # West

        if mode == "full":
            points.append((center_lat + lat_offset, center_lng + lng_offset))  # NE
            points.append((center_lat + lat_offset, center_lng - lng_offset))  # NW
            points.append((center_lat - lat_offset, center_lng + lng_offset))  # SE
            points.append((center_lat - lat_offset, center_lng - lng_offset))  # SW

        return points
