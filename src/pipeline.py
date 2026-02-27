# src/pipeline.py
import asyncio
import json
import random
import re
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

import httpx
from urllib.parse import urlparse

from src.config import settings
from src.serpapi_search import SerpApiSearcher, PlaceResult
from src.brand_grouper import BrandGrouper, BrandGroup
from src.ecommerce_check import EcommerceChecker
from src.linkedin_enrich import LinkedInEnricher, LinkedInCompanyData
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
    healthy_brands: list[dict] = field(default_factory=list)
    ecommerce_brands: list[dict] = field(default_factory=list)
    enriched: list[dict] = field(default_factory=list)
    timestamp: str = ""
    saved_settings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        # Handle checkpoints saved before saved_settings was added
        if "saved_settings" not in data:
            data["saved_settings"] = {}
        return cls(**data)


class Pipeline:
    CHECKPOINT_DIR = "checkpoints"

    # Known domain parking / parked domain hosts
    PARKING_DOMAINS = {
        "godaddy.com", "sedoparking.com", "hugedomains.com",
        "afternic.com", "dan.com", "parkingcrew.net",
        "bodis.com", "above.com", "undeveloped.com",
    }

    # Non-commerce domains: social profiles, link aggregators, store locators, etc.
    # These are never real company e-commerce websites.
    NON_COMMERCE_DOMAINS = {
        "linktr.ee", "linktree.com",
        "instagram.com", "facebook.com", "twitter.com", "x.com",
        "tiktok.com", "youtube.com", "pinterest.com",
        "yelp.com", "tripadvisor.com",
        "boards.com", "carrd.co", "bio.link", "beacons.ai",
        "google.com", "goo.gl", "bit.ly",
    }

    # URL path prefixes that indicate store locator pages (not actual company sites)
    STORE_LOCATOR_PREFIXES = {
        "locations.", "stores.", "store-locator.",
    }

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
            2.6: "Health Check",
            3: "E-commerce",
            4: "Enrichment",
            4.5: "Quality Gate",
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

    @staticmethod
    def _snapshot_settings() -> dict:
        """Capture current settings for checkpoint storage."""
        return {
            "search_concurrency": settings.search_concurrency,
            "ecommerce_concurrency": settings.ecommerce_concurrency,
            "health_check_concurrency": settings.health_check_concurrency,
            "enrichment_enabled": settings.enrichment.enabled,
            "enrichment_provider": settings.enrichment.provider,
            "enrichment_max_contacts": settings.enrichment.max_contacts,
            "quality_gate_max_locations": settings.quality_gate_max_locations,
            "quality_gate_max_employees": settings.quality_gate_max_employees,
            "ecommerce_pages_to_check": settings.ecommerce_pages_to_check,
            "search_mode": settings.search_mode,
        }

    @staticmethod
    def apply_settings(saved: dict):
        """Apply saved settings from a checkpoint to the current settings object."""
        if not saved:
            return
        if "search_concurrency" in saved:
            settings.search_concurrency = saved["search_concurrency"]
        if "ecommerce_concurrency" in saved:
            settings.ecommerce_concurrency = saved["ecommerce_concurrency"]
        if "health_check_concurrency" in saved:
            settings.health_check_concurrency = saved["health_check_concurrency"]
        if "enrichment_enabled" in saved:
            settings.enrichment.enabled = saved["enrichment_enabled"]
        if "enrichment_provider" in saved:
            settings.enrichment.provider = saved["enrichment_provider"]
        if "enrichment_max_contacts" in saved:
            settings.enrichment.max_contacts = saved["enrichment_max_contacts"]
        if "quality_gate_max_locations" in saved:
            settings.quality_gate_max_locations = saved["quality_gate_max_locations"]
        if "quality_gate_max_employees" in saved:
            settings.quality_gate_max_employees = saved["quality_gate_max_employees"]
        if "ecommerce_pages_to_check" in saved:
            settings.ecommerce_pages_to_check = saved["ecommerce_pages_to_check"]
        if "search_mode" in saved:
            settings.search_mode = saved["search_mode"]

    def _save_checkpoint(self, checkpoint: Checkpoint):
        """Save checkpoint to file."""
        checkpoint.timestamp = datetime.now().isoformat()
        checkpoint.saved_settings = self._snapshot_settings()

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
            "qualified": brand.qualified,
            "disqualify_reason": brand.disqualify_reason,
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
            qualified=data.get("qualified", True),
            disqualify_reason=data.get("disqualify_reason", ""),
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
        """Search for businesses via SerpAPI (parallel)."""
        self._show_stage_header(1, "Business Search (SerpAPI)", "Finding retail businesses across cities")

        searcher = SerpApiSearcher(api_key=settings.serpapi_api_key)
        concurrency = settings.search_concurrency
        semaphore = asyncio.Semaphore(concurrency)

        # Build city list with country tag
        city_country = []  # [(city, country), ...]
        for country in countries:
            for city in settings.cities.get(country, []):
                city_country.append((city, country))

        # Build all search tasks: (city, query, vertical, country)
        search_tasks = []
        for vertical in verticals:
            for query in settings.search_queries.get(vertical, []):
                for city, country in city_country:
                    search_tasks.append((city, query, vertical, country))

        total_searches = len(search_tasks)
        console.print(f"  [dim]• {len(city_country)} cities × {len(set((q, v) for _, q, v, _ in search_tasks))} queries = {total_searches} searches ({concurrency} parallel)[/dim]")
        console.print()

        # Country → expected address suffix for validation
        country_address_markers = {
            "us": ["USA", "United States"],
            "canada": ["Canada"],
        }

        async def do_search(city: str, query: str, vertical: str, country: str, progress, task) -> list[dict]:
            """Execute a single search with semaphore for rate limiting."""
            async with semaphore:
                try:
                    results = await searcher.search(query, city, vertical=vertical)
                    progress.advance(task)
                    markers = country_address_markers.get(country, [])
                    places = []
                    for r in results:
                        # Validate address matches search country
                        if markers and r.address:
                            if not any(marker in r.address for marker in markers):
                                continue  # Skip cross-country results
                        places.append({
                            "name": r.name,
                            "address": r.address,
                            "website": r.website,
                            "place_id": r.place_id,
                            "city": r.city,
                            "vertical": r.vertical
                        })
                    return places
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
            coros = [do_search(city, query, vertical, country, progress, task) for city, query, vertical, country in search_tasks]
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

    def _deduplicate_places(self, places: list[dict]) -> list[dict]:
        """Remove duplicate places (same place_id found from different city searches)."""
        seen_ids = {}
        deduped = []
        for place in places:
            pid = place.get("place_id", "")
            if not pid or pid not in seen_ids:
                if pid:
                    seen_ids[pid] = True
                deduped.append(place)
        removed = len(places) - len(deduped)
        if removed > 0:
            console.print(f"  [dim]• Removed {removed} duplicate places (same place_id from different city searches)[/dim]")
        return deduped

    def stage_2_group(self, places: list[dict], searched_cities: list[str]) -> list[BrandGroup]:
        """Group places by brand and filter by location count."""
        self._show_stage_header(2, "Brand Grouping", "Normalizing names and grouping by brand")

        # Deduplicate places by place_id before grouping
        places = self._deduplicate_places(places)

        # Dynamic min_locations: with few cities, lower the bar
        # 50+ cities → min 3, 20-49 → min 2, <20 → min 1
        num_cities = len(searched_cities)
        if num_cities >= 50:
            min_locations = 3
        elif num_cities >= 20:
            min_locations = 2
        else:
            min_locations = 1

        console.print(f"  [dim]• {num_cities} cities searched → min_locations={min_locations}[/dim]")

        with console.status("[cyan]Analyzing brands...[/cyan]"):
            grouper = BrandGrouper(min_locations=min_locations, max_locations=10, resolve_redirects=True)
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
        table.add_row(f"Brands with {min_locations}-10 locations", f"[bold]{len(filtered)}[/bold]")

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
                # Estimate nationwide locations based on how many cities were searched
                brand.estimated_nationwide = int(brand.location_count * (max(total_searched, 1) / num_cities) * 1.5)
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

    async def stage_2c_website_health(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Filter out brands with dead or parked websites."""
        self._show_stage_header("2c", "Website Health Check", "Filtering dead and parked websites")

        if not brands:
            console.print("  [yellow]⚠ No brands to check[/yellow]")
            return []

        brands_with_site = [b for b in brands if b.website]
        brands_without_site = [b for b in brands if not b.website]

        # Pre-filter: remove non-commerce websites (social profiles, link aggregators, store locators)
        filtered_brands = []
        non_commerce_count = 0
        for brand in brands_with_site:
            url = brand.website or ""
            parsed = urlparse(url if url.startswith(("http://", "https://")) else f"https://{url}")
            host = (parsed.netloc or "").lower().lstrip("www.")

            # Check non-commerce domains
            is_non_commerce = any(host == d or host.endswith("." + d) for d in self.NON_COMMERCE_DOMAINS)

            # Check store locator subdomains
            if not is_non_commerce:
                is_non_commerce = any(host.startswith(prefix) for prefix in self.STORE_LOCATOR_PREFIXES)

            if is_non_commerce:
                non_commerce_count += 1
                console.print(f"  [red]✗ Non-commerce URL:[/red] {brand.normalized_name.title()} — {url[:60]}")
            else:
                filtered_brands.append(brand)

        brands_with_site = filtered_brands
        concurrency = settings.health_check_concurrency
        semaphore = asyncio.Semaphore(concurrency)

        console.print(f"  [dim]• Checking {len(brands_with_site)} websites ({concurrency} parallel)[/dim]")
        if non_commerce_count:
            console.print(f"  [dim]• Filtered {non_commerce_count} non-commerce URLs (social/link aggregator/store locator)[/dim]")
        if brands_without_site:
            console.print(f"  [dim]• Passing through {len(brands_without_site)} brands without websites[/dim]")
        console.print()

        async def check_health(brand: BrandGroup) -> tuple[BrandGroup, bool, str]:
            """Check if a brand's website is alive. Returns (brand, is_healthy, reason)."""
            async with semaphore:
                url = brand.website
                url = url.strip()
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url}"

                try:
                    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                        response = await client.head(url)

                        # Check for dead status codes
                        if response.status_code in (404, 410, 500, 502, 503):
                            return (brand, False, f"HTTP {response.status_code}")

                        # Check for parked domain redirect
                        final_host = response.url.host or ""
                        for parking_domain in Pipeline.PARKING_DOMAINS:
                            if parking_domain in final_host:
                                return (brand, False, f"Parked domain ({parking_domain})")

                        return (brand, True, "OK")

                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.InvalidURL):
                    return (brand, False, "Connection failed")
                except httpx.TimeoutException:
                    return (brand, False, "Timeout")
                except Exception:
                    # On unexpected errors, let the brand through
                    return (brand, True, "Check failed (passing through)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Checking {len(brands_with_site)} websites...", total=len(brands_with_site))

            async def check_and_advance(brand):
                result = await check_health(brand)
                progress.advance(task)
                return result

            results = await asyncio.gather(*[check_and_advance(b) for b in brands_with_site])

        healthy = []
        dead_count = 0
        for brand, is_healthy, reason in results:
            if is_healthy:
                healthy.append(brand)
            else:
                dead_count += 1
                console.print(f"  [red]✗ Dead:[/red] {brand.normalized_name.title()} — {reason}")

        # Add back brands without websites
        healthy.extend(brands_without_site)

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Healthy websites", f"[bold green]{len(healthy) - len(brands_without_site)}[/bold green]")
        table.add_row("Dead/parked websites", f"[bold red]{dead_count}[/bold red]")
        table.add_row("No website (pass-through)", str(len(brands_without_site)))
        console.print(table)

        return healthy

    async def stage_3_ecommerce(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Check each brand for e-commerce presence (parallel)."""
        self._show_stage_header(3, "E-commerce Detection", "Checking websites for online store presence")

        if not brands:
            console.print("  [yellow]⚠ No brands to check[/yellow]")
            return []

        import random

        concurrency = settings.ecommerce_concurrency
        checker = EcommerceChecker(
            pages_to_check=settings.ecommerce_pages_to_check,
            playwright_fallback_enabled=settings.ecommerce_playwright_fallback_enabled,
            playwright_timeout=settings.ecommerce_playwright_fallback_timeout,
        )
        semaphore = asyncio.Semaphore(concurrency)
        # Rate limiter: stagger request starts to avoid CDN-level 429s
        request_interval = 1.0  # seconds between request starts
        results: dict[str, tuple[BrandGroup, bool]] = {}  # brand_name -> (brand, has_ecommerce)
        skipped = 0

        # Filter brands with websites
        brands_with_website = [b for b in brands if b.website]
        skipped = len(brands) - len(brands_with_website)

        console.print(f"  [dim]• Checking {len(brands_with_website)} brand websites ({concurrency} parallel)[/dim]")
        if skipped > 0:
            console.print(f"  [dim]• Skipping {skipped} brands without websites[/dim]")
        console.print()

        crawl_failure_count = 0
        fail_reasons: dict[str, int] = {}

        # result states: "ecommerce", "no_ecommerce", "crawl_failed"
        async def check_brand(brand: BrandGroup, idx: int, progress, task) -> tuple[BrandGroup, str]:
            """Check a single brand with semaphore + staggered start."""
            nonlocal crawl_failure_count
            # Stagger request starts to avoid CDN-level rate limits
            await asyncio.sleep(idx * request_interval + random.uniform(0, 0.2))
            async with semaphore:
                try:
                    result = await checker.check(brand.website)
                    if result.crawl_failed:
                        crawl_failure_count += 1
                        reason = result.fail_reason or "Unknown"
                        fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                    # Attach marketplace and platform data to brand
                    brand.marketplaces = result.marketplaces
                    brand.marketplace_links = result.marketplace_links
                    brand.priority = result.priority
                    brand.ecommerce_platform = result.platform  # Shopify, WooCommerce, etc.
                    progress.advance(task)
                    if result.crawl_failed:
                        return (brand, "crawl_failed")
                    return (brand, "ecommerce" if result.has_ecommerce else "no_ecommerce")
                except Exception as e:
                    crawl_failure_count += 1
                    reason = str(type(e).__name__)
                    fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
                    console.print(f"  [red]✗ Error: {brand.normalized_name.title()}: {e}[/red]")
                    progress.advance(task)
                    return (brand, "crawl_failed")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Checking {len(brands_with_website)} websites...", total=len(brands_with_website))

            # Run checks with staggered starts to avoid CDN rate limits
            tasks = [check_brand(brand, i, progress, task) for i, brand in enumerate(brands_with_website)]
            check_results = await asyncio.gather(*tasks)

        # Collect results — mark non-ecommerce brands as disqualified
        ecommerce_count = 0
        no_ecommerce_count = 0
        for brand, status in check_results:
            if status == "ecommerce":
                ecommerce_count += 1
            elif status == "no_ecommerce":
                brand.qualified = False
                brand.disqualify_reason = "No e-commerce detected"
                no_ecommerce_count += 1
            # crawl_failed: keep qualified=True (benefit of the doubt)

        # Also mark brands without websites
        for brand in brands:
            if not brand.website:
                brand.qualified = False
                brand.disqualify_reason = "No website"

        all_brands = [brand for brand, _ in check_results]
        # Add back brands without websites (weren't checked)
        all_brands.extend([b for b in brands if not b.website])

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("With e-commerce", f"[bold green]{ecommerce_count}[/bold green]")
        table.add_row("Without e-commerce", str(no_ecommerce_count))
        table.add_row("Fetch failed (included)", f"[yellow]{crawl_failure_count}[/yellow]")
        table.add_row("Skipped (no website)", str(skipped))
        console.print(table)

        # Show failure breakdown if any fetches failed
        if fail_reasons:
            console.print()
            fail_table = Table(box=box.SIMPLE, title="[dim]Fetch failure reasons[/dim]")
            fail_table.add_column("Reason", style="red")
            fail_table.add_column("Count", style="yellow", justify="right")
            for reason, count in sorted(fail_reasons.items(), key=lambda x: -x[1]):
                fail_table.add_row(reason, str(count))
            console.print(fail_table)

        return all_brands

    @staticmethod
    def _parse_employee_count(value) -> Optional[int]:
        """Parse employee count from various formats (int, string range, etc.)."""
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # Handle ranges like "201-500" or "1001-5000"
            match = re.search(r'(\d+)\s*[-–]\s*(\d+)', value)
            if match:
                return int(match.group(2))  # Use upper bound
            match = re.search(r'(\d+)', value)
            if match:
                return int(match.group(1))
        return None

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

    async def stage_4_enrich(self, brands: list[BrandGroup], linkedin_enricher=None) -> list[dict]:
        """Enrich brands with contact data using configured provider."""
        provider = settings.enrichment.provider
        self._show_stage_header(4, f"Contact Enrichment ({provider.title()})", "Finding company pages and executive contacts")

        # Split qualified vs disqualified
        qualified_brands = [b for b in brands if b.qualified]
        disqualified_brands = [b for b in brands if not b.qualified]

        console.print(f"  [dim]• {len(qualified_brands)} qualified leads to enrich, {len(disqualified_brands)} unqualified (skipped)[/dim]")

        enriched = []
        if qualified_brands:
            # Select enricher based on config
            if provider == "apollo":
                if not settings.apollo_api_key:
                    console.print("  [red]✗ APOLLO_API_KEY not set in .env[/red]")
                    console.print("  [dim]  Get your key at: https://app.apollo.io/[/dim]")
                    console.print("  [dim]  Or set enrichment.provider = \"linkedin\" in config/cities.json[/dim]")
                else:
                    enriched = await self._enrich_with_apollo(qualified_brands)
            else:
                enriched = await self._enrich_with_linkedin(qualified_brands, linkedin_enricher=linkedin_enricher)

        # Convert disqualified brands to lead dicts (no enrichment)
        for brand in disqualified_brands:
            enriched.append(self._brand_to_lead_dict(brand))

        return enriched

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

                        # Extract unique addresses from locations
                        addresses = []
                        for loc in brand.locations:
                            addr = loc.get("address", "")
                            if addr and addr not in addresses:
                                addresses.append(addr)

                        row = {
                            "brand_name": brand_name,
                            "location_count": brand.location_count,
                            "website": brand.website,
                            "has_ecommerce": True,
                            "ecommerce_platform": brand.ecommerce_platform or "",
                            "marketplaces": ", ".join(brand.marketplaces),
                            "priority": brand.priority,
                            "cities": ", ".join(brand.cities[:5]),
                            "addresses": " | ".join(addresses),
                            "linkedin_company": result.company.linkedin_url or "",
                            "employee_count": result.company.employee_count or "",
                            "industry": result.company.industry or "",
                            "technology_names": result.company.technology_names,
                            "apollo_location_count": result.company.retail_location_count,
                            "qualified": True,
                            "disqualify_reason": "",
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

    async def _enrich_with_linkedin(self, brands: list[BrandGroup], linkedin_enricher=None) -> list[dict]:
        """Enrich using LinkedIn page scraping."""
        enricher = linkedin_enricher or LinkedInEnricher(flaresolverr_url=settings.flaresolverr_url or None)
        enriched = []

        stats = {
            "linkedin_pages_found": 0,
            "total_contacts": 0,
            "c_suite": 0,
            "executive": 0,
            "management": 0,
            "other": 0,
        }

        concurrency = settings.enrichment.concurrency
        semaphore = asyncio.Semaphore(concurrency)
        request_interval = 0.5  # Stagger start times

        console.print(f"  [dim]• Enriching {len(brands)} qualified leads via LinkedIn page scraping ({concurrency} parallel)[/dim]")

        # Report JS rendering availability
        if enricher._browser_context:
            console.print(f"  [green]✓ Playwright browser active[/green]")
        elif await enricher._check_flaresolverr():
            console.print(f"  [green]✓ FlareSolverr connected[/green]")
        else:
            console.print(f"  [yellow]⚠ No JS renderer available — LinkedIn scraping will be limited (DDG fallback only)[/yellow]")
        console.print()

        async def enrich_brand(brand: BrandGroup, idx: int, progress, task) -> Optional[dict]:
            """Enrich a single brand with semaphore concurrency control."""
            # Stagger starts to avoid burst requests
            await asyncio.sleep(idx * request_interval + random.uniform(0, 0.3))

            async with semaphore:
                brand_name = brand.normalized_name.title()

                try:
                    # Step 1: Find LinkedIn company URL
                    linkedin_url = await enricher.find_company(brand.normalized_name, brand.website or "")

                    linkedin_data = None
                    contacts = []

                    if linkedin_url:
                        # Step 2: Scrape the company page for org data
                        linkedin_data = await enricher.scrape_company_page(linkedin_url)

                    # Step 3: Find contacts (people page scrape → DDG fallback)
                    contacts = await enricher.find_contacts(
                        brand.normalized_name, linkedin_url=linkedin_url, max_contacts=4
                    )

                    # Merge any company-page people not already found
                    if linkedin_data and linkedin_data.people:
                        existing_slugs = set()
                        for c in contacts:
                            slug_m = re.search(r'/in/([\w-]+)', c.linkedin_url)
                            if slug_m:
                                existing_slugs.add(slug_m.group(1))
                        for person in linkedin_data.people:
                            if len(contacts) >= 4:
                                break
                            slug_m = re.search(r'/in/([\w-]+)', person.linkedin_url)
                            if slug_m and slug_m.group(1) not in existing_slugs:
                                contacts.append(person)
                                existing_slugs.add(slug_m.group(1))

                    # Extract unique addresses from locations
                    addresses = []
                    for loc in brand.locations:
                        addr = loc.get("address", "")
                        if addr and addr not in addresses:
                            addresses.append(addr)

                    row = {
                        "brand_name": brand_name,
                        "location_count": brand.location_count,
                        "website": brand.website,
                        "has_ecommerce": True,
                        "ecommerce_platform": brand.ecommerce_platform or "",
                        "marketplaces": ", ".join(brand.marketplaces),
                        "priority": brand.priority,
                        "cities": ", ".join(brand.cities[:5]),
                        "addresses": " | ".join(addresses),
                        "linkedin_company": linkedin_url or "",
                        "employee_count": linkedin_data.employee_range if linkedin_data else "",
                        "industry": linkedin_data.industry if linkedin_data else "",
                        "apollo_location_count": linkedin_data.location_count if linkedin_data else None,
                        "qualified": True,
                        "disqualify_reason": "",
                    }

                    # Add contacts (up to 4)
                    for i in range(4):
                        if i < len(contacts):
                            row[f"contact_{i+1}_name"] = contacts[i].name
                            row[f"contact_{i+1}_title"] = contacts[i].title
                            row[f"contact_{i+1}_email"] = ""
                            row[f"contact_{i+1}_phone"] = ""
                            row[f"contact_{i+1}_linkedin"] = contacts[i].linkedin_url or ""
                        else:
                            row[f"contact_{i+1}_name"] = ""
                            row[f"contact_{i+1}_title"] = ""
                            row[f"contact_{i+1}_email"] = ""
                            row[f"contact_{i+1}_phone"] = ""
                            row[f"contact_{i+1}_linkedin"] = ""

                    if contacts:
                        progress.update(task, description=f"[green]✓[/green] {brand_name}: {len(contacts)} contacts")
                    else:
                        progress.update(task, description=f"[yellow]○[/yellow] {brand_name}: No data found")

                    return row, linkedin_url is not None, contacts
                except RuntimeError:
                    raise
                except Exception as e:
                    console.print(f"  [red]✗ Error enriching {brand_name}: {e}[/red]")
                    return None
                finally:
                    progress.advance(task)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Enriching...", total=len(brands))

            results = await asyncio.gather(
                *[enrich_brand(brand, idx, progress, task) for idx, brand in enumerate(brands)],
                return_exceptions=True,
            )

        for result in results:
            if result is None or isinstance(result, Exception):
                continue
            row, found_linkedin, contacts = result
            enriched.append(row)
            if found_linkedin:
                stats["linkedin_pages_found"] += 1
            for contact in contacts:
                category = self._categorize_contact(contact.title)
                stats["total_contacts"] += 1
                if category == "C-Suite":
                    stats["c_suite"] += 1
                elif category == "Executive":
                    stats["executive"] += 1
                elif category == "Management":
                    stats["management"] += 1
                else:
                    stats["other"] += 1

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

    async def stage_4b_quality_gate(self, enriched: list[dict], linkedin_enricher=None) -> list[dict]:
        """Verify chain sizes, mark disqualified leads, supplement contacts."""
        self._show_stage_header("4b", "Quality Gate", "Verifying chain sizes and supplementing contacts")

        if not enriched:
            console.print("  [yellow]⚠ No leads to verify[/yellow]")
            return []

        max_locations = settings.quality_gate_max_locations
        max_employees = settings.quality_gate_max_employees
        enricher = linkedin_enricher or LinkedInEnricher(flaresolverr_url=settings.flaresolverr_url or None)

        # Only check qualified leads (already-disqualified ones pass through untouched)
        qualified_leads = [l for l in enriched if l.get("qualified", True)]
        console.print(f"  [dim]• Checking {len(qualified_leads)} qualified leads[/dim]")
        console.print(f"  [dim]• Max locations: {max_locations}, Max employees: {max_employees}[/dim]")
        console.print()

        passed_count = 0
        filtered_count = 0

        for lead in qualified_leads:
            brand_name = lead.get("brand_name", "Unknown")
            apollo_locs = lead.get("apollo_location_count")
            employee_count = lead.get("employee_count")
            linkedin_url = lead.get("linkedin_company", "")

            # Signal 1: Apollo retail_location_count
            if apollo_locs and isinstance(apollo_locs, (int, float)) and apollo_locs > max_locations:
                lead["qualified"] = False
                lead["disqualify_reason"] = f"Too many locations ({int(apollo_locs)})"
                console.print(f"  [red]✗ Disqualified:[/red] {brand_name} — Apollo says {int(apollo_locs)} locations")
                filtered_count += 1
                continue

            # Signal 2: LinkedIn company page location count
            linkedin_data = None
            if apollo_locs is None and linkedin_url:
                if not employee_count:
                    try:
                        linkedin_data = await enricher.scrape_company_page(linkedin_url)
                        if linkedin_data.location_count and linkedin_data.location_count > max_locations:
                            lead["qualified"] = False
                            lead["disqualify_reason"] = f"Too many locations ({linkedin_data.location_count})"
                            console.print(f"  [red]✗ Disqualified:[/red] {brand_name} — LinkedIn says {linkedin_data.location_count} locations")
                            filtered_count += 1
                            continue
                    except Exception:
                        pass

            # Signal 3: Employee count heuristic
            parsed_employees = self._parse_employee_count(employee_count)
            if apollo_locs is None and parsed_employees and parsed_employees > max_employees:
                lead["qualified"] = False
                lead["disqualify_reason"] = f"Too many employees ({parsed_employees})"
                console.print(f"  [red]✗ Disqualified:[/red] {brand_name} — {parsed_employees} employees (likely large chain)")
                filtered_count += 1
                continue

            # Lead passed quality gate - supplement contacts from LinkedIn if available
            has_empty_slot = any(not lead.get(f"contact_{i}_name") for i in range(1, 5))
            if has_empty_slot and linkedin_url:
                try:
                    supplement_contacts = await enricher.find_contacts(
                        brand_name, linkedin_url=linkedin_url, max_contacts=4
                    )
                    if linkedin_data and linkedin_data.people:
                        existing_slugs = {
                            re.search(r'/in/([\w-]+)', c.linkedin_url).group(1)
                            for c in supplement_contacts
                            if re.search(r'/in/([\w-]+)', c.linkedin_url)
                        }
                        for person in linkedin_data.people:
                            slug_m = re.search(r'/in/([\w-]+)', person.linkedin_url)
                            if slug_m and slug_m.group(1) not in existing_slugs:
                                supplement_contacts.append(person)
                                existing_slugs.add(slug_m.group(1))

                    existing_names = {lead.get(f"contact_{j}_name", "").lower() for j in range(1, 5)}
                    for person in supplement_contacts:
                        if person.name.lower() in existing_names:
                            continue
                        for i in range(1, 5):
                            if not lead.get(f"contact_{i}_name"):
                                lead[f"contact_{i}_name"] = person.name
                                lead[f"contact_{i}_title"] = person.title
                                lead[f"contact_{i}_linkedin"] = person.linkedin_url or ""
                                if f"contact_{i}_email" not in lead:
                                    lead[f"contact_{i}_email"] = ""
                                if f"contact_{i}_phone" not in lead:
                                    lead[f"contact_{i}_phone"] = ""
                                existing_names.add(person.name.lower())
                                break
                except Exception:
                    pass

            # Explicitly mark as qualified (ensures key exists even for older data)
            lead.setdefault("qualified", True)
            lead.setdefault("disqualify_reason", "")
            passed_count += 1
            console.print(f"  [green]✓ Passed:[/green] {brand_name}")

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Passed quality gate", f"[bold green]{passed_count}[/bold green]")
        table.add_row("Disqualified", f"[bold red]{filtered_count}[/bold red]")
        console.print(table)

        return enriched  # Return ALL leads (qualified + disqualified)

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
                "qualified", "disqualify_reason",
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

            # Sort: qualified first, then by priority_score descending
            sort_cols = []
            sort_asc = []
            if 'qualified' in df.columns:
                sort_cols.append('qualified')
                sort_asc.append(False)  # True (qualified) before False
            if 'priority_score' in df.columns:
                sort_cols.append('priority_score')
                sort_asc.append(False)
            if sort_cols:
                df = df.sort_values(by=sort_cols, ascending=sort_asc)

            output_file = self.output_dir / f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(output_file, index=False)

        # Final summary
        qualified_count = sum(1 for d in data if d.get("qualified", True))
        disqualified_count = len(data) - qualified_count
        console.print(f"  [green]✓ Exported {len(data)} leads ({qualified_count} qualified, {disqualified_count} disqualified)[/green]")
        console.print(f"  [dim]  File: {output_file}[/dim]")

        # Show preview (qualified leads first)
        qualified_leads = [d for d in data if d.get("qualified", True)]
        preview_leads = qualified_leads[:3] if qualified_leads else data[:3]
        if preview_leads:
            console.print(f"\n  [bold]Preview (top 3 qualified leads):[/bold]")
            table = Table(box=box.SIMPLE, show_lines=True)
            table.add_column("Brand", style="cyan")
            table.add_column("Locations", justify="center")
            table.add_column("Website", style="dim")
            table.add_column("Contacts", justify="center")

            for lead in preview_leads:
                contacts = sum(1 for i in range(1, 5) if lead.get(f"contact_{i}_name"))
                table.add_row(
                    lead["brand_name"],
                    str(lead["location_count"]),
                    lead["website"][:40] + "..." if lead["website"] and len(lead["website"]) > 40 else lead.get("website", ""),
                    str(contacts),
                )

            console.print(table)

        return str(output_file)

    def _brand_to_lead_dict(self, brand: BrandGroup) -> dict:
        """Convert a single BrandGroup to a lead dict."""
        addresses = []
        for loc in brand.locations:
            addr = loc.get("address", "")
            if addr and addr not in addresses:
                addresses.append(addr)

        row = {
            "brand_name": brand.normalized_name.title(),
            "location_count": brand.location_count,
            "website": brand.website,
            "has_ecommerce": brand.qualified,  # qualified means e-commerce was detected or assumed
            "ecommerce_platform": brand.ecommerce_platform or "",
            "marketplaces": ", ".join(brand.marketplaces),
            "priority": brand.priority,
            "cities": ", ".join(brand.cities[:5]),
            "addresses": " | ".join(addresses),
            "linkedin_company": "",
            "employee_count": "",
            "industry": "",
            "qualified": brand.qualified,
            "disqualify_reason": brand.disqualify_reason,
        }

        # Empty contact slots
        for i in range(1, 5):
            row[f"contact_{i}_name"] = ""
            row[f"contact_{i}_title"] = ""
            row[f"contact_{i}_email"] = ""
            row[f"contact_{i}_phone"] = ""
            row[f"contact_{i}_linkedin"] = ""

        return row

    def _brands_to_leads(self, brands: list[BrandGroup]) -> list[dict]:
        """Convert BrandGroups to lead dicts without enrichment data."""
        return [self._brand_to_lead_dict(brand) for brand in brands]

    async def enrich_csv(self, csv_path: str, max_contacts: int = 4) -> str:
        """Enrich an existing leads CSV with Apollo contact data."""
        import pandas as pd

        self._show_stage_header(4, "Apollo Enrichment", "Enriching existing leads with contact data")

        if not settings.apollo_api_key:
            console.print("  [red]APOLLO_API_KEY not set in .env[/red]")
            console.print("  [dim]  Get your key at: https://app.apollo.io/[/dim]")
            return csv_path

        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        console.print(f"  [dim]• Loaded {len(df)} leads from {csv_path}[/dim]")

        enricher = ApolloEnricher(api_key=settings.apollo_api_key)
        stats = {"companies_found": 0, "total_contacts": 0, "with_email": 0, "with_phone": 0}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Enriching...", total=len(df))

            for idx, row in df.iterrows():
                brand_name = str(row.get("brand_name", ""))
                website = str(row.get("website", ""))
                progress.update(task, description=f"[cyan]Searching[/cyan] {brand_name}")

                if not website or website == "nan":
                    progress.advance(task)
                    continue

                try:
                    result = await enricher.enrich(brand_name, website, max_contacts)
                    if result:
                        if result.company.linkedin_url:
                            stats["companies_found"] += 1
                            df.at[idx, "linkedin_company"] = result.company.linkedin_url
                        if result.company.industry:
                            df.at[idx, "industry"] = result.company.industry
                        if result.company.employee_count:
                            df.at[idx, "employee_count"] = result.company.employee_count

                        for i, contact in enumerate(result.contacts[:4], 1):
                            df.at[idx, f"contact_{i}_name"] = contact.name
                            df.at[idx, f"contact_{i}_title"] = contact.title
                            df.at[idx, f"contact_{i}_email"] = contact.email or ""
                            df.at[idx, f"contact_{i}_phone"] = contact.phone or ""
                            df.at[idx, f"contact_{i}_linkedin"] = contact.linkedin_url or ""
                            stats["total_contacts"] += 1
                            if contact.email:
                                stats["with_email"] += 1
                            if contact.phone:
                                stats["with_phone"] += 1

                        contact_count = len(result.contacts)
                        if contact_count > 0:
                            progress.update(task, description=f"[green]✓[/green] {brand_name}: {contact_count} contacts")
                        else:
                            progress.update(task, description=f"[yellow]○[/yellow] {brand_name}: No contacts")

                    await asyncio.sleep(0.5)
                except Exception as e:
                    error_msg = str(e)
                    if "credits" in error_msg.lower():
                        console.print(f"\n  [red]Apollo credits exhausted. Stopping.[/red]")
                        break
                    console.print(f"  [red]✗ Error: {brand_name}: {e}[/red]")

                progress.advance(task)

        # Summary
        console.print()
        table = Table(title="Apollo Enrichment Results", box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Leads processed", str(len(df)))
        table.add_row("LinkedIn company pages", str(stats["companies_found"]))
        table.add_row("Total contacts", f"[bold]{stats['total_contacts']}[/bold]")
        table.add_row("  With email", f"[bold cyan]{stats['with_email']}[/bold cyan]")
        table.add_row("  With phone", str(stats["with_phone"]))
        console.print(table)

        # Save enriched file
        output_file = self.output_dir / f"leads_enriched_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(output_file, index=False)

        console.print(f"\n  [green]✓ Enriched leads saved to {output_file}[/green]")
        return str(output_file)

    async def run(
        self,
        verticals: list[str] = ["health_wellness", "sporting_goods", "apparel"],
        countries: list[str] = ["us", "canada"],
        resume_checkpoint: Optional[Path] = None,
        search_mode: Optional[str] = None,
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
                enrichment_status = (
                    f"[green]Enabled[/green] ({settings.enrichment.provider})"
                    if settings.enrichment.enabled
                    else "[dim]Disabled[/dim]"
                )
                settings_block = (
                    f"[bold]Active Settings:[/bold]\n"
                    f"  Search mode:              {settings.search_mode.capitalize()}\n"
                    f"  Search concurrency:       {settings.search_concurrency}\n"
                    f"  E-commerce concurrency:   {settings.ecommerce_concurrency}\n"
                    f"  Health check concurrency: {settings.health_check_concurrency}\n"
                    f"  Enrichment:               {enrichment_status}\n"
                    f"  Quality gate:             ≤{settings.quality_gate_max_locations} locations, ≤{settings.quality_gate_max_employees} employees"
                )
                # Show what changed vs original run
                saved = checkpoint.saved_settings
                if saved:
                    diffs = []
                    if saved.get("search_concurrency") != settings.search_concurrency:
                        diffs.append(f"search_concurrency: {saved['search_concurrency']} → {settings.search_concurrency}")
                    if saved.get("ecommerce_concurrency") != settings.ecommerce_concurrency:
                        diffs.append(f"ecommerce_concurrency: {saved['ecommerce_concurrency']} → {settings.ecommerce_concurrency}")
                    if saved.get("health_check_concurrency") != settings.health_check_concurrency:
                        diffs.append(f"health_check_concurrency: {saved['health_check_concurrency']} → {settings.health_check_concurrency}")
                    if saved.get("enrichment_enabled") != settings.enrichment.enabled:
                        diffs.append(f"enrichment: {'enabled' if saved.get('enrichment_enabled') else 'disabled'} → {'enabled' if settings.enrichment.enabled else 'disabled'}")
                    if diffs:
                        settings_block += "\n\n[bold yellow]Changed from original run:[/bold yellow]\n  " + "\n  ".join(diffs)

                console.print(Panel(
                    f"[bold yellow]Resuming Pipeline[/bold yellow]\n\n"
                    f"Last completed: Stage {checkpoint.stage}\n"
                    f"Verticals: {', '.join(verticals)}\n"
                    f"Countries: {', '.join(countries)}\n"
                    f"Saved at: {checkpoint.timestamp}\n\n"
                    f"{settings_block}",
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
            enrichment_status = (
                f"[green]Enabled[/green] ({settings.enrichment.provider})"
                if settings.enrichment.enabled
                else "[dim]Disabled[/dim]"
            )
            console.print()
            console.print(Panel(
                "[bold]Pipeline Starting[/bold]\n\n"
                f"Verticals: {', '.join(verticals)}\n"
                f"Countries: {', '.join(countries)}\n\n"
                f"[bold]Settings:[/bold]\n"
                f"  Search mode:           {settings.search_mode.capitalize()}\n"
                f"  Search concurrency:    {settings.search_concurrency}\n"
                f"  E-commerce concurrency:{settings.ecommerce_concurrency}\n"
                f"  Health check concurrency: {settings.health_check_concurrency}\n"
                f"  Enrichment:            {enrichment_status}\n"
                f"  Quality gate:          ≤{settings.quality_gate_max_locations} locations, ≤{settings.quality_gate_max_employees} employees",
                title="[bold blue]🚀 Lead Generator[/bold blue]",
                border_style="blue",
            ))

        # Apply search mode if specified
        if search_mode:
            settings.search_mode = search_mode

        # Initialize data from checkpoint or empty
        places = checkpoint.places if checkpoint and start_stage >= 1 else []
        searched_cities = checkpoint.searched_cities if checkpoint else []
        brands = [self._deserialize_brand(b) for b in checkpoint.brands] if checkpoint and start_stage >= 2 else []
        verified_brands = [self._deserialize_brand(b) for b in checkpoint.verified_brands] if checkpoint and start_stage >= 2.5 else []
        healthy_brands = [self._deserialize_brand(b) for b in checkpoint.healthy_brands] if checkpoint and start_stage >= 2.6 else []
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
            brands = self.stage_2_group(places, searched_cities)
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

        # Stage 2c: Website health check
        if start_stage < 2.6:
            healthy_brands = await self.stage_2c_website_health(verified_brands)
            checkpoint.healthy_brands = [self._serialize_brand(b) for b in healthy_brands]
            checkpoint.stage = 2.6
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 2c complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 2c (Health Check) - loaded {len(healthy_brands)} healthy brands from checkpoint[/dim]")

        # Stage 3: E-commerce check
        if start_stage < 3:
            ecommerce_brands = await self.stage_3_ecommerce(healthy_brands)
            checkpoint.ecommerce_brands = [self._serialize_brand(b) for b in ecommerce_brands]
            checkpoint.stage = 3
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 3 complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 3 (E-commerce) - loaded {len(ecommerce_brands)} e-commerce brands from checkpoint[/dim]")

        # Stage 4: Contact enrichment (Apollo or LinkedIn) — skip if disabled
        if settings.enrichment.enabled:
            # Create shared LinkedIn enricher with Playwright browser for stages 4 + 4b
            linkedin_enricher = LinkedInEnricher(
                flaresolverr_url=settings.flaresolverr_url or None,
                cookie_file=settings.enrichment.cookie_file or None,
            )
            try:
                if settings.enrichment.use_playwright:
                    await linkedin_enricher.start_browser()

                if start_stage < 4:
                    enriched = await self.stage_4_enrich(ecommerce_brands, linkedin_enricher=linkedin_enricher)
                    checkpoint.enriched = enriched
                    checkpoint.stage = 4
                    self._save_checkpoint(checkpoint)
                    console.print(f"  [dim]💾 Checkpoint saved (Stage 4 complete)[/dim]")
                else:
                    console.print(f"  [dim]⏭ Skipping Stage 4 (Enrichment) - loaded {len(enriched)} enriched leads from checkpoint[/dim]")

                # Stage 4b: Quality gate
                if start_stage < 4.5:
                    enriched = await self.stage_4b_quality_gate(enriched, linkedin_enricher=linkedin_enricher)
                    checkpoint.enriched = enriched
                    checkpoint.stage = 4.5
                    self._save_checkpoint(checkpoint)
                    console.print(f"  [dim]💾 Checkpoint saved (Stage 4b complete)[/dim]")
            finally:
                await linkedin_enricher.close_browser()
        else:
            # Skip enrichment — convert brands to export format directly
            console.print(f"\n  [dim]⏭ Skipping Stage 4 & 4b (Enrichment disabled)[/dim]")
            enriched = self._brands_to_leads(ecommerce_brands)
            checkpoint.enriched = enriched
            checkpoint.stage = 4.5
            self._save_checkpoint(checkpoint)

        # Stage 5: Score leads
        scored = self.stage_5_score(enriched)

        # Stage 6: Export
        output_file = self.stage_6_export(scored)

        # Clear checkpoint on successful completion
        self.clear_checkpoint()

        # Final summary
        elapsed = datetime.now() - start_time
        qualified_count = sum(1 for lead in scored if lead.get("qualified", True))
        disqualified_count = len(scored) - qualified_count
        console.print()
        console.print(Panel(
            f"[bold green]✓ Pipeline Complete![/bold green]\n\n"
            f"Duration: {elapsed.seconds // 60}m {elapsed.seconds % 60}s\n"
            f"Leads found: {len(scored)} ({qualified_count} qualified, {disqualified_count} disqualified)\n"
            f"Output: {output_file}",
            title="[bold green]Summary[/bold green]",
            border_style="green",
        ))

        return output_file
