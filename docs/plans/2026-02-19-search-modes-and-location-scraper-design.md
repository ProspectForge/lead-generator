# Search Modes & Website Location Scraper

**Date:** 2026-02-19
**Status:** Approved

## Problem

The pipeline has 1000 SerpAPI searches but the current config would burn ~70,000. Brand expansion alone costs ~17,400 searches (20 brands x 870 cities via SerpAPI). There is no way to run a budget-friendly discovery pass vs a full sweep.

## Solution

Two changes:
1. **Lean / Extended search modes** — lean uses ~50 curated cities + 3-4 queries per vertical; extended uses all cities + full query lists.
2. **Website location scraper** — replaces SerpAPI-based brand expansion. Scrapes the brand's own website for store locator pages. Zero SerpAPI cost. No fallback to SerpAPI.
3. **90-day cache TTL** on all caches (SerpAPI + location scraper). Cache-first everywhere.

## Search Modes

| | Lean | Extended |
|---|---|---|
| Cities | ~50 US + ~15 CA curated metros | All 782 US + 110 CA |
| Queries | 3-4 per vertical (`lean_queries`) | Full list (15-20) |
| Grid search | Disabled | Enabled |
| Brand expansion | Website scrape only | Website scrape only |
| Est. searches (2 verticals) | ~350 | ~45,000+ |

### Lean city selection criteria
Mid-tier metros (250k-1.5M pop) where regional chains cluster. Avoid megacities dominated by national chains and tiny towns with few retailers. Include a handful of large metros (Chicago, Houston, etc.) that still have strong regional presence.

### Lean query selection
3-4 highest-signal queries per vertical. E.g. for health_wellness: "supplement store", "health food store", "sports nutrition store" covers 90%+ of what the full 20-query list finds, since Google Maps returns overlapping results for synonyms.

## Website Location Scraper

New `src/location_scraper.py`:

1. **URL discovery**: Check common paths (`/locations`, `/stores`, `/store-locator`, `/find-a-store`, `/our-stores`, `/store-finder`). Also parse homepage nav links for location-related hrefs.
2. **Content parsing**: Extract addresses from:
   - JSON-LD `LocalBusiness` / `Store` structured data
   - Schema.org microdata
   - Plain HTML address patterns (street, city, state, zip)
3. **Cache**: `data/location_cache/{domain_hash}.json`, 90-day TTL, checked before any network request.
4. **Return**: List of `{name, address, city, state}` or empty list on failure. No SerpAPI fallback.

## Caching

- SerpAPI cache TTL: 30 days -> 90 days
- Location scraper cache: new, 90-day TTL, `data/location_cache/`
- Both: cache-first, only network on miss/expiry

## Config Changes

`config/cities.json` additions:
- `search.mode`: `"lean"` or `"extended"` (default: `"lean"`)
- `lean_cities.us`: curated list of ~50 US metros
- `lean_cities.canada`: curated list of ~15 CA metros
- Per-vertical `lean_queries` sublists within `search_queries`

`src/config.py` additions:
- `Settings.search_mode: str` field
- `Settings.lean_cities: dict` field
- `Settings.lean_queries: dict` field

## Integration

- `discovery.py`: reads `search_mode`, picks city list + query list + grid enabled accordingly. Brand expansion calls `LocationScraper` instead of SerpAPI.
- `brand_expander.py`: rewritten to use `LocationScraper`. No SerpAPI dependency.
- `__main__.py`: new interactive step + `--mode lean|extended` CLI flag. `show_summary()` displays mode + estimated API calls.
- `pipeline.run()`: accepts `search_mode` parameter, passes through to Discovery.

## What stays the same

All downstream stages: grouping, chain verification, health check, e-commerce detection, enrichment, quality gate, scoring, export. Checkpoint and cache systems (except TTL bump).
