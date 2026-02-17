# Pipeline Quality Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve lead pipeline accuracy by filtering dead websites before e-commerce detection and filtering large chains after enrichment using Apollo + LinkedIn location data.

**Architecture:** Three new pipeline stages (2c, 4b) plus a LinkedIn company page scraper. Stage 2c does cheap HTTP health checks to remove dead websites. Stage 4b uses Apollo/LinkedIn/employee data to catch large chains that slipped through the initial filter. The LinkedIn scraper also provides supplementary contact data.

**Tech Stack:** Python, httpx (async HTTP), Firecrawl API (LinkedIn scraping), pytest + pytest-asyncio

**Git repo:** `/home/farzin/PROSPECTFORGE/lead-generator` (git commands must use `git -C /home/farzin/PROSPECTFORGE/lead-generator`)

---

### Task 1: Add Config Settings for Quality Gate and Health Check

**Files:**
- Modify: `config/cities.json`
- Modify: `src/config.py:44-114`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_settings_loads_quality_gate_config():
    settings = Settings()

    assert settings.quality_gate_max_locations == 10
    assert settings.quality_gate_max_employees == 500

def test_settings_loads_health_check_config():
    settings = Settings()

    assert settings.health_check_concurrency == 10
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_config.py::test_settings_loads_quality_gate_config tests/test_config.py::test_settings_loads_health_check_config -v`
Expected: FAIL with AttributeError

**Step 3: Add config keys to cities.json**

Add after the `"email_verification"` block in `config/cities.json`:

```json
  "quality_gate": {
    "max_locations": 10,
    "max_employees": 500
  },
  "health_check": {
    "concurrency": 10
  }
```

**Step 4: Add fields to Settings dataclass and parsing in `src/config.py`**

Add fields to the `Settings` dataclass after `outreach`:

```python
    quality_gate_max_locations: int = 10
    quality_gate_max_employees: int = 500
    health_check_concurrency: int = 10
```

Add parsing in `__post_init__` after the outreach settings block:

```python
        # Load quality gate settings
        quality_gate_config = config.get("quality_gate", {})
        self.quality_gate_max_locations = quality_gate_config.get("max_locations", 10)
        self.quality_gate_max_employees = quality_gate_config.get("max_employees", 500)

        # Load health check settings
        health_check_config = config.get("health_check", {})
        self.health_check_concurrency = health_check_config.get("concurrency", 10)
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git -C /home/farzin/PROSPECTFORGE/lead-generator add config/cities.json src/config.py tests/test_config.py
git -C /home/farzin/PROSPECTFORGE/lead-generator commit -m "feat: add quality gate and health check config settings"
```

---

### Task 2: Website Health Check (Stage 2c)

**Files:**
- Modify: `src/pipeline.py`
- Create: `tests/test_website_health.py`

**Step 1: Write the failing tests**

Create `tests/test_website_health.py`:

```python
# tests/test_website_health.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from src.pipeline import Pipeline
from src.brand_grouper import BrandGroup


def _make_brand(name: str, website: str) -> BrandGroup:
    return BrandGroup(
        normalized_name=name,
        original_names=[name.title()],
        location_count=5,
        locations=[],
        website=website,
        cities=["Toronto"],
    )


@pytest.mark.asyncio
async def test_healthy_website_passes():
    """Brands with responsive websites pass through."""
    pipeline = Pipeline()
    brands = [_make_brand("good store", "https://goodstore.com")]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://goodstore.com")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 1
    assert result[0].normalized_name == "good store"


