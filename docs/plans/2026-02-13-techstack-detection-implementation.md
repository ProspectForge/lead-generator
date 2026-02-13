# Tech Stack Detection & Lead Scoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend Apollo enrichment to extract technographics (POS platforms, marketplaces) and auto-score leads based on Lightspeed usage and other signals.

**Architecture:** Add `technology_names` and `retail_location_count` extraction to existing Apollo enrichment, create a new LeadScorer module that calculates priority scores, integrate scoring into pipeline before export.

**Tech Stack:** Python 3.12, pytest, existing Apollo.io integration

---

## Task 1: Extend Apollo Data Model for Technographics

**Files:**
- Modify: `src/apollo_enrich.py`
- Modify: `tests/test_apollo_enrich.py`

**Step 1: Write the failing test**

Add to `tests/test_apollo_enrich.py`:

```python
@pytest.fixture
def mock_company_response_with_tech():
    return {
        "organization": {
            "name": "Fleet Feet",
            "primary_domain": "fleetfeet.com",
            "industry": "Retail",
            "estimated_num_employees": 500,
            "annual_revenue_printed": "$50M-$100M",
            "linkedin_url": "https://linkedin.com/company/fleet-feet",
            "technology_names": ["Lightspeed", "Shopify", "Klaviyo", "Amazon"],
            "retail_location_count": 7,
        }
    }


@pytest.mark.asyncio
async def test_search_company_extracts_technographics(mock_company_response_with_tech):
    enricher = ApolloEnricher(api_key="test_key")

    with patch.object(enricher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_company_response_with_tech

        company = await enricher.search_company("Fleet Feet", "https://fleetfeet.com")

        assert company is not None
        assert company.technology_names == ["Lightspeed", "Shopify", "Klaviyo", "Amazon"]
        assert company.retail_location_count == 7


@pytest.mark.asyncio
async def test_search_company_handles_missing_tech_data(mock_company_response):
    enricher = ApolloEnricher(api_key="test_key")

    with patch.object(enricher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_company_response

        company = await enricher.search_company("Fleet Feet", "https://fleetfeet.com")

        assert company is not None
        assert company.technology_names == []
        assert company.retail_location_count is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_apollo_enrich.py::test_search_company_extracts_technographics -v`
Expected: FAIL with "AttributeError: 'ApolloCompany' object has no attribute 'technology_names'"

**Step 3: Write minimal implementation**

Update `src/apollo_enrich.py`:

Change the `ApolloCompany` dataclass (around line 31-38):

```python
@dataclass
class ApolloCompany:
    name: str
    domain: str
    industry: Optional[str]
    employee_count: Optional[int]
    estimated_revenue: Optional[str]
    linkedin_url: Optional[str]
    technology_names: list[str] = field(default_factory=list)
    retail_location_count: Optional[int] = None
```

Add import at top:
```python
from dataclasses import dataclass, field
```

Update `search_company` method (around line 120-130) to extract the new fields:

```python
return ApolloCompany(
    name=org.get("name", company_name),
    domain=org.get("primary_domain", domain),
    industry=org.get("industry"),
    employee_count=org.get("estimated_num_employees"),
    estimated_revenue=org.get("annual_revenue_printed"),
    linkedin_url=org.get("linkedin_url"),
    technology_names=org.get("technology_names", []),
    retail_location_count=org.get("retail_location_count"),
)
```

Also update the fallback ApolloCompany in `enrich` method (around line 190-197):

```python
company = ApolloCompany(
    name=company_name,
    domain=domain,
    industry=None,
    employee_count=None,
    estimated_revenue=None,
    linkedin_url=None,
    technology_names=[],
    retail_location_count=None,
)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_apollo_enrich.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/apollo_enrich.py tests/test_apollo_enrich.py
git commit -m "feat: extract technographics from Apollo enrichment"
```

---

## Task 2: Create Lead Scorer Module

**Files:**
- Create: `src/lead_scorer.py`
- Create: `tests/test_lead_scorer.py`

**Step 1: Write the failing test**

Create `tests/test_lead_scorer.py`:

