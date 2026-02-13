# Apollo.io Enrichment Integration Design

**Date:** 2026-02-13
**Status:** Approved
**Problem:** LinkedIn enrichment produces irrelevant contacts (names with hash IDs, no real titles, people who don't work at the company)

## Solution

Replace the Google-scraping LinkedIn enricher with Apollo.io API integration. The `apollo_enrich.py` module already exists and is well-tested.

## Architecture

```
Current flow:
  stage_4_linkedin() → LinkedInEnricher → Google scraping → garbage contacts

New flow:
  stage_4_enrich() → ApolloEnricher → Apollo API → verified contacts
```

## Changes Required

### 1. pipeline.py
- Replace `LinkedInEnricher` import with `ApolloEnricher`
- Update `stage_4_linkedin()` to use Apollo
- Rename method to `stage_4_enrich()` for clarity
- Add new output columns: email, phone, employee_count, industry

### 2. config.py
- Add `apollo_api_key` to Settings class
- Load from `APOLLO_API_KEY` environment variable

### 3. .env.example
- Add `APOLLO_API_KEY=` placeholder

## Output Format

**New CSV columns:**
```
brand_name, location_count, website, has_ecommerce, marketplaces, priority, cities,
linkedin_company, employee_count, industry,
contact_1_name, contact_1_title, contact_1_email, contact_1_phone, contact_1_linkedin,
contact_2_name, contact_2_title, contact_2_email, contact_2_phone, contact_2_linkedin,
contact_3_name, contact_3_title, contact_3_email, contact_3_phone, contact_3_linkedin,
contact_4_name, contact_4_title, contact_4_email, contact_4_phone, contact_4_linkedin
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Company not found | Output row with empty enrichment fields |
| No contacts found | Output company data, empty contact fields |
| API rate limit | Retry with exponential backoff (built-in) |
| Credits exhausted | Stop enrichment, export partial data, warn user |

No fallback to LinkedIn scraper - prefer empty fields over garbage data.

## Apollo.io Setup

1. Sign up at https://app.apollo.io/
2. Get API key from Settings → Integrations → API
3. Add to `.env`: `APOLLO_API_KEY=your_key_here`

Free tier: 10,000 credits/month (~2,500 leads with full enrichment)

## Testing

1. Run existing tests: `pytest tests/test_pipeline.py -v`
2. Manual test with 5-10 leads
3. Compare output quality vs previous CSV