@pytest.mark.asyncio
async def test_404_website_filtered():
    """Brands with 404 websites are filtered out."""
    pipeline = Pipeline()
    brands = [_make_brand("dead store", "https://deadstore.com")]

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.url = httpx.URL("https://deadstore.com")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_dns_failure_filtered():
    """Brands with unresolvable domains are filtered out."""
    pipeline = Pipeline()
    brands = [_make_brand("expired store", "https://expired-domain.com")]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(side_effect=httpx.ConnectError("DNS resolution failed"))
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_parked_domain_filtered():
    """Brands redirecting to domain parking are filtered out."""
    pipeline = Pipeline()
    brands = [_make_brand("parked store", "https://parkedstore.com")]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://www.godaddy.com/parking")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_brand_without_website_passes():
    """Brands without websites pass through (filtered later by e-commerce check)."""
    pipeline = Pipeline()
    brands = [_make_brand("no website store", None)]

    result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_mixed_brands_filters_correctly():
    """Mix of healthy and dead websites filters correctly."""
    pipeline = Pipeline()
    brands = [
        _make_brand("healthy", "https://healthy.com"),
        _make_brand("dead", "https://dead.com"),
        _make_brand("no site", None),
    ]

    async def mock_head(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.url = httpx.URL(str(url))
        if "dead" in str(url):
            mock_resp.status_code = 404
        else:
            mock_resp.status_code = 200
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.head = AsyncMock(side_effect=mock_head)
        mock_client_cls.return_value = mock_client

        result = await pipeline.stage_2c_website_health(brands)

    assert len(result) == 2
    names = [b.normalized_name for b in result]
    assert "healthy" in names
    assert "no site" in names
    assert "dead" not in names
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_website_health.py -v`
Expected: FAIL with AttributeError (stage_2c_website_health doesn't exist)

**Step 3: Implement stage_2c_website_health in pipeline.py**

Add this method to the `Pipeline` class in `src/pipeline.py`, after `stage_2b_verify_chain_size`:

```python
    # Known domain parking / parked domain hosts
    PARKING_DOMAINS = {
        "godaddy.com", "sedoparking.com", "hugedomains.com",
        "afternic.com", "dan.com", "parkingcrew.net",
        "bodis.com", "above.com", "undeveloped.com",
    }

    async def stage_2c_website_health(self, brands: list[BrandGroup]) -> list[BrandGroup]:
        """Filter out brands with dead or parked websites."""
        self._show_stage_header("2c", "Website Health Check", "Filtering dead and parked websites")

        if not brands:
            console.print("  [yellow]⚠ No brands to check[/yellow]")
            return []

        brands_with_site = [b for b in brands if b.website]
        brands_without_site = [b for b in brands if not b.website]
        concurrency = settings.health_check_concurrency
        semaphore = asyncio.Semaphore(concurrency)

        console.print(f"  [dim]• Checking {len(brands_with_site)} websites ({concurrency} parallel)[/dim]")
        if brands_without_site:
            console.print(f"  [dim]• Passing through {len(brands_without_site)} brands without websites[/dim]")
        console.print()

        async def check_health(brand: BrandGroup) -> tuple[BrandGroup, bool, str]:
            """Check if a brand's website is alive. Returns (brand, is_healthy, reason)."""
            async with semaphore:
                url = brand.website
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
                        for parking_domain in self.PARKING_DOMAINS:
                            if parking_domain in final_host:
                                return (brand, False, f"Parked domain ({parking_domain})")

                        return (brand, True, "OK")

                except (httpx.ConnectError, httpx.ConnectTimeout):
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_website_health.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git -C /home/farzin/PROSPECTFORGE/lead-generator add src/pipeline.py tests/test_website_health.py
git -C /home/farzin/PROSPECTFORGE/lead-generator commit -m "feat: add website health check stage 2c"
```

---

### Task 3: LinkedIn Company Page Scraper

**Files:**
- Modify: `src/linkedin_enrich.py`
- Modify: `tests/test_linkedin_enrich.py`

**Step 1: Write the failing tests**

Add to `tests/test_linkedin_enrich.py`:

```python
from src.linkedin_enrich import LinkedInEnricher, Contact, LinkedInCompanyData


@pytest.fixture
def linkedin_company_page_markdown():
    """Realistic LinkedIn company page markdown as returned by Firecrawl."""
    return {
        "data": {
            "markdown": """
# Flaman Fitness

## About

Flaman Fitness is a leading Canadian retailer of fitness equipment.

**Industry:** Retail
**Company size:** 201-500 employees
**Headquarters:** Saskatoon, Saskatchewan
**Founded:** 1959

**Specialties:** Fitness Equipment, Treadmills, Exercise Bikes

36 locations

## People

### Leadership

[**John Macdonell**](https://www.linkedin.com/in/john-macdonell)
CEO

[**Sarah Thompson**](https://www.linkedin.com/in/sarah-thompson-fitness)
Chief Operating Officer

[**Mike Rodriguez**](https://www.linkedin.com/in/mike-rodriguez-ab)
Director of Operations

[**Lisa Chen**](https://www.linkedin.com/in/lisa-chen-retail)
Marketing Manager
"""
        }
    }


@pytest.fixture
def linkedin_page_no_locations():
    """LinkedIn page without location count."""
    return {
        "data": {
            "markdown": """
# Small Store Co

## About

**Industry:** Retail
**Company size:** 11-50 employees

## People

[**Jane Owner**](https://www.linkedin.com/in/jane-owner)
Founder & CEO
"""
        }
    }


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_locations(linkedin_company_page_markdown):
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert result.location_count == 36


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_people(linkedin_company_page_markdown):
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert len(result.people) >= 3
    # Check first person
    assert result.people[0].name == "John Macdonell"
    assert "CEO" in result.people[0].title


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_employee_range(linkedin_company_page_markdown):
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert result.employee_range == "201-500"


@pytest.mark.asyncio
async def test_scrape_company_page_handles_missing_locations(linkedin_page_no_locations):
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_page_no_locations

        result = await enricher.scrape_company_page("https://linkedin.com/company/small-store")

    assert result.location_count is None
    assert len(result.people) >= 1


@pytest.mark.asyncio
async def test_scrape_company_page_handles_fetch_failure():
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_fetch_page', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("Firecrawl error")

        result = await enricher.scrape_company_page("https://linkedin.com/company/broken")

    assert result.location_count is None
    assert result.people == []
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_linkedin_enrich.py::test_scrape_company_page_extracts_locations tests/test_linkedin_enrich.py::test_scrape_company_page_extracts_people -v`
Expected: FAIL with ImportError (LinkedInCompanyData not defined)

**Step 3: Implement LinkedInCompanyData and scrape_company_page**

Add to `src/linkedin_enrich.py`, after the `Contact` dataclass:

```python
@dataclass
class LinkedInCompanyData:
    """Data extracted from a LinkedIn company page."""
    location_count: Optional[int]
    employee_range: Optional[str]
    industry: Optional[str]
    people: list[Contact]
```

Add this method to the `LinkedInEnricher` class, after `_search_people`:

```python
    def _parse_company_page(self, markdown: str) -> LinkedInCompanyData:
        """Parse LinkedIn company page markdown to extract structured data."""
        location_count = None
        employee_range = None
        industry = None
        people = []

        # Extract location count - patterns like "36 locations" or "36 associated members"
        loc_match = re.search(r'(\d+)\s+locations?\b', markdown, re.IGNORECASE)
        if loc_match:
            location_count = int(loc_match.group(1))

        # Extract employee range - patterns like "201-500 employees" or "Company size: 201-500"
        emp_match = re.search(r'(\d+[\-–]\d+)\s*employees', markdown, re.IGNORECASE)
        if not emp_match:
            emp_match = re.search(r'[Cc]ompany\s+size[:\s]*(\d+[\-–]\d+)', markdown)
        if emp_match:
            employee_range = emp_match.group(1).replace('–', '-')

        # Extract industry
        ind_match = re.search(r'\*\*Industry:?\*\*\s*(.+)', markdown)
        if not ind_match:
            ind_match = re.search(r'Industry[:\s]+([A-Z][^\n]+)', markdown)
        if ind_match:
            industry = ind_match.group(1).strip()

        # Extract people - look for LinkedIn profile links with names and titles
        # Pattern: [**Name**](linkedin_url)\n Title
        people_pattern = re.findall(
            r'\[\*\*(.+?)\*\*\]\(https?://(?:www\.)?linkedin\.com/in/([\w-]+)\)\s*\n\s*(.+)',
            markdown
        )
        for name, profile_id, title in people_pattern:
            people.append(Contact(
                name=name.strip(),
                title=title.strip(),
                linkedin_url=f"https://www.linkedin.com/in/{profile_id}"
            ))

        # Fallback: look for simpler patterns like "Name\nTitle" near linkedin URLs
        if not people:
            simple_pattern = re.findall(
                r'([\w\s]+?)\s*[-–—|]\s*(?:https?://)?linkedin\.com/in/([\w-]+)',
                markdown
            )
            for name, profile_id in simple_pattern:
                name = name.strip()
                if len(name) > 2 and len(name) < 60:
                    people.append(Contact(
                        name=name,
                        title="(see LinkedIn profile)",
                        linkedin_url=f"https://www.linkedin.com/in/{profile_id}"
                    ))

        return LinkedInCompanyData(
            location_count=location_count,
            employee_range=employee_range,
            industry=industry,
            people=people,
        )

    async def scrape_company_page(self, linkedin_url: str) -> LinkedInCompanyData:
        """Scrape a LinkedIn company page and extract structured data."""
        try:
            data = await self._fetch_page(linkedin_url)
            markdown = data.get("data", {}).get("markdown", "")
            if not markdown:
                return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])
            return self._parse_company_page(markdown)
        except Exception:
            return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_linkedin_enrich.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git -C /home/farzin/PROSPECTFORGE/lead-generator add src/linkedin_enrich.py tests/test_linkedin_enrich.py
