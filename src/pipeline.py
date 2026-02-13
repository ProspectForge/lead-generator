# src/pipeline.py
import asyncio
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress

from src.config import settings
from src.places_search import PlacesSearcher, PlaceResult
from src.brand_grouper import BrandGrouper, BrandGroup
from src.ecommerce_check import EcommerceChecker
from src.linkedin_enrich import LinkedInEnricher

console = Console()

class Pipeline:
    def __init__(self):
        self.data_dir = Path(__file__).parent.parent / "data"
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.output_dir = self.data_dir / "output"

        # Ensure directories exist
        for d in [self.raw_dir, self.processed_dir, self.output_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def stage_1_search(self, verticals: list[str], countries: list[str]) -> list[dict]:
        """Search Google Places for businesses."""
        searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        all_results = []

        cities = []
        for country in countries:
            cities.extend(settings.cities.get(country, []))

        queries = []
        for vertical in verticals:
            queries.extend(settings.search_queries.get(vertical, []))

        console.print(f"[bold]Stage 1:[/bold] Searching {len(cities)} cities x {len(queries)} queries")

        for city in cities:
            for query in queries:
                try:
                    results = await searcher.search(query, city, vertical=vertical)
                    for r in results:
                        all_results.append({
                            "name": r.name,
                            "address": r.address,
                            "website": r.website,
                            "place_id": r.place_id,
                            "city": r.city,
                            "vertical": r.vertical
                        })
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    console.print(f"[red]Error searching {query} in {city}: {e}[/red]")

        # Save raw results
        raw_file = self.raw_dir / f"places_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(raw_file, 'w') as f:
            json.dump(all_results, f, indent=2)

        console.print(f"[green]Found {len(all_results)} places[/green]")
        return all_results

    def stage_2_group(self, places: list[dict]) -> list[BrandGroup]:
        """Group places by brand and filter by location count."""
        grouper = BrandGrouper(min_locations=3, max_locations=10)
        groups = grouper.group(places)
        filtered = grouper.filter(groups)

        console.print(f"[bold]Stage 2:[/bold] Grouped into {len(groups)} brands, {len(filtered)} have 3-10 locations")
        return filtered

    async def stage_3_ecommerce(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Check each brand for e-commerce presence."""
        checker = EcommerceChecker(api_key=settings.firecrawl_api_key)
        ecommerce_brands = []

        console.print(f"[bold]Stage 3:[/bold] Checking {len(brands)} brands for e-commerce")

        for brand in brands:
            if not brand.website:
                continue
            try:
                result = await checker.check(brand.website)
                if result.has_ecommerce:
                    ecommerce_brands.append(brand)
                await asyncio.sleep(0.5)  # Rate limiting
            except Exception as e:
                console.print(f"[red]Error checking {brand.website}: {e}[/red]")

        console.print(f"[green]{len(ecommerce_brands)} brands have e-commerce[/green]")
        return ecommerce_brands

    async def stage_4_linkedin(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich brands with LinkedIn data."""
        enricher = LinkedInEnricher(api_key=settings.firecrawl_api_key)
        enriched = []

        console.print(f"[bold]Stage 4:[/bold] Enriching {len(brands)} brands with LinkedIn data")

        for brand in brands:
            try:
                result = await enricher.enrich(brand.normalized_name, brand.website or "")

                enriched.append({
                    "brand_name": brand.normalized_name.title(),
                    "location_count": brand.location_count,
                    "website": brand.website,
                    "has_ecommerce": True,
                    "cities": ", ".join(brand.cities[:5]),
                    "linkedin_company": result.linkedin_company_url or "",
                    "contact_1_name": result.contacts[0].name if len(result.contacts) > 0 else "",
                    "contact_1_title": result.contacts[0].title if len(result.contacts) > 0 else "",
                    "contact_1_linkedin": result.contacts[0].linkedin_url if len(result.contacts) > 0 else "",
                    "contact_2_name": result.contacts[1].name if len(result.contacts) > 1 else "",
                    "contact_2_title": result.contacts[1].title if len(result.contacts) > 1 else "",
                    "contact_2_linkedin": result.contacts[1].linkedin_url if len(result.contacts) > 1 else "",
                    "contact_3_name": result.contacts[2].name if len(result.contacts) > 2 else "",
                    "contact_3_title": result.contacts[2].title if len(result.contacts) > 2 else "",
                    "contact_3_linkedin": result.contacts[2].linkedin_url if len(result.contacts) > 2 else "",
                    "contact_4_name": result.contacts[3].name if len(result.contacts) > 3 else "",
                    "contact_4_title": result.contacts[3].title if len(result.contacts) > 3 else "",
                    "contact_4_linkedin": result.contacts[3].linkedin_url if len(result.contacts) > 3 else "",
                })
                await asyncio.sleep(1.0)  # Rate limiting
            except Exception as e:
                console.print(f"[red]Error enriching {brand.normalized_name}: {e}[/red]")

        console.print(f"[green]Enriched {len(enriched)} brands[/green]")
        return enriched

    def stage_5_export(self, data: list[dict]) -> str:
        """Export to CSV."""
        df = pd.DataFrame(data)
        output_file = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(output_file, index=False)

        console.print(f"[bold green]Exported {len(data)} leads to {output_file}[/bold green]")
        return str(output_file)

    async def run(
        self,
        verticals: list[str] = ["health_wellness", "sporting_goods", "apparel"],
        countries: list[str] = ["us", "canada"]
    ) -> str:
        """Run the full pipeline."""
        console.print("[bold blue]Starting Lead Generator Pipeline[/bold blue]")

        # Stage 1: Search
        places = await self.stage_1_search(verticals, countries)

        # Stage 2: Group and filter
        brands = self.stage_2_group(places)

        # Stage 3: E-commerce check
        ecommerce_brands = await self.stage_3_ecommerce(brands)

        # Stage 4: LinkedIn enrichment
        enriched = await self.stage_4_linkedin(ecommerce_brands)

        # Stage 5: Export
        output_file = self.stage_5_export(enriched)

        console.print("[bold green]Pipeline complete![/bold green]")
        return output_file
