# Apollo.io Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace broken LinkedIn scraper with Apollo.io API for verified contact enrichment.

**Architecture:** Modify `stage_4_linkedin()` in pipeline.py to use `ApolloEnricher` instead of `LinkedInEnricher`. The Apollo module already exists and handles company search, contact search by title, retry logic. Config already supports `enrichment.provider` setting.

**Tech Stack:** Python, httpx (async HTTP), Apollo.io API, existing ApolloEnricher class

---

## Task 1: Update Pipeline to Use Apollo Enricher

**Files:**
- Modify: `src/pipeline.py:19` (imports)
- Modify: `src/pipeline.py:442-562` (stage_4_linkedin method)

**Step 1: Update imports**

In `src/pipeline.py`, change line 19 from:
```python
from src.linkedin_enrich import LinkedInEnricher
```
to:
```python
from src.linkedin_enrich import LinkedInEnricher
from src.apollo_enrich import ApolloEnricher
```

**Step 2: Modify stage_4_linkedin to support both providers**

Replace the `stage_4_linkedin` method (lines 442-562) with this implementation that checks `settings.enrichment.provider`:

```python
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
```

**Step 3: Update run() method to call stage_4_enrich**

In the `run()` method, change line 716 from:
```python
enriched = await self.stage_4_linkedin(ecommerce_brands)
```
to:
```python
enriched = await self.stage_4_enrich(ecommerce_brands)
```

**Step 4: Run tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests pass (existing tests mock the enrichment stage)

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/pipeline.py
git commit -m "feat: integrate Apollo.io enrichment with provider switching"
```

---

## Task 2: Update Config to Default to Apollo

**Files:**
- Modify: `config/cities.json`

**Step 1: Change default enrichment provider**

In `config/cities.json`, find the `enrichment` section and change `provider` from `"linkedin"` to `"apollo"`:

```json
"enrichment": {
    "enabled": true,
    "provider": "apollo",
    "max_contacts": 4
}
```

**Step 2: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add config/cities.json
git commit -m "config: default to Apollo.io for enrichment"
```

---

## Task 3: Test End-to-End with Apollo

**Step 1: Set Apollo API key**

Add your Apollo API key to `.env`:
```
APOLLO_API_KEY=your_actual_apollo_key
```

**Step 2: Run pipeline with a small test**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src --verticals health_wellness --countries canada`

Expected:
- Stage 4 shows "Contact Enrichment (Apollo)"
- Contacts have real names and titles
- Some contacts have email addresses

**Step 3: Verify output CSV**

Check the output CSV in `data/output/` - contacts should have:
- Real names (not "John Smith 32120344")
- Real titles (not "(to be verified)")
- Some emails and phone numbers

---

## Summary

| Task | Files | Purpose |
|------|-------|---------|
| 1 | pipeline.py | Add Apollo enrichment, keep LinkedIn as fallback |
| 2 | config/cities.json | Default to Apollo provider |
| 3 | Manual test | Verify end-to-end with real Apollo key |

**Prerequisites:**
1. Sign up at https://app.apollo.io/
2. Get API key from Settings → Integrations → API
3. Add to `.env`: `APOLLO_API_KEY=your_key`

**To run after implementation:**
```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
python -m src --verticals all --countries us,canada
```