git -C /home/farzin/PROSPECTFORGE/lead-generator commit -m "feat: add LinkedIn company page scraper for location count and contacts"
```

---

### Task 4: Post-Enrichment Quality Gate (Stage 4b)

**Files:**
- Modify: `src/pipeline.py`
- Create: `tests/test_quality_gate.py`

**Step 1: Write the failing tests**

Create `tests/test_quality_gate.py`:

```python
# tests/test_quality_gate.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline import Pipeline
from src.linkedin_enrich import LinkedInCompanyData, Contact


@pytest.mark.asyncio
async def test_filters_by_apollo_location_count():
    """Leads with apollo_location_count > max are filtered out."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Flaman Fitness",
            "apollo_location_count": 36,
            "employee_count": "",
            "linkedin_company": "https://linkedin.com/company/flaman-fitness",
            "location_count": 6,
        },
        {
            "brand_name": "Good Store",
            "apollo_location_count": 5,
            "employee_count": "",
            "linkedin_company": "",
            "location_count": 5,
        },
    ]

    result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["brand_name"] == "Good Store"


@pytest.mark.asyncio
async def test_filters_by_employee_count():
    """Leads with employee_count > max are filtered out when no location data."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Big Corp",
            "apollo_location_count": None,
            "employee_count": 1500,
            "linkedin_company": "",
            "location_count": 4,
        },
        {
            "brand_name": "Small Biz",
            "apollo_location_count": None,
            "employee_count": 30,
            "linkedin_company": "",
            "location_count": 4,
        },
    ]

    # No LinkedIn scraping since no linkedin_company URL for Big Corp
    result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["brand_name"] == "Small Biz"


