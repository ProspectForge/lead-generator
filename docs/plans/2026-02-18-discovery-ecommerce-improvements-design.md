# Discovery & E-commerce Detection Improvements

**Date:** 2026-02-18
**Status:** Approved

## Problem

Two quality gaps in the lead generation pipeline:

1. **Discovery geographic gaps** — Text search `"{query} in {city}"` biases toward city centers. Suburbs and surrounding metro areas are missed despite 905 cities in the config. The root cause is that Google Places text search doesn't cover the full metro radius.

2. **E-commerce false negatives** — Only 7 platforms detected (Shopify, WooCommerce, BigCommerce, Squarespace, Magento, Shopware, Prestashop). Many real e-commerce stores are missed because they use unrecognized platforms, render via JavaScript (SPAs), or have no platform-specific HTML signatures.

## Approach

**Nearby Search Grid + Platform Expansion + Playwright Fallback**

Quality is prioritized over API cost.

---

## Section 1: Discovery — Nearby Search Grid

Supplement existing text searches with nearby searches at grid points around each metro area.

### City coordinates

Add lat/lng to `cities.json` for each city. Auto-geocode using Google Geocoding API during first run, or one-time data entry.

### Grid generation

For each city, generate 5 search points:
- Center (the city itself)
- 4 cardinal offsets at ~20km (N, S, E, W)

This covers a ~40km diameter area per city, enough for most metro suburbs.

### Nearby search calls

At each grid point, run `nearby_search(lat, lng, radius=15000, includedTypes=[...])` using the existing method in `places_search.py`.

### Type mapping expansion

Expand `RETAIL_TYPES` from 4 verticals to all 11:

**Current:** sporting_goods, health_wellness, apparel, outdoor_camping

**Add:** pet_supplies, beauty_cosmetics, specialty_food, running_athletic, cycling, baby_kids, home_goods

### Integration

Add `_run_nearby_grid_search()` in `discovery.py` between the text search and scraping stages. Results merge into existing deduplication pipeline via `place_id` matching.

### Cost estimate

905 cities x 5 grid points x ~3 type groups = ~13,575 Nearby Search calls per run (vs current ~9,000 text search calls). Roughly 1.5x increase.

### Config

```json
"discovery": {
  "nearby_grid": {
    "enabled": true,
    "offset_km": 20,
    "radius_meters": 15000,
    "points": "cardinal"
  }
}
```

---

## Section 2: E-commerce Detection — Platform Expansion

### New platforms (8 additional, total 15)

| Platform | Detection Signatures |
|----------|---------------------|
| Wix Commerce | `wixsite.com`, `static.wixstatic.com`, `wix-ecommerce`, `_api/wix-ecommerce` |
| Ecwid | `ecwid.com`, `app.ecwid.com`, `Ecwid.Cart` |
| Volusion | `volusion.com`, `stor.vo.llnwd.net`, `/v/vspfiles/` |
| Shift4Shop (3dcart) | `shift4shop.com`, `3dcart.com`, `3dcartstores.com` |
| OpenCart | `opencart`, `route=product`, `route=checkout` |
| Salesforce Commerce | `demandware.net`, `demandware.static`, `dw/shop/v`, `sfcc` |
| SAP Commerce (Hybris) | `hybris`, `/yacceleratorstorefront/` |
| Snipcart | `snipcart.com`, `snipcart-add-item`, `class="snipcart-` |

### Enhanced detection signals

All detection runs on already-fetched content. No extra HTTP calls.

**HTTP response headers** (captured during existing `_fetch_page`):
- `X-Powered-By`: reveals Shopify, Magento, WooCommerce
- `Set-Cookie`: platform-specific cookie names (`_shopify_s`, WooCommerce patterns, `frontend` for Magento)
- `Server`: sometimes reveals platform
- `X-ShopId`, `X-Shopify-Stage`: Shopify-specific headers

