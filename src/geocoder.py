# src/geocoder.py
"""City geocoding using OpenStreetMap Nominatim (free, no API key)."""
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent.parent / "data" / "city_coordinates.json"


class CityGeocoder:
    """Geocodes city names to lat/lng using OpenStreetMap Nominatim with file cache."""

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, concurrency: int = 1):
        """Initialize geocoder.

        Args:
            concurrency: Max parallel requests (Nominatim policy: 1 req/sec).
        """
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

    async def _geocode_api(self, city: str) -> list[dict]:
        """Call Nominatim search API."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.NOMINATIM_URL,
                params={
                    "q": city,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 0,
                },
                headers={"User-Agent": "LeadGenerator/1.0"},
            )
            response.raise_for_status()
            return response.json()

    async def geocode(self, city: str) -> Optional[tuple[float, float]]:
        """Get lat/lng for a city. Returns cached result if available."""
        if city in self._cache:
            return self._cache[city]

        try:
            results = await self._geocode_api(city)
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
                coords = (lat, lng)
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
                # Nominatim requires max 1 request per second
                await asyncio.sleep(1.0)

        tasks = [geocode_one(city) for city in cities]
        await asyncio.gather(*tasks)

        # Save any new entries to cache
        self._save_cache()

        return results