@pytest.mark.asyncio
async def test_filters_by_linkedin_location_count():
    """When Apollo location is null, falls back to LinkedIn scrape."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Chain Store",
            "apollo_location_count": None,
            "employee_count": "",
            "linkedin_company": "https://linkedin.com/company/chain-store",
            "location_count": 7,
        },
    ]

    mock_linkedin_data = LinkedInCompanyData(
        location_count=25,
        employee_range="201-500",
        industry="Retail",
        people=[Contact(name="Boss Man", title="CEO", linkedin_url="https://linkedin.com/in/boss")],
    )

    with patch("src.pipeline.LinkedInEnricher") as mock_enricher_cls:
        mock_enricher = MagicMock()
        mock_enricher.scrape_company_page = AsyncMock(return_value=mock_linkedin_data)
        mock_enricher_cls.return_value = mock_enricher

        result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_linkedin_supplements_contacts():
    """LinkedIn people data fills empty contact slots."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Small Chain",
            "apollo_location_count": 5,
            "employee_count": 40,
            "linkedin_company": "https://linkedin.com/company/small-chain",
            "location_count": 5,
            "contact_1_name": "Existing Contact",
            "contact_1_title": "CEO",
            "contact_1_email": "ceo@small.com",
            "contact_1_phone": "555-1234",
            "contact_1_linkedin": "",
            "contact_2_name": "",
            "contact_2_title": "",
            "contact_2_email": "",
            "contact_2_phone": "",
            "contact_2_linkedin": "",
            "contact_3_name": "",
            "contact_3_title": "",
            "contact_3_email": "",
            "contact_3_phone": "",
            "contact_3_linkedin": "",
            "contact_4_name": "",
            "contact_4_title": "",
            "contact_4_email": "",
            "contact_4_phone": "",
            "contact_4_linkedin": "",
        },
    ]

    mock_linkedin_data = LinkedInCompanyData(
        location_count=5,
        employee_range="11-50",
        industry="Retail",
        people=[
            Contact(name="LI Person A", title="COO", linkedin_url="https://linkedin.com/in/a"),
            Contact(name="LI Person B", title="Director", linkedin_url="https://linkedin.com/in/b"),
        ],
    )

    with patch("src.pipeline.LinkedInEnricher") as mock_enricher_cls:
        mock_enricher = MagicMock()
        mock_enricher.scrape_company_page = AsyncMock(return_value=mock_linkedin_data)
        mock_enricher_cls.return_value = mock_enricher

        result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["contact_1_name"] == "Existing Contact"  # Not overwritten
    assert result[0]["contact_2_name"] == "LI Person A"
    assert result[0]["contact_3_name"] == "LI Person B"