```python
# tests/test_lead_scorer.py
import pytest
from src.lead_scorer import LeadScorer, ScoredLead


@pytest.fixture
def lightspeed_lead():
    return {
        "brand_name": "Fleet Feet",
        "location_count": 5,
        "has_ecommerce": True,
        "marketplaces": "Amazon, Etsy",
        "technology_names": ["Lightspeed", "Klaviyo", "Stripe"],
        "contact_1_name": "John Smith",
    }


@pytest.fixture
def non_lightspeed_lead():
    return {
        "brand_name": "Local Sports",
        "location_count": 4,
        "has_ecommerce": True,
        "marketplaces": "",
        "technology_names": ["Square", "Mailchimp"],
        "contact_1_name": "Jane Doe",
    }


@pytest.fixture
def no_tech_data_lead():
    return {
        "brand_name": "Unknown Store",
        "location_count": 3,
        "has_ecommerce": True,
        "marketplaces": "",
        "technology_names": [],
        "contact_1_name": "",
    }


def test_scores_lightspeed_highest(lightspeed_lead):
    scorer = LeadScorer()
    result = scorer.score(lightspeed_lead)

    assert result.uses_lightspeed is True
    assert result.priority_score >= 70  # High score for Lightspeed + marketplaces + contacts


def test_extracts_pos_platform(lightspeed_lead, non_lightspeed_lead):
    scorer = LeadScorer()

    result1 = scorer.score(lightspeed_lead)
    assert result1.pos_platform == "Lightspeed"

    result2 = scorer.score(non_lightspeed_lead)
    assert result2.pos_platform == "Square"


def test_extracts_marketplaces(lightspeed_lead):
    scorer = LeadScorer()
    result = scorer.score(lightspeed_lead)

    assert "Amazon" in result.detected_marketplaces
    assert "Etsy" in result.detected_marketplaces


def test_handles_missing_tech_data(no_tech_data_lead):
    scorer = LeadScorer()
    result = scorer.score(no_tech_data_lead)

    assert result.pos_platform is None
    assert result.uses_lightspeed is False
    assert result.priority_score < 50  # Low score without tech signals


def test_location_count_affects_score():
    scorer = LeadScorer()

    lead_5_locations = {"location_count": 5, "technology_names": [], "marketplaces": "", "has_ecommerce": True, "contact_1_name": ""}
    lead_8_locations = {"location_count": 8, "technology_names": [], "marketplaces": "", "has_ecommerce": True, "contact_1_name": ""}

    score_5 = scorer.score(lead_5_locations)
    score_8 = scorer.score(lead_8_locations)

    # 3-5 locations scores higher than 6-10
    assert score_5.priority_score > score_8.priority_score


def test_multiple_marketplaces_bonus():
    scorer = LeadScorer()

    lead_one_mp = {"location_count": 5, "technology_names": [], "marketplaces": "Amazon", "has_ecommerce": True, "contact_1_name": ""}
    lead_two_mp = {"location_count": 5, "technology_names": [], "marketplaces": "Amazon, Etsy", "has_ecommerce": True, "contact_1_name": ""}

    score_one = scorer.score(lead_one_mp)
    score_two = scorer.score(lead_two_mp)

    assert score_two.priority_score > score_one.priority_score
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_lead_scorer.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.lead_scorer'"

**Step 3: Write minimal implementation**

Create `src/lead_scorer.py`:

```python
# src/lead_scorer.py
"""
Lead scoring module based on tech stack and other signals.

Scoring weights:
- Uses Lightspeed: +30
- Has marketplaces: +15
- Multiple marketplaces (2+): +10
- 3-5 locations: +15
- 6-10 locations: +10
- Has e-commerce: +10
- Has verified contacts: +10
"""
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class ScoredLead:
    """Result of scoring a lead."""
    pos_platform: Optional[str]
    detected_marketplaces: list[str]
    tech_stack: list[str]
    uses_lightspeed: bool
    priority_score: int


