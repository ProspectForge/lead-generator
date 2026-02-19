# src/places_search.py
import asyncio
import math
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
    NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds

    # Google Places type mapping for retail
    RETAIL_TYPES = {
        "sporting_goods": ["sporting_goods_store", "bicycle_store"],
        "health_wellness": ["health_food_store", "drugstore"],
        "apparel": ["clothing_store", "shoe_store"],
        "outdoor_camping": ["camping_store", "outdoor_recreation_store"],
    }

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri,places.id"
        }

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
            except httpx.HTTPStatusError as e:
                last_error = e
                # Retry on 503 (Service Unavailable) or 429 (Rate Limit)
                if e.response.status_code in (503, 429, 500):
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
