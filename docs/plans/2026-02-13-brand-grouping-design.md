# Brand Grouping & Chain Filtering Improvements

**Date:** 2026-02-13
**Status:** Approved

## Problem

The current brand grouping logic fails to merge name variations like "Nike Store", "Nike Toronto", and "Nike Factory Outlet". This causes large national chains to appear as multiple small brands, each with 2-3 locations, allowing them to slip through the 3-10 location filter.

### Specific Issues

1. **Location suffixes not stripped:** "Healthy Planet - Yonge & Dundas" stays separate from "Healthy Planet - Queen Street"
2. **City names in brand:** "Nike Toronto" not grouped with "Nike Chicago"
3. **Website domain not used:** Locations sharing `popeyestoronto.com` not automatically grouped
4. **Incomplete blocklist:** Missing major chains like Nike, Adidas, Under Armour
5. **Blocklist matching broken:** "Nike Store" doesn't match "nike" in blocklist

## Solution

Three-part improvement with defense in depth.

### Part 1: Multi-Layer Name Normalization

Apply normalization in order of confidence:

**Layer 1 - Separator split (highest confidence):**
- Split on ` - `, ` @ `, ` at `, ` | `, `: `
- Take first part only
- Example: "Healthy Planet - Yonge & Dundas" → "Healthy Planet"

**Layer 2 - Website domain extraction:**
- Extract brand hint from domain: `healthyplanetcanada.com` → "healthyplanet"
- Use as validation signal

**Layer 3 - Suffix stripping (from END only):**
- City names from cities.json (Toronto, Vancouver, Chicago, etc.)
- Location words: Downtown, Uptown, East, West, North, South
- Street patterns: Street, Ave, Blvd, Plaza, Mall, Centre, Center
- Store types: Store, Shop, Outlet, Boutique, Factory

**Layer 4 - Frequency-based core detection:**
- Find shortest common prefix among variants in a group
- Validates that grouped names are actually related

**Safety checks:**
- Never strip if result < 3 characters
- Never strip words that appear in the domain
- Log uncertain matches for review

### Part 2: Expanded Chain Blocklist

Add ~40 missing chains:

| Category | Brands |
|----------|--------|
| Athletic/Apparel | Nike, Adidas, Under Armour, New Balance, Puma, Reebok, Athleta, Fabletics, Columbia |
| Sporting Goods | Big 5, Hibbett Sports, Scheels, Sportsman's Warehouse |
| Supplements | Vitamin World, Complete Nutrition, Max Muscle |
| Apparel | Uniqlo, Express, American Eagle, Aeropostale, Hollister, Abercrombie, Banana Republic, J Crew |
| Outdoor | North Face, Patagonia, Eddie Bauer, LL Bean |

**Improved matching:**
- Match against normalized name (not raw)
- Check if blocklist word appears at START of normalized name
- "nike" blocks: "nike", "nike store", "nike factory outlet"

### Part 3: Hybrid LLM Fallback

Use GPT-4o-mini for ambiguous cases only.

**Triggers for LLM call:**
1. Names partially match but not exact (e.g., "Fleet Feet Running" vs "Fleet Feet Sports")
2. Same domain but different normalized names
3. Near location threshold (8-12 locations)
4. Name contains hints: "National", "America", "USA"

**Batched prompt:**
```
Given these brand groups, identify:
1. Groups that should be merged (same company, different names)
2. Groups that are national chains (50+ locations nationwide)

Brands:
- Fleet Feet Running (5 locations)
- Fleet Feet Sports (3 locations)
...
```

**Response format:**
```json
{
  "merges": [["Fleet Feet Running", "Fleet Feet Sports"]],
  "large_chains": ["Fleet Feet Running"]
}
```

**Cost:** ~$0.01-0.02 per pipeline run

## Architecture

```
Places Data
    │
    ▼
┌─────────────────────────────┐
│ Rule-based normalization    │ ← Multi-layer (separators, domain, suffixes)
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Initial grouping            │ ← By (normalized_name, domain) pair
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Blocklist filter            │ ← Expanded list + prefix matching
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Identify ambiguous cases    │ ← Partial matches, borderline counts
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Batch LLM call (if needed)  │ ← GPT-4o-mini
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Apply LLM recommendations   │
└─────────────────────────────┘
    │
    ▼
Final Brand Groups
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/brand_grouper.py` | Multi-layer normalization, domain grouping, LLM integration |
| `src/config.py` | Add OpenAI key, LLM settings |
| `config/cities.json` | Expanded blocklist, LLM config section |
| `tests/test_brand_grouper.py` | New test cases for normalization and grouping |

## New Dependencies

- `openai` - For GPT-4o-mini API calls

## Configuration

**New env var:**
- `OPENAI_API_KEY` - API key for LLM fallback

**New config in cities.json:**
```json
{
  "llm": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-4o-mini"
  }
}
```

## Success Criteria

1. "Nike Store", "Nike Toronto", "Nike Factory Outlet" all normalize to "nike"
2. "Healthy Planet - Yonge & Dundas" groups with "Healthy Planet - Queen Street"
3. All major athletic/apparel chains blocked (Nike, Adidas, Lululemon, etc.)
4. LLM catches edge cases rules miss
5. Existing tests still pass
