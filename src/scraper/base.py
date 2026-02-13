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
