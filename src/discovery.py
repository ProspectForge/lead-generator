# src/discovery.py
import asyncio
import logging
import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.places_search import PlacesSearcher
from src.brand_expander import BrandExpander
from src.deduplicator import Deduplicator, MergedPlace
from src.scraper.bestof_scraper import BestOfScraper

console = Console()
logger = logging.getLogger(__name__)

# Limits for sampling/batching
SAMPLE_CITIES_LIMIT = 10
BRANDS_TO_EXPAND_LIMIT = 20

# Transient error codes that should be silently ignored (handled by retries)
SILENT_ERROR_CODES = {429, 503, 500}


def _is_transient_error(e: Exception) -> bool:
    """Check if exception is a transient error that should be silently ignored."""
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in SILENT_ERROR_CODES
    if isinstance(e, httpx.TimeoutException):
        return True
    return False


class Discovery:
    """Orchestrates multi-source lead discovery."""

    def __init__(self, settings):
        self.settings = settings
        self.searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        self.expander = BrandExpander(api_key=settings.google_places_api_key)
        self.deduplicator = Deduplicator()
        self.bestof_scraper = BestOfScraper(firecrawl_api_key=settings.firecrawl_api_key)

    async def run(
        self,
        verticals: list[str],
        countries: list[str]
    ) -> list[dict]:
        """Run full discovery pipeline."""
        all_places = []

        # Stage 1: Google Places search
        console.print("[bold cyan]Discovery Stage 1:[/bold cyan] Google Places Search")
        gp_results = await self._run_google_places(verticals, countries)
        all_places.extend(gp_results)
        console.print(f"  [green]Found {len(gp_results)} places from Google[/green]")

        # Stage 2: Web scraping
        console.print("[bold cyan]Discovery Stage 2:[/bold cyan] Web Scraping")
        scrape_results = await self._run_scraping(verticals, countries)
        all_places.extend(scrape_results)
        console.print(f"  [green]Found {len(scrape_results)} places from scraping[/green]")

        # Stage 3: Brand expansion
        console.print("[bold cyan]Discovery Stage 3:[/bold cyan] Brand Expansion")
        expand_results = await self._run_brand_expansion(all_places, countries)
        all_places.extend(expand_results)
        console.print(f"  [green]Found {len(expand_results)} additional locations[/green]")

        # Stage 4: Deduplicate
        console.print("[bold cyan]Discovery Stage 4:[/bold cyan] Deduplication")
        merged = self.deduplicator.deduplicate(all_places)
        console.print(f"  [green]Merged to {len(merged)} unique places[/green]")

        # Convert MergedPlace to dict for pipeline compatibility
        return [self._merged_to_dict(m) for m in merged]

    def _merged_to_dict(self, merged: MergedPlace) -> dict:
        """Convert MergedPlace to dict matching pipeline expectations."""
        return {
            "name": merged.name,
            "address": merged.address,
            "website": merged.website,
            "place_id": merged.place_id,
            "city": merged.city,
            "vertical": merged.vertical,
        }

    def _build_city_list(self, countries: list[str]) -> list[str]:
        """Build list of cities from the given countries."""
        cities = []
        for country in countries:
            cities.extend(self.settings.cities.get(country, []))
        return cities

    async def _run_google_places(
        self,
        verticals: list[str],
        countries: list[str]
    ) -> list[dict]:
        """Run enhanced Google Places searches."""
        results = []
        semaphore = asyncio.Semaphore(self.settings.search_concurrency)

        cities = self._build_city_list(countries)

        # Build search tasks
        tasks = []
        for vertical in verticals:
            for query in self.settings.search_queries.get(vertical, []):
                for city in cities:
                    tasks.append((city, query, vertical))

        async def search(city: str, query: str, vertical: str) -> list[dict]:
            async with semaphore:
                try:
                    places = await self.searcher.search(query, city, vertical=vertical)
                    return [
                        {
                            "name": p.name,
                            "address": p.address,
                            "website": p.website,
                            "place_id": p.place_id,
                            "city": p.city,
                            "vertical": p.vertical,
                            "source": "google_places"
                        }
                        for p in places
                    ]
                except Exception as e:
                    if not _is_transient_error(e):
                        logger.warning("Google Places search failed for %s in %s: %s", query, city, e)
                    return []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Searching {len(tasks)} combinations...", total=len(tasks))

            coros = []
            for city, query, vertical in tasks:
                coros.append(search(city, query, vertical))

            for coro in asyncio.as_completed(coros):
                result = await coro
                results.extend(result)
                progress.advance(task)

        return results

    async def _run_scraping(
        self,
        verticals: list[str],
        countries: list[str]
    ) -> list[dict]:
        """Run web scraping for additional leads."""
        results = []

        cities = self._build_city_list(countries)

        # Sample cities for best-of scraping (limit to avoid too many requests)
        sample_cities = cities[:SAMPLE_CITIES_LIMIT]

        for vertical in verticals:
            queries = self.settings.search_queries.get(vertical, [])
            if not queries:
                continue

            query = queries[0]  # Use first query as representative

            for city in sample_cities:
                try:
                    brands = await self.bestof_scraper.scrape_city(city, query)
                    for brand in brands:
                        results.append({
                            "name": brand.name,
                            "address": "",
                            "website": brand.website,
                            "place_id": None,
                            "city": city,
                            "vertical": vertical,
                            "source": "bestof_scrape"
                        })
                except Exception as e:
                    if not _is_transient_error(e):
                        logger.warning("Scraping failed for %s in %s: %s", query, city, e)

        return results

    async def _run_brand_expansion(
        self,
        places: list[dict],
        countries: list[str]
    ) -> list[dict]:
        """Expand promising brands to all cities."""
        results = []

        all_cities = self._build_city_list(countries)

        # Group by website domain to find multi-location brands
        from collections import defaultdict
        by_domain = defaultdict(list)

        for place in places:
            if place.get("website"):
                domain = self.deduplicator._normalize_domain(place["website"])
                if domain:
                    by_domain[domain].append(place)

        # Find brands worth expanding
        brands_to_expand = []
        for domain, domain_places in by_domain.items():
            cities_found = list(set(p["city"] for p in domain_places))

            if self.expander.should_expand(
                brand_name=domain_places[0]["name"],
                cities_found=cities_found,
                location_count=len(domain_places)
            ):
                brands_to_expand.append({
                    "name": domain_places[0]["name"],
                    "website": domain_places[0]["website"],
                    "vertical": domain_places[0]["vertical"],
                    "cities_found": cities_found
                })

        console.print(f"  [dim]Expanding {len(brands_to_expand)} promising brands...[/dim]")

        # Expand each brand
        for brand in brands_to_expand[:BRANDS_TO_EXPAND_LIMIT]:
            # Only search cities we haven't already found
            cities_to_search = [c for c in all_cities if c not in brand["cities_found"]]

            try:
                expanded = await self.expander.expand_brand(
                    brand_name=brand["name"],
                    known_website=brand["website"],
                    cities=cities_to_search,
                    vertical=brand["vertical"]
                )
                results.extend(expanded)
            except Exception as e:
                if not _is_transient_error(e):
                    logger.warning("Brand expansion failed for %s: %s", brand["name"], e)

        return results
