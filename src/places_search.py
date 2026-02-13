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