class LeadScorer:
    """Scores leads based on tech stack and other signals."""

    POS_PLATFORMS = [
        "Lightspeed",
        "Shopify POS",
        "Square",
        "Clover",
        "Toast",
        "Revel",
        "Vend",
        "Heartland",
    ]

    MARKETPLACES = [
        "Amazon",
        "eBay",
        "Etsy",
        "Walmart",
        "Google Shopping",
        "Facebook Shop",
        "Instagram Shop",
    ]

    # Scoring weights
    SCORE_LIGHTSPEED = 30
    SCORE_HAS_MARKETPLACES = 15
    SCORE_MULTIPLE_MARKETPLACES = 10
    SCORE_LOCATIONS_3_5 = 15
    SCORE_LOCATIONS_6_10 = 10
    SCORE_HAS_ECOMMERCE = 10
    SCORE_HAS_CONTACTS = 10

    def _detect_pos_platform(self, technology_names: list[str]) -> Optional[str]:
        """Detect POS platform from technology list."""
        for tech in technology_names:
            for pos in self.POS_PLATFORMS:
                # Case-insensitive match, also handles "Lightspeed POS", "Lightspeed Retail"
                if pos.lower() in tech.lower() or tech.lower() in pos.lower():
                    return pos
        return None

    def _detect_marketplaces(self, technology_names: list[str], marketplace_str: str) -> list[str]:
        """Detect marketplaces from technology list and existing marketplace string."""
        detected = set()

        # Check technology_names
        for tech in technology_names:
            for mp in self.MARKETPLACES:
                if mp.lower() in tech.lower():
                    detected.add(mp)

        # Parse existing marketplace string (comma-separated)
        if marketplace_str:
            for mp_part in marketplace_str.split(","):
                mp_part = mp_part.strip()
                for mp in self.MARKETPLACES:
                    if mp.lower() in mp_part.lower():
                        detected.add(mp)

        return list(detected)

    def _uses_lightspeed(self, technology_names: list[str], pos_platform: Optional[str]) -> bool:
        """Check if lead uses Lightspeed."""
        if pos_platform and "lightspeed" in pos_platform.lower():
            return True
        for tech in technology_names:
            if "lightspeed" in tech.lower():
                return True
        return False

    def score(self, lead: dict) -> ScoredLead:
        """Score a lead based on tech stack and other signals."""
        technology_names = lead.get("technology_names", [])
        marketplace_str = lead.get("marketplaces", "")
        location_count = lead.get("location_count", 0)
        has_ecommerce = lead.get("has_ecommerce", False)
        has_contacts = bool(lead.get("contact_1_name", ""))

        # Detect platforms and marketplaces
        pos_platform = self._detect_pos_platform(technology_names)
        detected_marketplaces = self._detect_marketplaces(technology_names, marketplace_str)
        uses_lightspeed = self._uses_lightspeed(technology_names, pos_platform)

        # Calculate score
        score = 0

        if uses_lightspeed:
            score += self.SCORE_LIGHTSPEED

        if detected_marketplaces:
            score += self.SCORE_HAS_MARKETPLACES
            if len(detected_marketplaces) >= 2:
                score += self.SCORE_MULTIPLE_MARKETPLACES

        if 3 <= location_count <= 5:
            score += self.SCORE_LOCATIONS_3_5
        elif 6 <= location_count <= 10:
            score += self.SCORE_LOCATIONS_6_10

        if has_ecommerce:
            score += self.SCORE_HAS_ECOMMERCE

        if has_contacts:
            score += self.SCORE_HAS_CONTACTS

        return ScoredLead(
            pos_platform=pos_platform,
            detected_marketplaces=detected_marketplaces,
            tech_stack=technology_names,
            uses_lightspeed=uses_lightspeed,
            priority_score=score,
        )

    def score_leads(self, leads: list[dict]) -> list[dict]:
        """Score multiple leads and add scoring fields to each."""
        scored_leads = []

        for lead in leads:
            result = self.score(lead)

            # Add scoring fields to lead
            lead_copy = lead.copy()
            lead_copy["pos_platform"] = result.pos_platform or ""
            lead_copy["detected_marketplaces"] = ", ".join(result.detected_marketplaces)
            lead_copy["tech_stack"] = ", ".join(result.tech_stack)
            lead_copy["uses_lightspeed"] = result.uses_lightspeed
            lead_copy["priority_score"] = result.priority_score

            scored_leads.append(lead_copy)

        # Sort by priority_score descending
        scored_leads.sort(key=lambda x: x["priority_score"], reverse=True)

        return scored_leads
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_lead_scorer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/lead_scorer.py tests/test_lead_scorer.py
git commit -m "feat: add lead scorer module with Lightspeed detection"
```

---

## Task 3: Integrate Scorer into Pipeline

**Files:**
- Modify: `src/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_includes_scoring_stage():
    """Test that pipeline adds tech stack scoring to enriched leads."""
    pipeline = Pipeline()

    # Mock enriched data with technology_names
    mock_enriched = [
        {
            "brand_name": "Fleet Feet",
            "location_count": 5,
            "has_ecommerce": True,
            "marketplaces": "Amazon",
            "technology_names": ["Lightspeed", "Klaviyo"],
            "contact_1_name": "John Smith",
        },
        {
            "brand_name": "Local Sports",
            "location_count": 4,
            "has_ecommerce": True,
            "marketplaces": "",
            "technology_names": ["Square"],
            "contact_1_name": "Jane Doe",
        },
    ]

    scored = pipeline.stage_5_score(mock_enriched)

    # Check scoring fields added
    assert "priority_score" in scored[0]
    assert "pos_platform" in scored[0]
    assert "uses_lightspeed" in scored[0]

    # Lightspeed lead should be first (highest score)
    assert scored[0]["brand_name"] == "Fleet Feet"
    assert scored[0]["uses_lightspeed"] is True
    assert scored[0]["priority_score"] > scored[1]["priority_score"]
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py::test_pipeline_includes_scoring_stage -v`
Expected: FAIL with "AttributeError: 'Pipeline' object has no attribute 'stage_5_score'"

**Step 3: Write minimal implementation**

Update `src/pipeline.py`:

Add import at top (around line 20):
```python
from src.lead_scorer import LeadScorer
```

Add the scoring stage method (after `stage_4_enrich`, around line 680):

```python
def stage_5_score(self, enriched: list[dict]) -> list[dict]:
    """Score leads based on tech stack and other signals."""
    self._show_stage_header(5, "Lead Scoring", "Calculating priority scores based on tech stack")

    if not enriched:
        console.print("  [yellow]No leads to score[/yellow]")
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
```

Rename existing `stage_5_export` to `stage_6_export` (around line 683):
```python
def stage_6_export(self, data: list[dict]) -> str:
    """Export to CSV."""
    self._show_stage_header(6, "Export", "Saving leads to CSV")
    # ... rest unchanged