@pytest.mark.asyncio
async def test_no_data_passes_through():
    """Leads with no Apollo or LinkedIn data pass through."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Unknown Store",
            "apollo_location_count": None,
            "employee_count": "",
            "linkedin_company": "",
            "location_count": 5,
        },
    ]

    result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["brand_name"] == "Unknown Store"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_quality_gate.py -v`
Expected: FAIL with AttributeError (stage_4b_quality_gate doesn't exist)

**Step 3: Implement stage_4b_quality_gate**

Add the import at the top of `src/pipeline.py`, alongside the existing imports:

```python
from src.linkedin_enrich import LinkedInEnricher, LinkedInCompanyData
```

Add this method to the `Pipeline` class in `src/pipeline.py`, after `stage_4_enrich` (and its sub-methods):

```python
    async def stage_4b_quality_gate(self, enriched: list[dict]) -> list[dict]:
        """Filter leads using Apollo/LinkedIn data and supplement contacts."""
        self._show_stage_header("4b", "Quality Gate", "Verifying chain sizes and supplementing contacts")

        if not enriched:
            console.print("  [yellow]⚠ No leads to verify[/yellow]")
            return []

        max_locations = settings.quality_gate_max_locations
        max_employees = settings.quality_gate_max_employees
        enricher = LinkedInEnricher(api_key=settings.firecrawl_api_key)

        console.print(f"  [dim]• Checking {len(enriched)} leads[/dim]")
        console.print(f"  [dim]• Max locations: {max_locations}, Max employees: {max_employees}[/dim]")
        console.print()

        passed = []
        filtered_count = 0

        for lead in enriched:
            brand_name = lead.get("brand_name", "Unknown")
            apollo_locs = lead.get("apollo_location_count")
            employee_count = lead.get("employee_count")
            linkedin_url = lead.get("linkedin_company", "")

            # Signal 1: Apollo retail_location_count
            if apollo_locs and isinstance(apollo_locs, (int, float)) and apollo_locs > max_locations:
                console.print(f"  [red]✗ Filtered:[/red] {brand_name} — Apollo says {int(apollo_locs)} locations")
                filtered_count += 1
                continue

            # Signal 2: LinkedIn company page (only if Apollo location count is null)
            linkedin_data = None
            if apollo_locs is None and linkedin_url:
                try:
                    linkedin_data = await enricher.scrape_company_page(linkedin_url)

                    if linkedin_data.location_count and linkedin_data.location_count > max_locations:
                        console.print(f"  [red]✗ Filtered:[/red] {brand_name} — LinkedIn says {linkedin_data.location_count} locations")
                        filtered_count += 1
                        continue
                except Exception:
                    pass  # LinkedIn scrape failed, continue with other signals

            # Signal 3: Employee count heuristic
            if apollo_locs is None and employee_count and isinstance(employee_count, (int, float)) and employee_count > max_employees:
                console.print(f"  [red]✗ Filtered:[/red] {brand_name} — {int(employee_count)} employees (likely large chain)")
                filtered_count += 1
                continue

            # Lead passed quality gate - supplement contacts from LinkedIn if available
            if linkedin_data and linkedin_data.people:
                # Find empty contact slots and fill them
                for i in range(1, 5):
                    if not lead.get(f"contact_{i}_name"):
                        # Find next LinkedIn person not already in contacts
                        existing_names = {lead.get(f"contact_{j}_name", "").lower() for j in range(1, 5)}
                        for person in linkedin_data.people:
                            if person.name.lower() not in existing_names:
                                lead[f"contact_{i}_name"] = person.name
                                lead[f"contact_{i}_title"] = person.title
                                lead[f"contact_{i}_linkedin"] = person.linkedin_url or ""
                                # Don't overwrite email/phone with empty values
                                if f"contact_{i}_email" not in lead:
                                    lead[f"contact_{i}_email"] = ""
                                if f"contact_{i}_phone" not in lead:
                                    lead[f"contact_{i}_phone"] = ""
                                existing_names.add(person.name.lower())
                                break

            passed.append(lead)
            console.print(f"  [green]✓ Passed:[/green] {brand_name}")

        # Summary
        console.print()
        table = Table(box=box.SIMPLE)
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Passed quality gate", f"[bold green]{len(passed)}[/bold green]")
        table.add_row("Filtered out", f"[bold red]{filtered_count}[/bold red]")
        console.print(table)

        return passed
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_quality_gate.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git -C /home/farzin/PROSPECTFORGE/lead-generator add src/pipeline.py tests/test_quality_gate.py
git -C /home/farzin/PROSPECTFORGE/lead-generator commit -m "feat: add post-enrichment quality gate stage 4b"
```

---

### Task 5: Wire New Stages into Pipeline.run() and Update Checkpoints

**Files:**
- Modify: `src/pipeline.py:811-943` (the `run` method)
- Modify: `tests/test_pipeline.py`

**Step 1: Update the integration test**

Replace the test `test_pipeline_runs_all_stages` in `tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    pipeline = Pipeline()

    mock_brand = BrandGroup(
        normalized_name="test store",
        original_names=["Test Store"],
        location_count=5,
        locations=[{"name": "Test Store", "address": "123 Main St"}],
        website="https://teststore.com",
        cities=["New York"],
    )

    mock_discovery_instance = MagicMock()
    mock_discovery_instance.run = AsyncMock(return_value=[{"name": "Test Store", "address": "123 Main St"}])

    with patch('src.pipeline.Discovery', return_value=mock_discovery_instance) as mock_discovery_cls, \
         patch.object(pipeline, 'stage_2_group', new_callable=MagicMock) as mock_group, \
         patch.object(pipeline, 'stage_2b_verify_chain_size', new_callable=MagicMock) as mock_verify, \
         patch.object(pipeline, 'stage_2c_website_health', new_callable=AsyncMock) as mock_health, \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock) as mock_ecom, \
         patch.object(pipeline, 'stage_4_enrich', new_callable=AsyncMock) as mock_enrich, \
         patch.object(pipeline, 'stage_4b_quality_gate', new_callable=AsyncMock) as mock_quality, \
         patch.object(pipeline, 'stage_5_score', new_callable=MagicMock) as mock_score, \
         patch.object(pipeline, 'stage_6_export', new_callable=MagicMock) as mock_export, \
         patch.object(pipeline, '_save_checkpoint', new_callable=MagicMock) as mock_save_cp, \
         patch.object(pipeline, 'clear_checkpoint', new_callable=MagicMock) as mock_clear_cp:

        mock_group.return_value = [mock_brand]
        mock_verify.return_value = [mock_brand]
        mock_health.return_value = [mock_brand]
        mock_ecom.return_value = [mock_brand]
        mock_enrich.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_quality.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_score.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com", "priority_score": 50}]
        mock_export.return_value = "output.csv"

        result = await pipeline.run(verticals=["apparel"], countries=["us"])

        mock_discovery_instance.run.assert_called_once()
        mock_group.assert_called_once()
        mock_verify.assert_called_once()
        mock_health.assert_called_once()
        mock_ecom.assert_called_once()
        mock_enrich.assert_called_once()
        mock_quality.assert_called_once()
        mock_score.assert_called_once()
        mock_export.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py::test_pipeline_runs_all_stages -v`
Expected: FAIL (mock_health and mock_quality not called because run() doesn't invoke them yet)

**Step 3: Wire new stages into Pipeline.run()**

Update the `Checkpoint` dataclass — add `healthy_brands` field after `verified_brands`:

```python
    healthy_brands: list[dict] = field(default_factory=list)
```

Update the `run()` method. Add this block after Stage 2b and before Stage 3:

```python
        # Stage 2c: Website health check
        if start_stage < 2.6:
            healthy_brands = await self.stage_2c_website_health(verified_brands)
            checkpoint.healthy_brands = [self._serialize_brand(b) for b in healthy_brands]
            checkpoint.stage = 2.6
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 2c complete)[/dim]")
        else:
            console.print(f"  [dim]⏭ Skipping Stage 2c (Health Check) - loaded {len(healthy_brands)} healthy brands from checkpoint[/dim]")
```

Change the Stage 3 e-commerce call to use `healthy_brands` instead of `verified_brands`:

```python
        # Stage 3: E-commerce check
        if start_stage < 3:
            ecommerce_brands = await self.stage_3_ecommerce(healthy_brands)
```

Add this block after Stage 4 and before Stage 5:

```python
        # Stage 4b: Quality gate
        if start_stage < 4.5:
            enriched = await self.stage_4b_quality_gate(enriched)
            checkpoint.enriched = enriched
            checkpoint.stage = 4.5
            self._save_checkpoint(checkpoint)
            console.print(f"  [dim]💾 Checkpoint saved (Stage 4b complete)[/dim]")
```

Update the checkpoint loading section near the top of `run()` to load `healthy_brands`:

```python
        healthy_brands = [self._deserialize_brand(b) for b in checkpoint.healthy_brands] if checkpoint and start_stage >= 2.6 else []
```

Update the `list_checkpoints` stage_names dict to include the new stages:

```python
            2.6: "Health Check",
            4.5: "Quality Gate",
```

**Step 4: Run all pipeline tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git -C /home/farzin/PROSPECTFORGE/lead-generator add src/pipeline.py tests/test_pipeline.py
git -C /home/farzin/PROSPECTFORGE/lead-generator commit -m "feat: wire stages 2c and 4b into pipeline with checkpoint support"
```

---

### Task 6: Update LinkedIn Enrichment Path to Use Direct Page Scrape

**Files:**
- Modify: `src/pipeline.py` (the `_enrich_with_linkedin` method)
- Test: existing tests still pass

**Step 1: Write a test for the improved LinkedIn enrichment path**

Add to `tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_linkedin_enrichment_uses_page_scrape():
    """LinkedIn enrichment path uses direct page scrape instead of Google searches."""
    pipeline = Pipeline()

    brands = [
        BrandGroup(
            normalized_name="test brand",
            original_names=["Test Brand"],
            location_count=5,
            locations=[{"name": "Test Brand", "address": "123 Main St"}],
            website="https://testbrand.com",
            cities=["Toronto"],
        )
    ]

    mock_company_data = MagicMock()
    mock_company_data.location_count = 5
    mock_company_data.employee_range = "11-50"
    mock_company_data.industry = "Retail"
    mock_company_data.people = [
        MagicMock(name="John CEO", title="CEO", linkedin_url="https://linkedin.com/in/john"),
        MagicMock(name="Jane COO", title="COO", linkedin_url="https://linkedin.com/in/jane"),
    ]

    with patch('src.pipeline.LinkedInEnricher') as mock_enricher_cls:
        mock_enricher = MagicMock()
        # Mock finding the company URL
        mock_enricher.find_company = AsyncMock(return_value="https://linkedin.com/company/test-brand")
        # Mock scraping the company page
        mock_enricher.scrape_company_page = AsyncMock(return_value=mock_company_data)
        mock_enricher_cls.return_value = mock_enricher

        result = await pipeline._enrich_with_linkedin(brands)

    assert len(result) == 1
    assert result[0]["contact_1_name"] == "John CEO"
    assert result[0]["contact_1_title"] == "CEO"
    # Verify scrape_company_page was called (not the old _search_people)
    mock_enricher.scrape_company_page.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py::test_linkedin_enrichment_uses_page_scrape -v`
Expected: FAIL

**Step 3: Update `_enrich_with_linkedin` in pipeline.py**

Replace the `_enrich_with_linkedin` method. Key changes:
- First find the LinkedIn company URL (keep existing `find_company` call)
- Then scrape the company page directly instead of using `_search_people`
- Extract contacts from the page scrape result

```python
    async def _enrich_with_linkedin(self, brands: list[BrandGroup]) -> list[dict]:
        """Enrich using LinkedIn page scraping."""
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

        console.print(f"  [dim]• Enriching {len(brands)} qualified leads via LinkedIn page scraping[/dim]")
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
                    # Step 1: Find LinkedIn company URL
                    linkedin_url = await enricher.find_company(brand.normalized_name, brand.website or "")

                    linkedin_data = None
                    contacts = []

                    if linkedin_url:
                        stats["linkedin_pages_found"] += 1

                        # Step 2: Scrape the company page directly
                        linkedin_data = await enricher.scrape_company_page(linkedin_url)
                        contacts = linkedin_data.people[:4] if linkedin_data.people else []

                    # Track contact stats
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

                    enriched.append(row)

                    if contacts:
                        progress.update(task, description=f"[green]✓[/green] {brand_name}: {len(contacts)} contacts")
                    else:
                        progress.update(task, description=f"[yellow]○[/yellow] {brand_name}: No data found")

                    await asyncio.sleep(1.0)
                except RuntimeError:
                    raise  # Re-raise credit exhaustion
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

**Step 4: Run all tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git -C /home/farzin/PROSPECTFORGE/lead-generator add src/pipeline.py tests/test_pipeline.py
git -C /home/farzin/PROSPECTFORGE/lead-generator commit -m "feat: update LinkedIn enrichment to use direct page scraping"
```

---

### Task 7: Final Integration Test and Cleanup

**Files:**
- All modified files
- Run full test suite

**Step 1: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest -v`
Expected: ALL PASS

**Step 2: Verify no import errors by running CLI help**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src --help`
Expected: CLI help output, no import errors

**Step 3: Commit any final fixes**

If any tests fail, fix and commit. Otherwise, this task is just verification.
