# src/pipeline.py
import asyncio
import json
import pandas as pd
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
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
from src.apollo_enrich import ApolloEnricher
from src.discovery import Discovery
from src.lead_scorer import LeadScorer

console = Console()


@dataclass
class Checkpoint:
    """Stores pipeline state for resume capability."""
    stage: int  # Last completed stage (0=none, 1=search, 2=group, 2.5=verify, 3=ecommerce, 4=linkedin)
    verticals: list[str]
    countries: list[str]
    searched_cities: list[str] = field(default_factory=list)
    places: list[dict] = field(default_factory=list)
    brands: list[dict] = field(default_factory=list)  # Serialized BrandGroup
    verified_brands: list[dict] = field(default_factory=list)
    ecommerce_brands: list[dict] = field(default_factory=list)
    enriched: list[dict] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        return cls(**data)


class Pipeline:
    CHECKPOINT_DIR = "checkpoints"

    def __init__(self):
        self.data_dir = Path(__file__).parent.parent / "data"
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.output_dir = self.data_dir / "output"
        self.checkpoint_dir = self.data_dir / self.CHECKPOINT_DIR
        self._current_checkpoint_path: Optional[Path] = None

        # Ensure directories exist
        for d in [self.raw_dir, self.processed_dir, self.output_dir, self.checkpoint_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def list_checkpoints(self) -> list[dict]:
        """List all available checkpoints with summary info."""
        checkpoints = []
        stage_names = {
            1: "Search",
            2: "Grouping",
            2.5: "Verification",
            3: "E-commerce",
            4: "Enrichment",
            5: "Scoring",
            6: "Export",
        }

        for cp_file in sorted(self.checkpoint_dir.glob("checkpoint_*.json"), reverse=True):
            try:
                with open(cp_file, 'r') as f:
                    data = json.load(f)
                checkpoint = Checkpoint.from_dict(data)
                checkpoints.append({
                    "filename": cp_file.name,
                    "path": cp_file,
                    "stage": checkpoint.stage,
                    "stage_name": stage_names.get(checkpoint.stage, f"Stage {checkpoint.stage}"),
                    "verticals": checkpoint.verticals,
                    "countries": checkpoint.countries,
                    "timestamp": checkpoint.timestamp,
                    "places_count": len(checkpoint.places),
                    "brands_count": len(checkpoint.brands),
                    "verified_count": len(checkpoint.verified_brands),
                    "ecommerce_count": len(checkpoint.ecommerce_brands),
                })
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return checkpoints

    def has_checkpoints(self) -> bool:
        """Check if any checkpoint files exist."""
        return len(list(self.checkpoint_dir.glob("checkpoint_*.json"))) > 0

    def load_checkpoint(self, checkpoint_path: Optional[Path] = None) -> Optional[Checkpoint]:
        """Load checkpoint from a specific file or the most recent one."""
        if checkpoint_path:
            path = checkpoint_path
        else:
            # Load most recent checkpoint
            checkpoints = list(self.checkpoint_dir.glob("checkpoint_*.json"))
            if not checkpoints:
                return None
            path = max(checkpoints, key=lambda p: p.stat().st_mtime)

        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self._current_checkpoint_path = path
            return Checkpoint.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            console.print(f"[yellow]⚠ Could not load checkpoint: {e}[/yellow]")
            return None

    def _save_checkpoint(self, checkpoint: Checkpoint):
        """Save checkpoint to file."""
        checkpoint.timestamp = datetime.now().isoformat()

        # Use existing checkpoint path or create new one
        if self._current_checkpoint_path:
            path = self._current_checkpoint_path
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = self.checkpoint_dir / f"checkpoint_{timestamp}.json"
            self._current_checkpoint_path = path

        with open(path, 'w') as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

    def clear_checkpoint(self, path: Optional[Path] = None):
        """Remove checkpoint file after successful completion."""
        if path:
            if path.exists():
                path.unlink()
        elif self._current_checkpoint_path and self._current_checkpoint_path.exists():
            self._current_checkpoint_path.unlink()
            self._current_checkpoint_path = None

    def delete_checkpoint(self, checkpoint_path: Path):
        """Delete a specific checkpoint."""
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    def _serialize_brand(self, brand: BrandGroup) -> dict:
        """Serialize a BrandGroup to dict for checkpoint."""
        return {
            "normalized_name": brand.normalized_name,
            "original_names": brand.original_names,
            "location_count": brand.location_count,
            "locations": brand.locations,
            "website": brand.website,
            "cities": brand.cities,
            "estimated_nationwide": brand.estimated_nationwide,
            "is_large_chain": brand.is_large_chain,
            "marketplaces": brand.marketplaces,
            "marketplace_links": brand.marketplace_links,
            "priority": brand.priority,
            "ecommerce_platform": brand.ecommerce_platform,
        }

    def _deserialize_brand(self, data: dict) -> BrandGroup:
        """Deserialize a dict to BrandGroup."""
        return BrandGroup(
            normalized_name=data["normalized_name"],
            original_names=data.get("original_names", []),
            location_count=data.get("location_count", 0),
            locations=data.get("locations", []),
            website=data.get("website"),
            cities=data.get("cities", []),
            estimated_nationwide=data.get("estimated_nationwide"),
            is_large_chain=data.get("is_large_chain", False),
            marketplaces=data.get("marketplaces", []),
            marketplace_links=data.get("marketplace_links", {}),
            priority=data.get("priority", "medium"),
            ecommerce_platform=data.get("ecommerce_platform"),
        )

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
        """Search Google Places for businesses (parallel)."""
        self._show_stage_header(1, "Google Places Search", "Finding retail businesses across cities")

        searcher = PlacesSearcher(api_key=settings.google_places_api_key)
        concurrency = settings.search_concurrency
        semaphore = asyncio.Semaphore(concurrency)

        cities = []
        for country in countries:
            cities.extend(settings.cities.get(country, []))

        # Build all search tasks: (city, query, vertical)
        search_tasks = []
        for vertical in verticals:
            for query in settings.search_queries.get(vertical, []):
                for city in cities:
                    search_tasks.append((city, query, vertical))

        total_searches = len(search_tasks)
        console.print(f"  [dim]• {len(cities)} cities × {len(set((q, v) for _, q, v in search_tasks))} queries = {total_searches} searches ({concurrency} parallel)[/dim]")
        console.print()

        async def do_search(city: str, query: str, vertical: str, progress, task) -> list[dict]:
            """Execute a single search with semaphore for rate limiting."""
            async with semaphore:
                try:
                    results = await searcher.search(query, city, vertical=vertical)
                    progress.advance(task)
                    return [
                        {
                            "name": r.name,
                            "address": r.address,
                            "website": r.website,
                            "place_id": r.place_id,
                            "city": r.city,
                            "vertical": r.vertical
                        }
                        for r in results
                    ]
                except Exception as e:
                    console.print(f"  [red]✗ Error: {query} in {city}: {e}[/red]")
                    progress.advance(task)
                    return []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Searching {total_searches} locations...", total=total_searches)

            # Run all searches in parallel (limited by semaphore)
            coros = [do_search(city, query, vertical, progress, task) for city, query, vertical in search_tasks]
            results_lists = await asyncio.gather(*coros)

        # Flatten results
        all_results = [place for result_list in results_lists for place in result_list]

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

            # Apply blocklist filter
            filtered = grouper.filter_with_blocklist(groups)

            # Apply LLM disambiguation if enabled
            if settings.llm.enabled:
                console.print("  [dim]• Running LLM disambiguation...[/dim]")
                filtered = grouper.process_with_llm(filtered)

        # Show summary table
        table = Table(box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Total places", str(len(places)))
        table.add_row("Unique brands", str(len(groups)))
        table.add_row("After blocklist filter", str(len(filtered)))
        table.add_row("Brands with 3-10 locations", f"[bold]{len(filtered)}[/bold]")

        console.print(table)

        if filtered:
            console.print(f"\n  [dim]Top brands:[/dim]")
            for brand in sorted(filtered, key=lambda x: x.location_count, reverse=True)[:5]:
                console.print(f"    • {brand.normalized_name.title()} ({brand.location_count} locations)")

        return filtered

    def stage_2b_verify_chain_size(self, brands: list[BrandGroup], searched_cities: list[str]) -> list[BrandGroup]:
        """Filter out large nationwide chains using heuristics (no API calls)."""
        self._show_stage_header("2b", "Chain Size Verification", "Filtering out large nationwide chains")

        if not brands:
            console.print("  [yellow]⚠ No brands to verify[/yellow]")
            return []

        max_cities = settings.chain_filter_max_cities
        known_chains = settings.known_large_chains
        total_searched = len(searched_cities)
        verified_brands = []
        large_chains_found = 0
        known_chains_found = 0

        console.print(f"  [dim]• Analyzing {len(brands)} brands[/dim]")
        console.print(f"  [dim]• Filtering brands found in {max_cities}+ cities (of {total_searched} searched)[/dim]")
        console.print(f"  [dim]• Also filtering {len(known_chains)} known large chains (from config)[/dim]")
        console.print()

        for brand in brands:
            brand_name = brand.normalized_name.title()
            num_cities = len(brand.cities)

            # Check 1: Known large chain list (from config)
            if brand.normalized_name.lower() in known_chains:
                brand.is_large_chain = True
                brand.estimated_nationwide = 500  # Rough estimate for known chains
                known_chains_found += 1
                console.print(f"  [red]✗ Known chain:[/red] {brand_name}")
                continue

            # Check 2: Found in too many cities (likely national)
            if num_cities >= max_cities:
                brand.is_large_chain = True
                # Estimate: if found in 8 of 50 cities, extrapolate to ~80+ nationwide
                brand.estimated_nationwide = int(brand.location_count * (50 / num_cities) * 1.5)
                large_chains_found += 1
                console.print(f"  [red]✗ Large chain:[/red] {brand_name} (found in {num_cities} cities)")
                continue

            # Passed both checks
            verified_brands.append(brand)
            console.print(f"  [green]✓ Regional:[/green] {brand_name} ({num_cities} cities, {brand.location_count} locations)")

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Verified (true regional chains)", f"[bold green]{len(verified_brands)}[/bold green]")
        table.add_row("Known large chains filtered", f"[bold red]{known_chains_found}[/bold red]")
        table.add_row("Multi-city chains filtered", f"[bold red]{large_chains_found}[/bold red]")
        console.print(table)

        return verified_brands

    async def stage_3_ecommerce(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Check each brand for e-commerce presence (parallel)."""
        self._show_stage_header(3, "E-commerce Detection", "Checking websites for online store presence")

        if not brands:
            console.print("  [yellow]⚠ No brands to check[/yellow]")
            return []

        concurrency = settings.ecommerce_concurrency
        checker = EcommerceChecker(
            api_key=settings.firecrawl_api_key,
            pages_to_check=settings.ecommerce_pages_to_check
        )
        semaphore = asyncio.Semaphore(concurrency)
        results: dict[str, tuple[BrandGroup, bool]] = {}  # brand_name -> (brand, has_ecommerce)
        skipped = 0

        # Filter brands with websites
        brands_with_website = [b for b in brands if b.website]
        skipped = len(brands) - len(brands_with_website)

        console.print(f"  [dim]• Checking {len(brands_with_website)} brand websites ({concurrency} parallel)[/dim]")
        if skipped > 0:
            console.print(f"  [dim]• Skipping {skipped} brands without websites[/dim]")
        console.print()

        async def check_brand(brand: BrandGroup, progress, task) -> tuple[BrandGroup, bool]:
            """Check a single brand with semaphore for rate limiting."""
            async with semaphore:
                try:
                    result = await checker.check(brand.website)
                    # Attach marketplace and platform data to brand
                    brand.marketplaces = result.marketplaces
                    brand.marketplace_links = result.marketplace_links
                    brand.priority = result.priority
                    brand.ecommerce_platform = result.platform  # Shopify, WooCommerce, etc.
                    progress.advance(task)
                    return (brand, result.has_ecommerce)
                except Exception as e:
                    console.print(f"  [red]✗ Error: {brand.normalized_name.title()}: {e}[/red]")
                    progress.advance(task)
                    return (brand, False)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Checking {len(brands_with_website)} websites...", total=len(brands_with_website))

            # Run all checks in parallel (limited by semaphore)
            tasks = [check_brand(brand, progress, task) for brand in brands_with_website]
            check_results = await asyncio.gather(*tasks)

        # Collect results
        ecommerce_brands = [brand for brand, has_ecom in check_results if has_ecom]
        no_ecommerce_count = len(brands_with_website) - len(ecommerce_brands)

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("With e-commerce", f"[bold green]{len(ecommerce_brands)}[/bold green]")
        table.add_row("Without e-commerce", str(no_ecommerce_count))
        table.add_row("Skipped (no website)", str(skipped))
        console.print(table)

        return ecommerce_brands

    def _categorize_contact(self, title: str) -> str:
        """Categorize a contact by their title."""
        title_lower = title.lower()
        if any(t in title_lower for t in ["ceo", "chief executive", "founder", "owner", "president"]):
            return "C-Suite"
        elif any(t in title_lower for t in ["coo", "chief operating", "cfo", "chief financial", "cto"]):
            return "C-Suite"
        elif any(t in title_lower for t in ["vp", "vice president", "director"]):
            return "Executive"
        elif any(t in title_lower for t in ["manager", "head of"]):
            return "Management"
        else:
            return "Other"

    async def stage_4_enrich(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich brands with contact data using configured provider."""
        provider = settings.enrichment.provider
        self._show_stage_header(4, f"Contact Enrichment ({provider.title()})", "Finding company pages and executive contacts")

        if not brands:
            console.print("  [yellow]⚠ No brands to enrich[/yellow]")
            return []

        # Select enricher based on config
        if provider == "apollo":
            if not settings.apollo_api_key:
                console.print("  [red]✗ APOLLO_API_KEY not set in .env[/red]")
                console.print("  [dim]  Get your key at: https://app.apollo.io/[/dim]")
                console.print("  [dim]  Or set enrichment.provider = \"linkedin\" in config/cities.json[/dim]")
                return []
            return await self._enrich_with_apollo(brands)
        else:
            return await self._enrich_with_linkedin(brands)

    async def _enrich_with_apollo(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich using Apollo.io API."""
        enricher = ApolloEnricher(api_key=settings.apollo_api_key)
        enriched = []
        max_contacts = settings.enrichment.max_contacts

        # Track statistics
        stats = {
            "companies_found": 0,
            "total_contacts": 0,
            "with_email": 0,
            "with_phone": 0,
        }

        console.print(f"  [dim]• Enriching {len(brands)} qualified leads via Apollo.io[/dim]")
        console.print(f"  [dim]• Looking for: CEO, COO, Founder, Owner, Operations Manager[/dim]")
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
                progress.update(task, description=f"[cyan]Searching[/cyan] {brand_name}")

                try:
                    result = await enricher.enrich(brand.normalized_name, brand.website or "", max_contacts)

                    if result:
                        # Track stats
                        if result.company.linkedin_url:
                            stats["companies_found"] += 1

                        row = {
                            "brand_name": brand_name,
                            "location_count": brand.location_count,
                            "website": brand.website,
                            "has_ecommerce": True,
                            "ecommerce_platform": brand.ecommerce_platform or "",
                            "marketplaces": ", ".join(brand.marketplaces),
                            "priority": brand.priority,
                            "cities": ", ".join(brand.cities[:5]),
                            "linkedin_company": result.company.linkedin_url or "",
                            "employee_count": result.company.employee_count or "",
                            "industry": result.company.industry or "",
                            "technology_names": result.company.technology_names,
                            "apollo_location_count": result.company.retail_location_count,
                        }

                        # Add contacts
                        for i in range(4):
                            if i < len(result.contacts):
                                contact = result.contacts[i]
                                row[f"contact_{i+1}_name"] = contact.name
                                row[f"contact_{i+1}_title"] = contact.title
                                row[f"contact_{i+1}_email"] = contact.email or ""
                                row[f"contact_{i+1}_phone"] = contact.phone or ""
                                row[f"contact_{i+1}_linkedin"] = contact.linkedin_url or ""
                                stats["total_contacts"] += 1
                                if contact.email:
                                    stats["with_email"] += 1
                                if contact.phone:
                                    stats["with_phone"] += 1
                            else:
                                row[f"contact_{i+1}_name"] = ""
                                row[f"contact_{i+1}_title"] = ""
                                row[f"contact_{i+1}_email"] = ""
                                row[f"contact_{i+1}_phone"] = ""
                                row[f"contact_{i+1}_linkedin"] = ""

                        enriched.append(row)

                        # Status message
                        contact_count = len(result.contacts)
                        if contact_count > 0:
                            progress.update(task, description=f"[green]✓[/green] {brand_name}: {contact_count} contacts found")
                        else:
                            progress.update(task, description=f"[yellow]○[/yellow] {brand_name}: No contacts found")

                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    error_msg = str(e)
                    if "credits" in error_msg.lower():
                        console.print(f"\n  [red]✗ Apollo credits exhausted. Stopping enrichment.[/red]")
                        console.print(f"  [dim]  Add credits at: https://app.apollo.io/settings/credits[/dim]")
                        break
                    console.print(f"  [red]✗ Error enriching {brand_name}: {e}[/red]")

                progress.advance(task)

        # Summary
        console.print()
        table = Table(title="Apollo Enrichment Results", box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Brands enriched", str(len(enriched)))
        table.add_row("LinkedIn company pages", str(stats["companies_found"]))
        table.add_row("─" * 25, "─" * 5)
        table.add_row("Total contacts", f"[bold]{stats['total_contacts']}[/bold]")
        table.add_row("  └ With email", f"[bold cyan]{stats['with_email']}[/bold cyan]")
        table.add_row("  └ With phone", str(stats["with_phone"]))
        console.print(table)

        return enriched

    async def _enrich_with_linkedin(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich using LinkedIn scraping (legacy fallback)."""
        enricher = LinkedInEnricher(api_key=settings.firecrawl_api_key)
        enriched = []

        stats = {
            "linkedin_pages_found": 0,
            "total_contacts": 0,
            "c_suite": 0,
            "executive": 0,
            "management": 0,
            "other": 0,
        }

        console.print(f"  [dim]• Enriching {len(brands)} qualified leads via LinkedIn scraping[/dim]")
        console.print(f"  [yellow]⚠ Warning: LinkedIn scraping produces lower quality results[/yellow]")
        console.print(f"  [dim]  Consider using Apollo.io for verified contacts[/dim]")
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
                progress.update(task, description=f"[cyan]Searching[/cyan] {brand_name}")

                try:
                    result = await enricher.enrich(brand.normalized_name, brand.website or "")

                    if result.linkedin_company_url:
                        stats["linkedin_pages_found"] += 1

                    contact_types = []
                    for contact in result.contacts:
                        category = self._categorize_contact(contact.title)
                        contact_types.append(category)
                        stats["total_contacts"] += 1
                        if category == "C-Suite":
                            stats["c_suite"] += 1
                        elif category == "Executive":
                            stats["executive"] += 1
                        elif category == "Management":
                            stats["management"] += 1
                        else:
                            stats["other"] += 1

                    enriched.append({
                        "brand_name": brand_name,
                        "location_count": brand.location_count,
                        "website": brand.website,
                        "has_ecommerce": True,
                        "ecommerce_platform": brand.ecommerce_platform or "",
                        "marketplaces": ", ".join(brand.marketplaces),
                        "priority": brand.priority,
                        "cities": ", ".join(brand.cities[:5]),
                        "linkedin_company": result.linkedin_company_url or "",
                        "employee_count": "",
                        "industry": "",
                        "contact_1_name": result.contacts[0].name if len(result.contacts) > 0 else "",
                        "contact_1_title": result.contacts[0].title if len(result.contacts) > 0 else "",
                        "contact_1_email": "",
                        "contact_1_phone": "",
                        "contact_1_linkedin": result.contacts[0].linkedin_url if len(result.contacts) > 0 else "",
                        "contact_2_name": result.contacts[1].name if len(result.contacts) > 1 else "",
                        "contact_2_title": result.contacts[1].title if len(result.contacts) > 1 else "",
                        "contact_2_email": "",
                        "contact_2_phone": "",
                        "contact_2_linkedin": result.contacts[1].linkedin_url if len(result.contacts) > 1 else "",
                        "contact_3_name": result.contacts[2].name if len(result.contacts) > 2 else "",
                        "contact_3_title": result.contacts[2].title if len(result.contacts) > 2 else "",
                        "contact_3_email": "",
                        "contact_3_phone": "",
                        "contact_3_linkedin": result.contacts[2].linkedin_url if len(result.contacts) > 2 else "",
                        "contact_4_name": result.contacts[3].name if len(result.contacts) > 3 else "",
                        "contact_4_title": result.contacts[3].title if len(result.contacts) > 3 else "",
                        "contact_4_email": "",
                        "contact_4_phone": "",
                        "contact_4_linkedin": result.contacts[3].linkedin_url if len(result.contacts) > 3 else "",
                    })

                    if contact_types:
                        progress.update(task, description=f"[green]✓[/green] {brand_name}: {len(result.contacts)} contacts")
                    else:
                        progress.update(task, description=f"[yellow]○[/yellow] {brand_name}: No data found")

                    await asyncio.sleep(1.0)
                except Exception as e:
                    console.print(f"  [red]✗ Error enriching {brand_name}: {e}[/red]")

                progress.advance(task)

        # Summary
        console.print()
        table = Table(title="LinkedIn Enrichment Results", box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Brands enriched", str(len(enriched)))
        table.add_row("LinkedIn pages found", str(stats["linkedin_pages_found"]))
        table.add_row("Total contacts", f"[bold]{stats['total_contacts']}[/bold]")
        console.print(table)

        return enriched

    def stage_5_score(self, enriched: list[dict]) -> list[dict]:
        """Score leads based on tech stack and other signals."""
        self._show_stage_header(5, "Lead Scoring", "Calculating priority scores based on tech stack")

        if not enriched:
            console.print("  [yellow]⚠ No leads to score[/yellow]")
            return []

        scorer = LeadScorer()

        with console.status("[cyan]Scoring leads...[/cyan]"):
            scored = scorer.score_leads(enriched)

        # Summary statistics
        lightspeed_count = sum(1 for lead in scored if lead.get("uses_lightspeed"))
        with_pos = sum(1 for lead in scored if lead.get("pos_platform"))
        with_marketplaces = sum(1 for lead in scored if lead.get("detected_marketplaces"))

        # Show summary
        table = Table(box=box.SIMPLE)
        table.add_column("Signal", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Uses Lightspeed", f"[bold green]{lightspeed_count}[/bold green]")
        table.add_row("Has POS platform data", str(with_pos))
        table.add_row("Has marketplace presence", str(with_marketplaces))
        console.print(table)

        # Show top scored leads
        if scored:
            console.print(f"\n  [bold]Top 5 leads by priority score:[/bold]")
            for lead in scored[:5]:
                score = lead["priority_score"]
                name = lead["brand_name"]
                pos = lead.get("pos_platform", "")
                ls_badge = "[green]LS[/green]" if lead.get("uses_lightspeed") else ""
                console.print(f"    {score:>3}  {name} {ls_badge} {pos}")

        return scored

    def stage_6_export(self, data: list[dict]) -> str:
        """Export to CSV."""
        self._show_stage_header(6, "Export", "Saving leads to CSV")

        if not data:
            console.print("  [yellow]⚠ No data to export[/yellow]")
            output_file = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}_empty.csv"
            pd.DataFrame().to_csv(output_file, index=False)
            return str(output_file)

        with console.status("[cyan]Writing CSV...[/cyan]"):
            df = pd.DataFrame(data)

            # Define column order (priority columns first)
            priority_cols = [
                "priority_score", "uses_lightspeed", "pos_platform",
                "brand_name", "location_count", "website",
                "detected_marketplaces", "tech_stack",
                "has_ecommerce", "ecommerce_platform", "marketplaces", "priority",
                "cities", "linkedin_company", "employee_count", "industry",
            ]

            # Contact columns
            contact_cols = []
            for i in range(1, 5):
                contact_cols.extend([
                    f"contact_{i}_name", f"contact_{i}_title",
                    f"contact_{i}_email", f"contact_{i}_phone", f"contact_{i}_linkedin"
                ])

            # Reorder columns (existing columns only)
            ordered_cols = [c for c in priority_cols + contact_cols if c in df.columns]
            remaining_cols = [c for c in df.columns if c not in ordered_cols]
            df = df[ordered_cols + remaining_cols]

            # Sort by priority_score descending
            if 'priority_score' in df.columns:
                df = df.sort_values(by='priority_score', ascending=False)

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
        countries: list[str] = ["us", "canada"],
        resume_checkpoint: Optional[Path] = None
    ) -> str:
        """Run the full pipeline, optionally resuming from a checkpoint."""
        start_time = datetime.now()

        # Initialize checkpoint or load existing
        checkpoint: Optional[Checkpoint] = None
        start_stage = 0

        if resume_checkpoint:
            checkpoint = self.load_checkpoint(resume_checkpoint)
            if checkpoint:
                start_stage = checkpoint.stage
                verticals = checkpoint.verticals
                countries = checkpoint.countries
                console.print()
                console.print(Panel(
                    f"[bold yellow]Resuming Pipeline[/bold yellow]\n\n"
                    f"Last completed: Stage {checkpoint.stage}\n"
                    f"Verticals: {', '.join(verticals)}\n"
                    f"Countries: {', '.join(countries)}\n"
                    f"Saved at: {checkpoint.timestamp}",
                    title="[bold yellow]⏯ Resuming[/bold yellow]",
                    border_style="yellow",
                ))
        else:
            # Fresh run - create new checkpoint
            checkpoint = Checkpoint(
                stage=0,
                verticals=verticals,
                countries=countries,
            )
            console.print()
            console.print(Panel(
                "[bold]Pipeline Starting[/bold]\n\n"
                f"Verticals: {', '.join(verticals)}\n"
                f"Countries: {', '.join(countries)}",
                title="[bold blue]🚀 Lead Generator[/bold blue]",
                border_style="blue",
            ))

        # Initialize data from checkpoint or empty
        places = checkpoint.places if checkpoint and start_stage >= 1 else []
        searched_cities = checkpoint.searched_cities if checkpoint else []
        brands = [self._deserialize_brand(b) for b in checkpoint.brands] if checkpoint and start_stage >= 2 else []
        verified_brands = [self._deserialize_brand(b) for b in checkpoint.verified_brands] if checkpoint and start_stage >= 2.5 else []
        ecommerce_brands = [self._deserialize_brand(b) for b in checkpoint.ecommerce_brands] if checkpoint and start_stage >= 3 else []
        enriched = checkpoint.enriched if checkpoint and start_stage >= 4 else []

        # Stage 1: Discovery (enhanced multi-source search)
        if start_stage < 1:
            discovery = Discovery(settings)
            places = await discovery.run(verticals, countries)
            searched_cities = []
            for country in countries:
                searched_cities.extend(settings.cities.get(country, []))
            checkpoint.places = places
            checkpoint.searched_cities = searched_cities
            checkpoint.stage = 1
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 1 complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 1 (Search) - loaded {len(places)} places from checkpoint[/dim]")
            if not searched_cities:
                for country in countries:
                    searched_cities.extend(settings.cities.get(country, []))

        # Stage 2: Group and filter
        if start_stage < 2:
            brands = self.stage_2_group(places)
            checkpoint.brands = [self._serialize_brand(b) for b in brands]
            checkpoint.stage = 2
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 2 complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 2 (Grouping) - loaded {len(brands)} brands from checkpoint[/dim]")

        # Stage 2b: Verify chain sizes (filter out large nationwide chains)
        if start_stage < 2.5:
            verified_brands = self.stage_2b_verify_chain_size(brands, searched_cities)
            checkpoint.verified_brands = [self._serialize_brand(b) for b in verified_brands]
            checkpoint.stage = 2.5
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 2b complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 2b (Verification) - loaded {len(verified_brands)} verified brands from checkpoint[/dim]")

        # Stage 3: E-commerce check
        if start_stage < 3:
            ecommerce_brands = await self.stage_3_ecommerce(verified_brands)
            checkpoint.ecommerce_brands = [self._serialize_brand(b) for b in ecommerce_brands]
            checkpoint.stage = 3
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 3 complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 3 (E-commerce) - loaded {len(ecommerce_brands)} e-commerce brands from checkpoint[/dim]")

        # Stage 4: Contact enrichment (Apollo or LinkedIn)
        if start_stage < 4:
            enriched = await self.stage_4_enrich(ecommerce_brands)
            checkpoint.enriched = enriched
            checkpoint.stage = 4
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 4 complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 4 (LinkedIn) - loaded {len(enriched)} enriched leads from checkpoint[/dim]")

        # Stage 5: Score leads
        scored = self.stage_5_score(enriched)

        # Stage 6: Export
        output_file = self.stage_6_export(scored)

        # Clear checkpoint on successful completion
        self.clear_checkpoint()

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
