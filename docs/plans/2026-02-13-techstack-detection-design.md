# Tech Stack Detection & Lead Scoring Design

**Date:** 2026-02-13
**Status:** Approved

## Problem

We need to identify which leads use Lightspeed POS to prioritize outreach. Lightspeed users are ideal customers. Additionally, marketplace presence (Amazon, Etsy, etc.) indicates strong omnichannel operations.

## Solution

Extend the existing Apollo.io enrichment to extract technographics data. Apollo already tracks `technology_names` and `current_technologies` - we just need to parse them.

## Architecture

```
Pipeline Flow:

stage_3_ecommerce() → EcommerceChecker
         ↓
stage_4_enrich() → ApolloEnricher (UPDATED)
         ↓
stage_5_score() → LeadScorer (NEW)
         ↓
stage_6_export()
```

No new API integrations. No scraping. Extends existing Apollo integration.

## Changes Required

### 1. apollo_enrich.py

Add new fields to `ApolloCompany` dataclass:

```python
@dataclass
class ApolloCompany:
    # Existing fields...
    name: str
    domain: str
    industry: Optional[str]
    employee_count: Optional[int]
    estimated_revenue: Optional[str]
    linkedin_url: Optional[str]

    # NEW fields
    technology_names: list[str]           # ["Lightspeed", "Shopify", "Stripe"]
    retail_location_count: Optional[int]  # Apollo's location count
```

Extract from Apollo response:
- `org.get("technology_names", [])`
- `org.get("retail_location_count")`

### 2. lead_scorer.py (NEW)

```python
POS_PLATFORMS = ["Lightspeed", "Shopify POS", "Square", "Clover", "Toast", "Revel"]
MARKETPLACES = ["Amazon", "eBay", "Etsy", "Walmart Marketplace", "Google Shopping"]
```

**Scoring weights:**

| Signal | Points |
|--------|--------|
| Uses Lightspeed | +30 |
| Has marketplaces | +15 |
| Multiple marketplaces (2+) | +10 |
| 3-5 locations | +15 |
| 6-10 locations | +10 |
| Has e-commerce | +10 |
| Has verified contacts | +10 |

Match Lightspeed case-insensitively, including variants ("Lightspeed POS", "Lightspeed Retail").

### 3. pipeline.py

- Add `stage_5_score()` between enrichment and export
- Rename current `stage_5_export()` to `stage_6_export()`
- Sort output by `priority_score` descending

### 4. Output CSV

New columns:

| Column | Example |
|--------|---------|
| `pos_platform` | "Lightspeed" |
| `marketplaces` | "Amazon, Etsy" |
| `tech_stack` | "Lightspeed, Shopify, Stripe, Klaviyo" |
| `priority_score` | 80 |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Apollo has no tech data | Empty fields, score based on other signals |
| Lightspeed variant naming | Match any string containing "Lightspeed" |
| Apollo rate limit | Existing retry logic handles this |
| Company not found | Keep lead with empty enrichment, low score |

No data does not exclude a lead. Leads without tech data still appear, just scored lower.

## Testing

1. Run existing tests: `pytest tests/ -v`
2. Add tests for `lead_scorer.py`
3. Manual test: run pipeline on 10-20 leads, verify tech stack extraction
