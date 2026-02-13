# Marketplace Detection Design

**Date:** 2026-02-12
**Status:** Approved
**Project:** PROSPECTFORGE Lead Generator

---

## Overview

Add marketplace detection to the lead generator pipeline as a priority signal for qualifying omnichannel retailer leads.

**Goal:** Identify brands that sell on Amazon, eBay, Walmart, or Etsy - these are higher-priority leads for RASAI's inventory automation services.

---

## Business Context

RASAI's ideal customer:
- Omnichannel retailer using Lightspeed Retail (POS)
- 2-10 physical locations + online presence
- 500+ SKUs with inventory complexity

Marketplace sellers have MORE inventory complexity (stores + warehouse + marketplace fulfillment), making them higher-value leads.

**Qualification logic:**
| Lead Type | Qualified? | Priority |
|-----------|------------|----------|
| Marketplace sellers (Amazon/eBay/etc.) | Yes | High |
| E-commerce only (Shopify/own site) | Yes | Medium |
| Physical stores only | No | - |

---

## Pipeline Integration

**Current pipeline:**
```
Stage 1: Google Places Search
Stage 2: Brand Grouping (filter to 3-10 locations)
Stage 2b: Chain Verification (filter out large chains)
Stage 3: E-commerce Check
Stage 4: LinkedIn Enrichment
Stage 5: Export
```

**Change:** Extend Stage 3 to detect both:
1. E-commerce presence (existing) - required to qualify
2. Marketplace presence (new) - priority signal

**No new stages added** - marketplace detection happens during existing website scan.

---

## Detection Method

During the existing Firecrawl website scan, detect marketplace presence via:

### 1. Link Scanning
Check page content for marketplace URLs:
```
amazon.com/stores/*
amazon.com/sp?seller=*
amazon.ca/stores/*
ebay.com/str/*
ebay.com/usr/*
walmart.com/seller/*
etsy.com/shop/*
```

### 2. Badge/Text Detection
Look for keywords and phrases:
```
"Shop on Amazon"
"Find us on eBay"
"Available on Walmart"
"Amazon Prime"
"eBay Store"
"Our Amazon Store"
"Buy on Amazon"
```

### 3. Footer/Social Links
Marketplaces often listed alongside social media icons in footer.

### Marketplaces to Detect
| Marketplace | Priority | Notes |
|-------------|----------|-------|
| Amazon | High | Biggest marketplace, FBA complexity |
| eBay | High | Common for retail brands |
| Walmart | Medium | Growing marketplace |
| Etsy | Low | More niche/handmade focus |

---

## Data Model Changes

### EcommerceResult (updated)

```python
@dataclass
class EcommerceResult:
    has_ecommerce: bool              # Required to qualify
    marketplaces: list[str]          # ["amazon", "ebay"] - empty if none
    marketplace_links: dict[str, str] # {"amazon": "https://..."} - optional
    priority: str                    # "high" (has marketplace) or "medium" (e-commerce only)
```

### CSV Output (new columns)

| Column | Type | Example |
|--------|------|---------|
| `marketplaces` | string | "amazon, ebay" |
| `priority` | string | "high" or "medium" |

### Final CSV Structure

```
brand_name, locations, has_ecommerce, marketplaces, priority, website, linkedin_company, contact_1_name, ...
```

Output sorted by priority (high first).

---

## File Changes

| File | Change |
|------|--------|
| `src/ecommerce_check.py` | Add marketplace detection logic, update EcommerceResult dataclass |
| `src/pipeline.py` | Capture marketplace data in Stage 3, pass through to export, add priority sorting |
| `config/cities.json` | (Optional) Add marketplace URL patterns as config |

**No new dependencies** - uses existing Firecrawl infrastructure.

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Website has Amazon link but broken | Still flag as marketplace (validation separate concern) |
| Multiple marketplaces detected | List all, single "high" priority |
| No marketplaces but has e-commerce | Pass through as "medium" priority |
| Marketplace link in image only | Miss it - text detection catches most cases |
| Foreign marketplace (amazon.ca, amazon.co.uk) | Detect as "amazon" - same seller |
| Detection fails entirely | Graceful degradation - lead passes with e-commerce status only |

---

## Success Criteria

1. Pipeline detects Amazon/eBay/Walmart/Etsy presence from website scans
2. Leads with marketplace presence marked as "high" priority
3. Leads with e-commerce only marked as "medium" priority
4. Final CSV sorted by priority
5. No additional API costs (uses existing Firecrawl)

---

## Out of Scope

- Verifying marketplace links are valid/active
- Detecting FBA vs FBM specifically
- Scraping marketplace pages directly
- Lightspeed detection (future feature)
