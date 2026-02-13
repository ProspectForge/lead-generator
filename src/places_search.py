# src/places_search.py
import asyncio
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
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri,places.id"
        }

    async def _make_request(self, payload: dict) -> dict:
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.BASE_URL,
                        headers=self.headers,
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