**Meta tag patterns:**
- `<meta name="generator" content="WooCommerce">`
- `<meta name="platform" content="...">`
- `og:type` of `product` indicates product pages

**Script src patterns:**
- CDN URLs reveal platform (e.g., `cdn.shopify.com/s/files/`, `cdn.bigcommerce.com`)
- Cart/checkout JS files

**Structured data (JSON-LD):**
- Detect `"@type": "Product"` or `"@type": "Offer"` in `<script type="application/ld+json">` blocks
- Catches custom/headless stores with no platform signature

### Implementation

Modify `_fetch_page` to return response headers alongside HTML. Add detection methods for headers, meta tags, script src, and JSON-LD. All run against already-fetched content.

---

## Section 3: Playwright Fallback for JS-Rendered Stores

Targeted Playwright fallback for sites where static HTML looks like an empty SPA shell.

### Trigger conditions (ALL must be true)

1. Static HTML returned successfully (not a crawl failure)
2. No platform detected
3. No e-commerce indicators found (score = 0)
4. HTML contains JS framework markers (`__NEXT_DATA__`, `__NUXT__`, `id="app"`, `id="root"`, `bundle.js`, `React`, `Vue`)
5. HTML body has < 2KB of visible text but large total response size

### Flow

1. Static check returns "no e-commerce" for a site
2. Check trigger conditions
3. If triggered: launch headless Chromium, navigate to URL, wait for network idle
4. Extract rendered HTML, run same platform/indicator detection
5. Return Playwright result, merging with any partial static signals

### Scope control

- Max 20% of sites can go through Playwright fallback per run (configurable cap)
- Timeout: 15 seconds per page (homepage only, no additional page probing)
- Reuses existing Playwright dependency from `package.json`

### Config

```json
"ecommerce": {
  "concurrency": 5,
  "pages_to_check": 3,
  "playwright_fallback": {
    "enabled": true,
    "max_percent": 20,
    "timeout_seconds": 15
  }
}
```

---

## Section 4: Data Flow & Integration

### Pipeline flow

```
Discovery Stage 1 (existing)
  Text Search (current) ────── "{query} in {city}" x all cities x all verticals
  Nearby Grid Search (NEW) ─── nearby_search at 5 grid points x city x retail types
  Web Scraping (current) ───── BestOf scraper, sampled cities
  Brand Expansion (current) ── Expand multi-location brands
                    |
                    v
          Deduplication (existing)
                    |
                    v
E-commerce Detection Stage 3 (enhanced)
  Pass 1: Static HTTP (current + expanded)
    Fetch homepage + shop paths (existing)
    Platform signatures (7 -> 15 platforms)
    HTTP header detection (NEW)
    Meta tag / script src detection (NEW)
    JSON-LD structured data detection (NEW)
  Pass 2: Playwright fallback (NEW, conditional)
    Only for sites matching SPA trigger conditions
```

### Changes by file

| File | Changes |
|------|---------|
| `config/cities.json` | Add `discovery.nearby_grid` config, `ecommerce.playwright_fallback` config, expand city entries with lat/lng |
| `src/config.py` | Load new config sections, add `DiscoverySettings` dataclass |
| `src/places_search.py` | Add `RETAIL_TYPES` for all 11 verticals, add grid point generation helper |
| `src/discovery.py` | Add `_run_nearby_grid_search()` step between text search and scraping |
| `src/ecommerce_check.py` | Add 8 platform signatures, header/meta/JSON-LD detection, `_fetch_page` returns headers, Playwright fallback with trigger logic |

### No changes to

`pipeline.py` (stages stay the same), `brand_grouper.py`, enrichment, scoring, export.

### Testing

- Unit tests for new platform signatures (mock HTML for each new platform)
- Unit tests for header-based detection (mock response headers)
- Unit tests for JSON-LD detection
- Unit tests for Playwright trigger conditions (mock HTML that should/shouldn't trigger)
- Unit tests for grid point generation (verify offsets)
- Integration test for nearby search flow in discovery
