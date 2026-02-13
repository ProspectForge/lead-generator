# Enhanced Discovery Phase Design

**Date**: 2026-02-13
**Goal**: Increase lead discovery from ~170 to 700-1,000 qualified leads
**Approach**: Hybrid — Enhanced Google Places + Targeted Web Scraping + Brand Expansion

---

## Problem

Current discovery phase only returns ~170 leads:
- Google Places returns max 20 results per query
- Generic queries miss niche specialty retailers
- No brand expansion (finding all locations of discovered brands)
- Limited to text search (no radius-based nearby search)

## Architecture

Three-stage funnel for discovery:

```
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 1: DISCOVERY                           │
├─────────────────────┬─────────────────────┬─────────────────────┤
│  Google Places      │  Web Scraping       │  Brand Expansion    │
│  (Enhanced)         │  (Targeted)         │  (Follow-up)        │
│                     │                     │                     │
│  • Niche queries    │  • Franchise dirs   │  • Take brand names │
│  • Nearby Search    │  • Industry assocs  │  • Search all cities│
│  • More cities      │  • Local "best of"  │  • Find all locations│
└─────────┬───────────┴─────────┬───────────┴──────────┬──────────┘
          │                     │                      │
          ▼                     ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 2: DEDUPLICATION                       │
│                                                                 │
│  • Normalize brand names                                        │
│  • Match by website domain                                      │
│  • Merge location data from all sources                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STAGE 3: EXISTING PIPELINE                   │
│                                                                 │
│  Brand Grouper → E-commerce Check → LinkedIn Enrich → Export    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component 1: Enhanced Google Places Strategy

### 1a. Niche Query Expansion

Expand from 4 generic queries per vertical to 15-20 specific queries:

| Current | Expanded |
|---------|----------|
| "sporting goods store" | "running shoe store", "golf shop", "tennis pro shop", "ski equipment", "hockey store", "soccer store", "fishing tackle shop", "archery store", "climbing gear", "surf shop" |
| "outdoor gear store" | "camping supply", "hiking gear", "backpacking store", "kayak shop", "canoe outfitter" |
| "clothing boutique" | "yoga apparel", "activewear store", "athleisure boutique", "workwear store", "denim shop" |

### 1b. Nearby Search API

Add radius-based searches around city centers:

```
For each city:
  1. Text Search (current) → max 20 results
  2. Nearby Search (5km radius) → max 20 results
  3. Nearby Search (15km radius) → max 20 results
```

### 1c. City Expansion

Add ~48 more cities focusing on affluent suburbs:

**US additions**: Scottsdale AZ, Boulder CO, Naperville IL, Plano TX, Bellevue WA, Santa Monica CA, Greenwich CT, Westchester NY, etc.

**Canada additions**:
- Metro Vancouver: Coquitlam BC, Port Coquitlam BC, Burnaby BC, Surrey BC, Richmond BC, North Vancouver BC
- GTA: Mississauga ON, Markham ON, Vaughan ON, Oakville ON, Burlington ON
- Montreal area: Laval QC, Longueuil QC, Brossard QC
- Other: Saskatoon SK, Regina SK, Red Deer AB

---

## Component 2: Web Scraping — Targeted Sources

### 2a. Franchise Directories

| Source | URL | Data |
|--------|-----|------|
| Franchise Direct | franchisedirect.com | Brand name, category, location count |
| Entrepreneur Franchise 500 | entrepreneur.com/franchise500 | Top franchises by category |
| Franchise Gator | franchisegator.com | Emerging brands |

Filter: Only retail categories (skip food service, automotive, etc.)

### 2b. Industry Association Member Lists

| Association | Focus |
|-------------|-------|
| NSGA (National Sporting Goods Association) | Sporting goods retailers |
| Outdoor Industry Association | Outdoor/camping retailers |
| Running USA retailer directory | Running specialty stores |
| CHFA (Canadian Health Food Association) | Health/wellness retailers |

### 2c. Local "Best Of" Articles

Scrape Google search results for:
- "best outdoor stores in [city]"
- "top sporting goods stores [city]"
- "independent running stores [city]"

### 2d. Brand Website Store Locators

When we discover a promising brand (3+ locations in one city), scrape their "Find a Store" page to get ALL locations nationally.

---

## Component 3: Brand Expansion Strategy

When a brand is discovered with multiple locations, search for ALL their locations:

### Trigger criteria:

| Condition | Action |
|-----------|--------|
| Brand appears in 2+ cities from initial discovery | Expand to all cities |
| Brand scraped from franchise directory | Expand to all cities |
| Brand has 3+ locations in single city | Expand to all cities |

### Implementation:

```python
async def expand_brand(brand_name: str, known_website: str):
    locations = []
    for city in all_cities:
        results = await places.search(f"{brand_name}", city)
        matching = [r for r in results if same_domain(r.website, known_website)]
        locations.extend(matching)
    return locations
```

### Rate limiting:

- Max 5 concurrent city searches per brand
- 100ms delay between searches
- Skip cities where brand already found

---

## Component 4: Deduplication & Merging

### Matching strategy (priority order):

| Method | Confidence |
|--------|------------|
| Place ID match | 100% |
| Website domain + city | 95% |
| Normalized name + address | 85% |
| Fuzzy name + city | 70% (flag for review) |

### Merge rules:

```
place_id:    Google Places > (not available from scraping)
name:        Google Places > Scraped
website:     Google Places > Scraped
address:     Google Places > Scraped
vertical:    Scraped > Google (better categorization)
source:      Track all sources ["google_places", "franchise_dir", "brand_expansion"]
```

### Output structure:

```python
@dataclass
class MergedPlace:
    name: str
    address: str
    website: str
    place_id: Optional[str]
    city: str
    vertical: str
    sources: list[str]      # Track provenance
    confidence: float       # Match confidence if merged
```

---

## File Structure

### New modules:

```
src/
├── places_search.py        # MODIFY: add Nearby Search, niche queries
├── scraper/                # NEW
│   ├── __init__.py
│   ├── franchise_scraper.py
│   ├── association_scraper.py
│   ├── bestof_scraper.py
│   └── store_locator.py
├── brand_expander.py       # NEW
├── deduplicator.py         # NEW
├── discovery.py            # NEW: orchestrates all 3 sources
├── pipeline.py             # MODIFY: call discovery.py

config/
├── cities.json             # MODIFY: add suburban cities
├── queries.json            # NEW: expanded niche queries
└── scrape_sources.json     # NEW: URLs for scrapers
```

### Pipeline integration:

```python
# pipeline.py
async def run(self, ...):
    discovery = Discovery(settings)
    places = await discovery.run(verticals, countries)

    # Rest unchanged
    brands = self.stage_2_group(places)
    ecommerce_brands = await self.stage_3_ecommerce(brands)
    ...
```

---

## Expected Results

| Metric | Current | Expected |
|--------|---------|----------|
| Total leads | ~170 | 700-1,000 |
| API calls | ~200 | ~2,500 |
| Sources | 1 | 3 |
| Cities covered | 51 | ~100 |

---

## Non-Goals

- Paid data providers (Crunchbase, D&B)
- Real-time scraping (batch is fine)
- International expansion beyond US/Canada
