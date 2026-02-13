# Lead Generator

Automated B2B lead generation pipeline for omnichannel retailers.

## Overview

Finds qualified leads by:
1. Searching Google Places for retail businesses
2. Grouping by brand and counting locations
3. Filtering to 3-10 location chains with e-commerce
4. Enriching with LinkedIn contacts

## Target Criteria

| Criteria | Value |
|----------|-------|
| Geography | US + Canada |
| Verticals | Health/wellness, Sporting goods, Apparel |
| Locations | 3-10 physical stores |
| E-commerce | Must have online store |
| Contacts | Owner, CEO, COO, Operations Manager |

## Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your API keys
```

## Usage

```bash
# Full pipeline
python -m src.pipeline --verticals all --countries us,ca

# Step by step
python -m src.places_search --vertical apparel --country us
python -m src.brand_grouper
python -m src.ecommerce_check
python -m src.linkedin_enrich
```

## Output

CSV file in `data/output/` with:
- Brand name, location count, website
- E-commerce status
- LinkedIn company page
- Up to 4 contacts with titles and profile URLs

## API Keys Required

- **Google Places API** - [Get key](https://console.cloud.google.com/)
- **Firecrawl** - [Get key](https://firecrawl.dev/)