```

Update the `run` method (around line 830-860) to add scoring stage:

After stage 4 enrichment and before export, add:
```python
# Stage 5: Score leads
scored = self.stage_5_score(enriched)

# Stage 6: Export
output_file = self.stage_6_export(scored)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/pipeline.py tests/test_pipeline.py
git commit -m "feat: integrate lead scoring into pipeline"
```

---

## Task 4: Pass Technology Names Through Pipeline

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Update `_enrich_with_apollo` to include technology_names**

In `_enrich_with_apollo` method (around line 500-538), update the row dict to include technology data:

```python
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
    "technology_names": result.company.technology_names,  # NEW
    "apollo_location_count": result.company.retail_location_count,  # NEW
}
```

**Step 2: Run all tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/pipeline.py
git commit -m "feat: pass technology_names through pipeline enrichment"
```

---

## Task 5: Update Export Column Order

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Update `stage_6_export` to order columns correctly**

In `stage_6_export` (previously `stage_5_export`), add column ordering before CSV export:

```python
def stage_6_export(self, data: list[dict]) -> str:
    """Export to CSV."""
    self._show_stage_header(6, "Export", "Saving leads to CSV")

    if not data:
        console.print("  [yellow]No data to export[/yellow]")
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

    # ... rest of summary code unchanged
```

**Step 2: Run all tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/pipeline.py
git commit -m "feat: order CSV columns with priority_score first"
```

---

## Task 6: Final Integration Test

**Step 1: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 2: Manual sanity check (optional)**

If you have Apollo API key configured, test with a small run:
```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
python -m src --verticals apparel --countries us --dry-run
```

**Step 3: Final commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add -A
git status
# If any uncommitted changes:
git commit -m "chore: cleanup after tech stack detection implementation"
```

---

## Summary

| Task | Component | Purpose |
|------|-----------|---------|
| 1 | apollo_enrich.py | Add technology_names, retail_location_count extraction |
| 2 | lead_scorer.py | NEW - Score leads based on Lightspeed, marketplaces, etc. |
| 3 | pipeline.py | Add stage_5_score between enrichment and export |
| 4 | pipeline.py | Pass technology_names through _enrich_with_apollo |
| 5 | pipeline.py | Reorder CSV columns with priority_score first |
| 6 | tests/ | Final integration test |

**Expected output after implementation:**

CSV columns:
```
priority_score, uses_lightspeed, pos_platform, brand_name, location_count, ...
```

Lightspeed users will have:
- `uses_lightspeed = True`
- `pos_platform = "Lightspeed"`
- `priority_score >= 70` (typically)
