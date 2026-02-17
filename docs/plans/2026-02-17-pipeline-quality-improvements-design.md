# Pipeline Quality Improvements Design

**Date:** 2026-02-17
**Status:** Approved

## Problem

Two quality issues in the lead generation pipeline:

1. **Inaccurate location counts:** The pipeline counts locations by how many Google Places results appear in the ~120 searched cities. Brands with locations in smaller cities get undercounted. Example: Flaman Fitness has 36 locations but the pipeline only found 6, so it passes the 3-10 location filter and becomes a lead when it shouldn't.

2. **Dead/irrelevant websites:** 404 pages, expired domains, parked domains, and wrong-business websites waste Firecrawl API credits during e-commerce detection and pollute results.

## Approach: Post-Enrichment Quality Gate + Website Health Check

Use data already collected from Apollo enrichment (retail_location_count, employee_count) to filter out large chains after enrichment. Add LinkedIn company page scraping as a supplementary signal. Pre-filter dead websites before the expensive Firecrawl e-commerce crawl.

## Design

### 1. Website Health Check (Stage 2c)

New pipeline stage between chain size verification (2b) and e-commerce detection (3).

For each brand with a website, send an HTTP HEAD request (fall back to GET if HEAD is rejected). Mark a website as dead if:
- HTTP status 404, 410, or 5xx
- Connection refused / DNS resolution failure (domain expired)
- Final redirect lands on a known domain parking service (godaddy.com/parking, sedoparking.com, hugedomains.com, etc.)

Dead-website brands are removed from the pipeline before the Firecrawl crawl. Results logged to console.

Lives in `pipeline.py` as `stage_2c_website_health`. Runs in parallel with a semaphore. Zero API cost.

### 2. LinkedIn Company Page Scraping

New function in `linkedin_enrich.py` that scrapes a LinkedIn company page via Firecrawl and extracts:
- Location count
- Employee count range
- Industry
- List of people: name, title, LinkedIn profile URL

```
scrape_company_page(linkedin_url: str) -> LinkedInCompanyData
  - location_count: Optional[int]
  - employee_range: Optional[str]
  - industry: Optional[str]
  - people: list[{name, title, linkedin_url}]
```

Cost: 1 Firecrawl credit per call.

### 3. Post-Enrichment Quality Gate (Stage 4b)

New pipeline stage after enrichment (4) that filters leads using three signals, checked in order:

1. **Apollo retail_location_count** — if available and > max_locations (10), discard
2. **LinkedIn company page scrape** — if Apollo location count is null, scrape the LinkedIn company page. If locations > max_locations (10), discard
3. **Employee count heuristic** — if employee_count > max_employees (500), discard

The LinkedIn scrape only fires when Apollo's retail_location_count is null, keeping costs balanced.

### 4. LinkedIn Contact Supplementation

The LinkedIn company page scrape also extracts people data. This integrates with enrichment providers:

**Apollo path:** LinkedIn page scrape runs for leads where retail_location_count is null OR fewer than 4 contacts were found. LinkedIn contacts fill empty contact slots but don't replace Apollo's verified emails/phones.

**LinkedIn enrichment path:** The LinkedIn page scrape replaces the current Google search approach entirely. Instead of two Google searches via Firecrawl (one for company URL, one for people), one direct company page scrape provides better data — real names and titles instead of URL-slug guesses.

## Updated Pipeline Flow

```
Stage 1:  Discovery (unchanged)
Stage 2:  Brand Grouping (unchanged)
Stage 2b: Chain Size Verify (unchanged)
Stage 2c: Website Health Check (NEW)
Stage 3:  E-commerce Detection (unchanged, receives only healthy websites)
Stage 4:  Enrichment (Apollo or LinkedIn — LinkedIn path updated to use direct page scrape)
Stage 4b: Quality Gate (NEW)
Stage 5:  Scoring (unchanged)
Stage 6:  Export (unchanged)
```

## Files Changed

- `pipeline.py` — Add stage_2c_website_health, stage_4b_quality_gate, wire into run(), update checkpoint stages
- `linkedin_enrich.py` — Add scrape_company_page(), update LinkedIn enrichment path to use direct page scraping
- `config/cities.json` — Add quality_gate config (max_locations, max_employees) and health_check config (concurrency)

## Files Unchanged

- `brand_grouper.py`
- `ecommerce_check.py`
- `apollo_enrich.py`
- `discovery.py`
- `lead_scorer.py`

## Configuration

New config keys in cities.json:
```json
{
  "quality_gate": {
    "max_locations": 10,
    "max_employees": 500
  },
  "health_check": {
    "concurrency": 10
  }
}
```
