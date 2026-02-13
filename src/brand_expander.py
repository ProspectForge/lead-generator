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
