#!/usr/bin/env python3
"""
Generate expanded city list for cities.json from population data.

US data: CSV from github.com/matteo-psnt/US-city-visualization
Canada data: Statistics Canada 2021 Census (hardcoded for cities >= 50k)

Usage:
    python scripts/generate_city_list.py [--min-pop 50000]
"""
import csv
import json
import sys
from pathlib import Path

# US state name -> abbreviation mapping
US_STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    "Puerto Rico": "PR",
}

# Canadian cities with population >= 50,000 (2021 Census)
# Source: Statistics Canada, Census 2021
CANADA_CITIES_50K = [
    # Ontario
    ("Toronto", "ON"), ("Ottawa", "ON"), ("Mississauga", "ON"), ("Brampton", "ON"),
    ("Hamilton", "ON"), ("London", "ON"), ("Markham", "ON"), ("Vaughan", "ON"),
    ("Kitchener", "ON"), ("Windsor", "ON"), ("Richmond Hill", "ON"), ("Oakville", "ON"),
    ("Burlington", "ON"), ("Oshawa", "ON"), ("Barrie", "ON"), ("St. Catharines", "ON"),
    ("Cambridge", "ON"), ("Kingston", "ON"), ("Guelph", "ON"), ("Thunder Bay", "ON"),
    ("Waterloo", "ON"), ("Chatham-Kent", "ON"), ("Brantford", "ON"),
    ("Pickering", "ON"), ("Niagara Falls", "ON"), ("Newmarket", "ON"),
    ("Milton", "ON"), ("Halton Hills", "ON"), ("Peterborough", "ON"),
    ("Sault Ste. Marie", "ON"), ("Sarnia", "ON"), ("Whitby", "ON"),
    ("Ajax", "ON"), ("Clarington", "ON"), ("Sudbury", "ON"),
    ("Welland", "ON"), ("Aurora", "ON"), ("North Bay", "ON"),
    ("Belleville", "ON"), ("Cornwall", "ON"), ("Georgina", "ON"),
    # Quebec
    ("Montreal", "QC"), ("Quebec City", "QC"), ("Laval", "QC"), ("Gatineau", "QC"),
    ("Longueuil", "QC"), ("Sherbrooke", "QC"), ("Levis", "QC"),
    ("Saguenay", "QC"), ("Trois-Rivieres", "QC"), ("Terrebonne", "QC"),
    ("Saint-Jean-sur-Richelieu", "QC"), ("Repentigny", "QC"),
    ("Brossard", "QC"), ("Drummondville", "QC"), ("Saint-Jerome", "QC"),
    ("Granby", "QC"), ("Blainville", "QC"), ("Mirabel", "QC"),
    ("Shawinigan", "QC"), ("Dollard-des-Ormeaux", "QC"),
    ("Rimouski", "QC"), ("Victoriaville", "QC"),
    ("Saint-Hyacinthe", "QC"), ("Mascouche", "QC"),
    # British Columbia
    ("Vancouver", "BC"), ("Surrey", "BC"), ("Burnaby", "BC"), ("Richmond", "BC"),
    ("Abbotsford", "BC"), ("Coquitlam", "BC"), ("Kelowna", "BC"),
    ("Saanich", "BC"), ("Victoria", "BC"), ("Langley", "BC"),
    ("Delta", "BC"), ("Nanaimo", "BC"), ("Kamloops", "BC"),
    ("Chilliwack", "BC"), ("Maple Ridge", "BC"), ("New Westminster", "BC"),
    ("Prince George", "BC"), ("North Vancouver", "BC"), ("Port Coquitlam", "BC"),
    ("West Vancouver", "BC"), ("Vernon", "BC"), ("Mission", "BC"),
    ("Campbell River", "BC"), ("Langford", "BC"), ("Courtenay", "BC"),
    ("Penticton", "BC"), ("White Rock", "BC"),
    # Alberta
    ("Calgary", "AB"), ("Edmonton", "AB"), ("Red Deer", "AB"),
    ("Lethbridge", "AB"), ("St. Albert", "AB"), ("Medicine Hat", "AB"),
    ("Grande Prairie", "AB"), ("Airdrie", "AB"), ("Spruce Grove", "AB"),
    ("Leduc", "AB"), ("Fort Saskatchewan", "AB"), ("Okotoks", "AB"),
    ("Cochrane", "AB"), ("Lloydminster", "AB"), ("Chestermere", "AB"),
    # Manitoba
    ("Winnipeg", "MB"), ("Brandon", "MB"), ("Steinbach", "MB"),
    # Saskatchewan
    ("Saskatoon", "SK"), ("Regina", "SK"), ("Prince Albert", "SK"),
    ("Moose Jaw", "SK"),
    # Nova Scotia
    ("Halifax", "NS"), ("Cape Breton", "NS"), ("Dartmouth", "NS"),
    # New Brunswick
    ("Moncton", "NB"), ("Saint John", "NB"), ("Fredericton", "NB"),
    # Newfoundland
    ("St. John's", "NL"), ("Conception Bay South", "NL"), ("Mount Pearl", "NL"),
    ("Paradise", "NL"),
    # PEI
    ("Charlottetown", "PE"),
]


def load_us_cities(csv_path: str, min_pop: int) -> list[str]:
    """Load US cities from CSV, filter by population, return 'City, ST' format."""
    cities = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue
            # Format: rank, city, state_full, population, growth%, lat, lng
            city_name = row[1].strip()
            state_full = row[2].strip()
            try:
                population = int(row[3].strip())
            except ValueError:
                continue

            state_abbrev = US_STATE_ABBREV.get(state_full)
            if not state_abbrev:
                continue

            if population >= min_pop:
                cities.append((f"{city_name}, {state_abbrev}", population))

    # Sort by population descending, then return just the city strings
    cities.sort(key=lambda x: -x[1])
    return [c[0] for c in cities]


def get_canada_cities() -> list[str]:
    """Return Canadian cities >= 50k in 'City, PR' format."""
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for city, prov in CANADA_CITIES_50K:
        key = f"{city}, {prov}"
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def main():
    min_pop = 50000
    if "--min-pop" in sys.argv:
        idx = sys.argv.index("--min-pop")
        min_pop = int(sys.argv[idx + 1])

    script_dir = Path(__file__).parent
    csv_path = script_dir / "us_cities_raw.csv"

    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found. Download it first:")
        print('  curl -sL "https://raw.githubusercontent.com/matteo-psnt/US-city-visualization/master/Biggest%20US%20Cities%20By%20Population%20-%20city_info.csv" -o scripts/us_cities_raw.csv')
        sys.exit(1)

    us_cities = load_us_cities(str(csv_path), min_pop)
    ca_cities = get_canada_cities()

    print(f"US cities with population >= {min_pop:,}: {len(us_cities)}")
    print(f"Canadian cities with population >= {min_pop:,}: {len(ca_cities)}")
    print(f"Total: {len(us_cities) + len(ca_cities)}")

    # Load existing cities.json
    config_path = script_dir.parent / "config" / "cities.json"
    with open(config_path) as f:
        config = json.load(f)

    # Update city lists
    config["us"] = us_cities
    config["canada"] = ca_cities

    # Write back
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"\nUpdated {config_path}")
    print(f"\nSample US cities (first 10):")
    for c in us_cities[:10]:
        print(f"  {c}")
    print(f"\nSample Canada cities (first 10):")
    for c in ca_cities[:10]:
        print(f"  {c}")


if __name__ == "__main__":
    main()
