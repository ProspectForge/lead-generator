# src/pipeline.py
import asyncio
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

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

    def _show_stage_header(self, stage_num: int, title: str, description: str):
        """Display a formatted stage header."""
        console.print()
        console.print(Panel(
            f"[bold]{description}[/bold]",
            title=f"[bold cyan]Stage {stage_num}: {title}[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        ))

    async def stage_1_search(self, verticals: list[str], countries: list[str]) -> list[dict]:
        """Search Google Places for businesses."""
        self._show_stage_header(1, "Google Places Search", "Finding retail businesses across cities")

        searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        all_results = []

        cities = []
        for country in countries:
            cities.extend(settings.cities.get(country, []))

        # Build queries with their verticals
        query_vertical_pairs = []
        for vertical in verticals:
            for query in settings.search_queries.get(vertical, []):
                query_vertical_pairs.append((query, vertical))

        total_searches = len(cities) * len(query_vertical_pairs)
        console.print(f"  [dim]• {len(cities)} cities × {len(query_vertical_pairs)} queries = {total_searches} searches[/dim]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Searching...", total=total_searches)
            search_count = 0
            found_count = 0

            for city in cities:
                for query, vertical in query_vertical_pairs:
                    progress.update(task, description=f"[cyan]{city}[/cyan] → {query}")
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
                        found_count += len(results)
                        await asyncio.sleep(0.1)  # Rate limiting
                    except Exception as e:
                        console.print(f"  [red]✗ Error: {query} in {city}: {e}[/red]")

                    search_count += 1
                    progress.update(task, advance=1)

        # Save raw results
        raw_file = self.raw_dir / f"places_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(raw_file, 'w') as f:
            json.dump(all_results, f, indent=2)

        console.print(f"\n  [green]✓ Found {len(all_results)} places[/green]")
        console.print(f"  [dim]  Saved to: {raw_file}[/dim]")
        return all_results

    def stage_2_group(self, places: list[dict]) -> list[BrandGroup]:
        """Group places by brand and filter by location count."""
        self._show_stage_header(2, "Brand Grouping", "Normalizing names and grouping by brand")

        with console.status("[cyan]Analyzing brands...[/cyan]"):
            grouper = BrandGrouper(min_locations=3, max_locations=10)
            groups = grouper.group(places)
            filtered = grouper.filter(groups)

        # Show summary table
        table = Table(box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Total places", str(len(places)))
        table.add_row("Unique brands", str(len(groups)))
        table.add_row("Brands with 3-10 locations", f"[bold]{len(filtered)}[/bold]")

        console.print(table)

        if filtered:
            console.print(f"\n  [dim]Top brands:[/dim]")
            for brand in sorted(filtered, key=lambda x: x.location_count, reverse=True)[:5]:
                console.print(f"    • {brand.normalized_name.title()} ({brand.location_count} locations)")

        return filtered

    async def stage_2b_verify_chain_size(self, brands: list[BrandGroup], searched_cities: list[str]) -> list[BrandGroup]:
        """Verify brands aren't large nationwide chains by checking additional cities."""
        self._show_stage_header("2b", "Chain Size Verification", "Filtering out large nationwide chains")

        if not brands:
            console.print("  [yellow]⚠ No brands to verify[/yellow]")
            return []

        # Test cities NOT in our main search to detect nationwide presence
        test_cities = [
            "Albuquerque, NM",
            "Tucson, AZ",
            "Omaha, NE",
            "Boise, ID",
            "Richmond, VA",
            "Knoxville, TN",
            "Des Moines, IA",
            "Spokane, WA",
        ]
        # Remove any test cities that were in our search
        test_cities = [c for c in test_cities if c not in searched_cities][:5]

        if not test_cities:
            console.print("  [yellow]⚠ No test cities available, skipping verification[/yellow]")
            return brands

        searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        verified_brands = []
        large_chains_found = 0

        console.print(f"  [dim]• Testing {len(brands)} brands in {len(test_cities)} additional cities[/dim]")
        console.print(f"  [dim]• Brands found in 3+ test cities are likely large chains[/dim]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Verifying...", total=len(brands))

            for brand in brands:
                brand_name = brand.normalized_name.title()
                progress.update(task, description=f"[cyan]Checking[/cyan] {brand_name}")

                # Search for this brand in test cities
                found_in_cities = 0
                for test_city in test_cities:
                    try:
                        results = await searcher.search(brand_name, test_city)
                        # Check if any result matches this brand
                        for r in results:
                            if brand.normalized_name.lower() in r.name.lower():
                                found_in_cities += 1
                                break
                        await asyncio.sleep(0.1)
                    except Exception:
                        pass

                # If found in 3+ additional cities, likely a large chain
                if found_in_cities >= 3:
                    brand.is_large_chain = True
                    brand.estimated_nationwide = brand.location_count + (found_in_cities * 10)  # Rough estimate
                    large_chains_found += 1
                    progress.update(task, description=f"[red]✗ Large chain[/red] {brand_name} (found in {found_in_cities} test cities)")
                else:
                    verified_brands.append(brand)
                    progress.update(task, description=f"[green]✓ Verified[/green] {brand_name}")

                progress.advance(task)

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Verified (true regional chains)", f"[bold green]{len(verified_brands)}[/bold green]")
        table.add_row("Excluded (large nationwide chains)", f"[bold red]{large_chains_found}[/bold red]")
        console.print(table)

        return verified_brands

    async def stage_3_ecommerce(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Check each brand for e-commerce presence."""
        self._show_stage_header(3, "E-commerce Detection", "Checking websites for online store presence")

        if not brands:
            console.print("  [yellow]⚠ No brands to check[/yellow]")
            return []

        checker = EcommerceChecker(api_key=settings.firecrawl_api_key)
        ecommerce_brands = []
        skipped = 0

        console.print(f"  [dim]• Checking {len(brands)} brand websites[/dim]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Checking...", total=len(brands))

            for brand in brands:
                if not brand.website:
                    progress.update(task, description=f"[yellow]Skipped[/yellow] {brand.normalized_name.title()} (no website)")
                    skipped += 1
                    progress.advance(task)
                    continue

                progress.update(task, description=f"[cyan]Checking[/cyan] {brand.normalized_name.title()}")

                try:
                    result = await checker.check(brand.website)
                    if result.has_ecommerce:
                        ecommerce_brands.append(brand)
                        progress.update(task, description=f"[green]✓ E-commerce[/green] {brand.normalized_name.title()}")
                    else:
                        progress.update(task, description=f"[dim]✗ No e-commerce[/dim] {brand.normalized_name.title()}")
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    console.print(f"  [red]✗ Error checking {brand.website}: {e}[/red]")

                progress.advance(task)

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("With e-commerce", f"[bold green]{len(ecommerce_brands)}[/bold green]")
        table.add_row("Without e-commerce", str(len(brands) - len(ecommerce_brands) - skipped))
        table.add_row("Skipped (no website)", str(skipped))
        console.print(table)

        return ecommerce_brands

    async def stage_4_linkedin(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich brands with LinkedIn data."""
        self._show_stage_header(4, "LinkedIn Enrichment", "Finding company pages and executive contacts")

        if not brands:
            console.print("  [yellow]⚠ No brands to enrich[/yellow]")
            return []

        enricher = LinkedInEnricher(api_key=settings.firecrawl_api_key)
        enriched = []

        console.print(f"  [dim]• Enriching {len(brands)} qualified leads[/dim]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Enriching...", total=len(brands))

            for brand in brands:
                brand_name = brand.normalized_name.title()
                progress.update(task, description=f"[cyan]Enriching[/cyan] {brand_name}")

                try:
                    result = await enricher.enrich(brand.normalized_name, brand.website or "")

                    contacts_found = len(result.contacts)
                    linkedin_found = "✓" if result.linkedin_company_url else "✗"

                    enriched.append({
                        "brand_name": brand_name,
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

                    progress.update(task, description=f"[green]✓[/green] {brand_name} [dim](LinkedIn: {linkedin_found}, Contacts: {contacts_found})[/dim]")
                    await asyncio.sleep(1.0)  # Rate limiting
                except Exception as e:
                    console.print(f"  [red]✗ Error enriching {brand_name}: {e}[/red]")

                progress.advance(task)

        console.print(f"\n  [green]✓ Enriched {len(enriched)} leads[/green]")
        return enriched

    def stage_5_export(self, data: list[dict]) -> str:
        """Export to CSV."""
        self._show_stage_header(5, "Export", "Saving leads to CSV")

        if not data:
            console.print("  [yellow]⚠ No data to export[/yellow]")
            output_file = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}_empty.csv"
            pd.DataFrame().to_csv(output_file, index=False)
            return str(output_file)

        with console.status("[cyan]Writing CSV...[/cyan]"):
            df = pd.DataFrame(data)
            output_file = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(output_file, index=False)

        # Final summary
        console.print(f"  [green]✓ Exported {len(data)} leads[/green]")
        console.print(f"  [dim]  File: {output_file}[/dim]")

        # Show preview
        if data:
            console.print(f"\n  [bold]Preview (first 3 leads):[/bold]")
            table = Table(box=box.SIMPLE, show_lines=True)
            table.add_column("Brand", style="cyan")
            table.add_column("Locations", justify="center")
            table.add_column("Website", style="dim")
            table.add_column("Contacts", justify="center")

            for lead in data[:3]:
                contacts = sum(1 for i in range(1, 5) if lead.get(f"contact_{i}_name"))
                table.add_row(
                    lead["brand_name"],
                    str(lead["location_count"]),
                    lead["website"][:40] + "..." if lead["website"] and len(lead["website"]) > 40 else lead.get("website", ""),
                    str(contacts),
                )

            console.print(table)

        return str(output_file)

    async def run(
        self,
        verticals: list[str] = ["health_wellness", "sporting_goods", "apparel"],
        countries: list[str] = ["us", "canada"]
    ) -> str:
        """Run the full pipeline."""
        start_time = datetime.now()

        console.print()
        console.print(Panel(
            "[bold]Pipeline Starting[/bold]\n\n"
            f"Verticals: {', '.join(verticals)}\n"
            f"Countries: {', '.join(countries)}",
            title="[bold blue]🚀 Lead Generator[/bold blue]",
            border_style="blue",
        ))

        # Stage 1: Search
        places = await self.stage_1_search(verticals, countries)

        # Get list of cities we searched (for chain verification)
        searched_cities = []
        for country in countries:
            searched_cities.extend(settings.cities.get(country, []))

        # Stage 2: Group and filter
        brands = self.stage_2_group(places)

        # Stage 2b: Verify chain sizes (filter out large nationwide chains)
        verified_brands = await self.stage_2b_verify_chain_size(brands, searched_cities)

        # Stage 3: E-commerce check
        ecommerce_brands = await self.stage_3_ecommerce(verified_brands)

        # Stage 4: LinkedIn enrichment
        enriched = await self.stage_4_linkedin(ecommerce_brands)

        # Stage 5: Export
        output_file = self.stage_5_export(enriched)

        # Final summary
        elapsed = datetime.now() - start_time
        console.print()
        console.print(Panel(
            f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
            f"Duration: {elapsed.seconds // 60}m {elapsed.seconds % 60}s\n"
            f"Leads found: {len(enriched)}\n"
            f"Output: {output_file}",
            title="[bold green]Summary[/bold green]",
            border_style="green",
        ))

        return output_file
