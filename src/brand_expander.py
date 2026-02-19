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
