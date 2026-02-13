# Brand Grouping Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve brand grouping to correctly merge name variations (Nike Store/Nike Toronto) and filter out large chains using multi-layer normalization, expanded blocklist, and LLM fallback.

**Architecture:** Four-layer name normalization (separator split → domain extraction → suffix stripping → frequency detection), expanded blocklist with prefix matching, and batched GPT-4o-mini calls for ambiguous cases.

**Tech Stack:** Python 3.11+, openai package, existing brand_grouper.py refactored

---

## Task 1: Add OpenAI Dependency

**Files:**
- Modify: `requirements.txt`

**Step 1: Add openai package**

Add to requirements.txt:
```
openai>=1.0.0
```

**Step 2: Install dependency**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && pip install openai>=1.0.0`
Expected: Successfully installed openai

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add openai dependency for LLM fallback"
```

---

## Task 2: Expand Configuration

**Files:**
- Modify: `src/config.py`
- Modify: `config/cities.json`

**Step 1: Update cities.json with expanded blocklist and LLM config**

Add to `config/cities.json` (merge with existing):
```json
{
  "known_large_chains": [
    "gnc",
    "vitamin shoppe",
    "the vitamin shoppe",
    "cvs",
    "walgreens",
    "rite aid",
    "dicks sporting goods",
    "academy sports",
    "rei",
    "bass pro shops",
    "cabelas",
    "gap",
    "old navy",
    "h&m",
    "zara",
    "forever 21",
    "lululemon",
    "foot locker",
    "finish line",
    "petco",
    "petsmart",
    "pet supplies plus",
    "ulta",
    "sephora",
    "sally beauty",
    "whole foods",
    "trader joes",
    "sprouts",
    "fleet feet",
    "road runner sports",
    "trek bicycle",
    "performance bicycle",
    "camping world",
    "buy buy baby",
    "carters",
    "oshkosh",
    "williams sonoma",
    "sur la table",
    "crate and barrel",
    "bed bath beyond",
    "nike",
    "adidas",
    "under armour",
    "new balance",
    "puma",
    "reebok",
    "athleta",
    "fabletics",
    "columbia",
    "big 5",
    "hibbett sports",
    "scheels",
    "sportsmans warehouse",
    "vitamin world",
    "complete nutrition",
    "max muscle",
    "uniqlo",
    "express",
    "american eagle",
    "aeropostale",
    "hollister",
    "abercrombie",
    "banana republic",
    "j crew",
    "north face",
    "the north face",
    "patagonia",
    "eddie bauer",
    "ll bean",
    "asics",
    "brooks",
    "saucony",
    "hoka",
    "on running",
    "target",
    "walmart",
    "costco",
    "sams club",
    "best buy",
    "macys",
    "nordstrom",
    "kohls",
    "jcpenney",
    "ross",
    "tj maxx",
    "marshalls"
  ],
  "llm": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-4o-mini"
  }
}
```

**Step 2: Update config.py to load LLM settings**

Replace `src/config.py` with:
```python
# src/config.py
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMSettings:
    enabled: bool = True
    provider: str = "openai"
    model: str = "gpt-4o-mini"


@dataclass
class Settings:
    google_places_api_key: str = ""
    firecrawl_api_key: str = ""
    openai_api_key: str = ""
    cities: dict = field(default_factory=dict)
    search_queries: dict = field(default_factory=dict)
    known_large_chains: set = field(default_factory=set)
    chain_filter_max_cities: int = 8
    ecommerce_concurrency: int = 10
    ecommerce_pages_to_check: int = 3
    search_concurrency: int = 10
    llm: LLMSettings = field(default_factory=LLMSettings)

    def __post_init__(self):
        self.google_places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

        config_path = Path(__file__).parent.parent / "config" / "cities.json"
        with open(config_path) as f:
            config = json.load(f)

        self.cities = {
            "us": config.get("us", []),
            "canada": config.get("canada", [])
        }
        self.search_queries = config.get("search_queries", {})
        self.known_large_chains = set(chain.lower() for chain in config.get("known_large_chains", []))
        self.chain_filter_max_cities = config.get("chain_filter", {}).get("max_cities", 8)
        self.ecommerce_concurrency = config.get("ecommerce", {}).get("concurrency", 10)
        self.ecommerce_pages_to_check = config.get("ecommerce", {}).get("pages_to_check", 3)
        self.search_concurrency = config.get("search", {}).get("concurrency", 10)

        llm_config = config.get("llm", {})
        self.llm = LLMSettings(
            enabled=llm_config.get("enabled", True),
            provider=llm_config.get("provider", "openai"),
            model=llm_config.get("model", "gpt-4o-mini")
        )

    def get_all_city_names(self) -> set[str]:
        """Return all city names for stripping from brand names."""
        all_cities = set()
        for country_cities in self.cities.values():
            for city in country_cities:
                # "Toronto, ON" -> add both "Toronto" and "Toronto, ON"
                all_cities.add(city.lower())
                city_name = city.split(",")[0].strip().lower()
                all_cities.add(city_name)
        return all_cities


settings = Settings()
```

**Step 3: Run existing tests to verify nothing broke**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_config.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/config.py config/cities.json
git commit -m "feat: expand blocklist and add LLM config"
```

---

## Task 3: Multi-Layer Name Normalizer

**Files:**
- Modify: `src/brand_grouper.py`
- Modify: `tests/test_brand_grouper.py`

**Step 1: Write failing tests for multi-layer normalization**

Add to `tests/test_brand_grouper.py`:
```python
class TestNameNormalizer:
    """Tests for the multi-layer name normalization."""

    def test_strips_separator_suffix(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        assert normalizer.normalize("Healthy Planet - Yonge & Dundas") == "healthy planet"
        assert normalizer.normalize("Nike @ Downtown Mall") == "nike"
        assert normalizer.normalize("Store Name | Location") == "store name"

    def test_strips_city_names(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        assert normalizer.normalize("Nike Toronto") == "nike"
        assert normalizer.normalize("Supplement King Vancouver") == "supplement king"
        assert normalizer.normalize("Fleet Feet Chicago") == "fleet feet"

    def test_strips_location_words(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        assert normalizer.normalize("Nike Downtown") == "nike"
        assert normalizer.normalize("Store Name East") == "store name"
        assert normalizer.normalize("Brand Plaza") == "brand"

    def test_strips_store_types(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        assert normalizer.normalize("Nike Factory Outlet") == "nike"
        assert normalizer.normalize("Brand Store") == "brand"
        assert normalizer.normalize("Name Boutique") == "name"

    def test_preserves_domain_words(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        # "Portland" should stay if it's in the domain
        result = normalizer.normalize("Portland Running Company", domain="portlandrunning.com")
        assert "portland" in result

    def test_minimum_length_safety(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        # Should not strip to less than 3 chars
        assert len(normalizer.normalize("AB Store")) >= 2

    def test_extracts_domain_hint(self):
        from src.brand_grouper import NameNormalizer
        normalizer = NameNormalizer()

        assert normalizer.extract_domain_hint("https://healthyplanetcanada.com/store") == "healthyplanetcanada"
        assert normalizer.extract_domain_hint("http://www.nike.com") == "nike"
        assert normalizer.extract_domain_hint("popeyestoronto.com") == "popeyestoronto"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestNameNormalizer -v`
Expected: FAIL with "cannot import name 'NameNormalizer'"

**Step 3: Implement NameNormalizer class**

Add to `src/brand_grouper.py` (before BrandGrouper class):
```python
from urllib.parse import urlparse
from src.config import settings


class NameNormalizer:
    """Multi-layer name normalization for brand grouping."""

    # Layer 1: Separators to split on (take first part)
    SEPARATORS = [' - ', ' @ ', ' at ', ' | ', ': ']

    # Layer 3: Location words to strip from END
    LOCATION_WORDS = {
        'downtown', 'uptown', 'midtown', 'east', 'west', 'north', 'south',
        'street', 'st', 'ave', 'avenue', 'blvd', 'boulevard', 'road', 'rd',
        'plaza', 'mall', 'centre', 'center', 'square', 'park'
    }

    # Layer 3: Store types to strip from END
    STORE_TYPES = {
        'store', 'shop', 'boutique', 'outlet', 'factory', 'factory outlet',
        'clearance', 'warehouse', 'superstore', 'megastore', 'express'
    }

    # Legal suffixes to strip
    LEGAL_SUFFIXES = {'inc', 'llc', 'ltd', 'corp', 'co', 'company'}

    def __init__(self):
        self.city_names = settings.get_all_city_names()

    def extract_domain_hint(self, url: str) -> str:
        """Extract brand hint from domain name."""
        if not url:
            return ""

        try:
            # Handle URLs without scheme
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            # Take the main domain part (before TLD)
            parts = domain.split('.')
            if len(parts) >= 2:
                # Return the main part (e.g., "healthyplanetcanada" from "healthyplanetcanada.com")
                return parts[0].lower()
            return domain.lower()
        except Exception:
            return ""

    def normalize(self, name: str, domain: str = "") -> str:
        """Apply multi-layer normalization to a brand name."""
        if not name:
            return ""

        original = name
        result = name.strip()

        # Layer 1: Split on separators, take first part
        for sep in self.SEPARATORS:
            if sep in result:
                result = result.split(sep)[0].strip()
                break

        # Lowercase for remaining operations
        result = result.lower()

        # Extract domain hint for protection
        domain_hint = self.extract_domain_hint(domain)
        protected_words = set(domain_hint.replace('-', ' ').split()) if domain_hint else set()

        # Layer 3a: Strip legal suffixes
        words = result.split()
        while words and words[-1].rstrip('.') in self.LEGAL_SUFFIXES:
            words.pop()
        result = ' '.join(words)

        # Layer 3b: Strip store types from end
        for store_type in sorted(self.STORE_TYPES, key=len, reverse=True):
            if result.endswith(' ' + store_type):
                candidate = result[:-len(store_type)-1].strip()
                if len(candidate) >= 3:
                    result = candidate
                    break

        # Layer 3c: Strip location words from end (if not protected)
        words = result.split()
        while words and words[-1] in self.LOCATION_WORDS and words[-1] not in protected_words:
            candidate = ' '.join(words[:-1])
            if len(candidate) >= 3:
                words.pop()
                result = candidate
            else:
                break

        # Layer 3d: Strip city names from end (if not protected)
        words = result.split()
        if words:
            last_word = words[-1]
            if last_word in self.city_names and last_word not in protected_words:
                candidate = ' '.join(words[:-1])
                if len(candidate) >= 3:
                    result = candidate

        # Layer 3e: Strip store numbers from end
        result = re.sub(r'\s*#?\d+$', '', result).strip()

        # Safety: never return less than 3 characters (unless input was shorter)
        if len(result) < 3 and len(original) >= 3:
            result = original.lower().strip()

        return result.strip()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestNameNormalizer -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/brand_grouper.py tests/test_brand_grouper.py
git commit -m "feat: add multi-layer NameNormalizer class"
```

---

## Task 4: Domain-Aware Grouping

**Files:**
- Modify: `src/brand_grouper.py`
- Modify: `tests/test_brand_grouper.py`

**Step 1: Write failing tests for domain-aware grouping**

Add to `tests/test_brand_grouper.py`:
```python
class TestDomainAwareGrouping:
    """Tests for grouping that uses both name and domain."""

    def test_groups_by_normalized_name_and_domain(self):
        places = [
            {"name": "Healthy Planet - Yonge", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet - Queen", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet Downtown", "website": "https://healthyplanet.com", "city": "Vancouver, BC"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        # All three should be in one group
        assert len(groups) == 1
        assert groups[0].location_count == 3

    def test_same_name_different_domain_separate(self):
        places = [
            {"name": "The Running Room", "website": "https://runningroom.com", "city": "Toronto, ON"},
            {"name": "The Running Room", "website": "https://differentrunningroom.com", "city": "Vancouver, BC"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        # Same name but different domains - should be separate
        assert len(groups) == 2

    def test_merges_groups_with_same_domain_similar_names(self):
        places = [
            {"name": "Nike Store", "website": "https://nike.com", "city": "Toronto, ON"},
            {"name": "Nike Factory Outlet", "website": "https://nike.com", "city": "Vancouver, BC"},
            {"name": "Nike", "website": "https://nike.com", "city": "Chicago, IL"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        # All Nike variations with same domain should merge
        assert len(groups) == 1
        assert groups[0].location_count == 3
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestDomainAwareGrouping -v`
Expected: FAIL (tests show wrong grouping)

**Step 3: Update BrandGrouper to use NameNormalizer and domain-aware grouping**

Replace the `BrandGrouper` class in `src/brand_grouper.py`:
```python
class BrandGrouper:
    """Groups places by brand using multi-layer normalization and domain matching."""

    def __init__(self, min_locations: int = 3, max_locations: int = 10):
        self.min_locations = min_locations
        self.max_locations = max_locations
        self.normalizer = NameNormalizer()

    def _get_domain(self, url: str) -> str:
        """Extract normalized domain from URL."""
        return self.normalizer.extract_domain_hint(url)

    def _get_group_key(self, name: str, website: str) -> tuple[str, str]:
        """Generate grouping key from name and website."""
        domain = self._get_domain(website) if website else ""
        normalized_name = self.normalizer.normalize(name, domain=website)
        return (normalized_name, domain)

    def group(self, places: list[dict]) -> list[BrandGroup]:
        """Group places by normalized name and domain."""
        # Phase 1: Initial grouping by (normalized_name, domain)
        groups: dict[tuple[str, str], BrandGroup] = defaultdict(
            lambda: BrandGroup(normalized_name="")
        )

        for place in places:
            name = place.get("name", "")
            website = place.get("website", "")

            if not name:
                continue

            key = self._get_group_key(name, website)
            normalized_name, domain = key

            if not normalized_name:
                continue

            if groups[key].normalized_name == "":
                groups[key].normalized_name = normalized_name

            groups[key].original_names.append(name)
            groups[key].location_count += 1
            groups[key].locations.append(place)

            if website and not groups[key].website:
                groups[key].website = website

            city = place.get("city", "")
            if city and city not in groups[key].cities:
                groups[key].cities.append(city)

        # Phase 2: Merge groups with same domain and similar names
        merged_groups = self._merge_by_domain(list(groups.values()))

        return merged_groups

    def _merge_by_domain(self, groups: list[BrandGroup]) -> list[BrandGroup]:
        """Merge groups that share the same domain and have related names."""
        # Group by domain
        by_domain: dict[str, list[BrandGroup]] = defaultdict(list)
        no_domain: list[BrandGroup] = []

        for group in groups:
            domain = self._get_domain(group.website) if group.website else ""
            if domain:
                by_domain[domain].append(group)
            else:
                no_domain.append(group)

        merged = []

        # Merge groups with same domain
        for domain, domain_groups in by_domain.items():
            if len(domain_groups) == 1:
                merged.append(domain_groups[0])
            else:
                # Check if names are related (share common prefix)
                if self._names_are_related([g.normalized_name for g in domain_groups]):
                    # Merge all into one
                    base = domain_groups[0]
                    for other in domain_groups[1:]:
                        base.original_names.extend(other.original_names)
                        base.location_count += other.location_count
                        base.locations.extend(other.locations)
                        for city in other.cities:
                            if city not in base.cities:
                                base.cities.append(city)
                    merged.append(base)
                else:
                    # Keep separate
                    merged.extend(domain_groups)

        # Add groups without domains
        merged.extend(no_domain)

        return merged

    def _names_are_related(self, names: list[str]) -> bool:
        """Check if names share a common prefix (indicating same brand)."""
        if not names or len(names) < 2:
            return True

        # Find shortest common prefix
        sorted_names = sorted(names, key=len)
        shortest = sorted_names[0]

        # Check if all names start with the shortest one (or vice versa)
        for name in names:
            # At least 3 chars must match at start
            prefix_len = 0
            for i, (c1, c2) in enumerate(zip(shortest, name)):
                if c1 == c2:
                    prefix_len = i + 1
                else:
                    break

            if prefix_len < 3:
                return False

        return True

    def filter(self, groups: list[BrandGroup]) -> list[BrandGroup]:
        """Filter groups by location count."""
        return [
            g for g in groups
            if self.min_locations <= g.location_count <= self.max_locations
        ]
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/brand_grouper.py tests/test_brand_grouper.py
git commit -m "feat: add domain-aware grouping with merge logic"
```

---

## Task 5: Improved Blocklist Matching

**Files:**
- Modify: `src/brand_grouper.py`
- Modify: `tests/test_brand_grouper.py`

**Step 1: Write failing tests for blocklist matching**

Add to `tests/test_brand_grouper.py`:
```python
class TestBlocklistMatching:
    """Tests for improved blocklist matching."""

    def test_blocks_exact_match(self):
        from src.brand_grouper import BlocklistChecker
        checker = BlocklistChecker()

        assert checker.is_blocked("nike") == True
        assert checker.is_blocked("adidas") == True
        assert checker.is_blocked("lululemon") == True

    def test_blocks_with_suffix(self):
        from src.brand_grouper import BlocklistChecker
        checker = BlocklistChecker()

        assert checker.is_blocked("nike store") == True
        assert checker.is_blocked("nike factory outlet") == True
        assert checker.is_blocked("the north face") == True

    def test_allows_partial_unrelated(self):
        from src.brand_grouper import BlocklistChecker
        checker = BlocklistChecker()

        # "nike" in blocklist shouldn't block "nikesha's boutique"
        assert checker.is_blocked("nikesha's boutique") == False

    def test_allows_unknown_brands(self):
        from src.brand_grouper import BlocklistChecker
        checker = BlocklistChecker()

        assert checker.is_blocked("portland running company") == False
        assert checker.is_blocked("local supplement shop") == False
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestBlocklistMatching -v`
Expected: FAIL with "cannot import name 'BlocklistChecker'"

**Step 3: Implement BlocklistChecker class**

Add to `src/brand_grouper.py` (after NameNormalizer):
```python
class BlocklistChecker:
    """Check if a brand name matches the large chain blocklist."""

    def __init__(self):
        self.blocklist = settings.known_large_chains
        self.normalizer = NameNormalizer()

    def is_blocked(self, name: str) -> bool:
        """Check if a normalized brand name should be blocked."""
        normalized = self.normalizer.normalize(name)

        # Exact match
        if normalized in self.blocklist:
            return True

        # Prefix match: "nike store" starts with "nike"
        # But protect against false positives like "nikesha"
        for chain in self.blocklist:
            if normalized.startswith(chain + ' '):
                return True
            if normalized.startswith(chain + "'s "):
                return True

        return False
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestBlocklistMatching -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/brand_grouper.py tests/test_brand_grouper.py
git commit -m "feat: add BlocklistChecker with prefix matching"
```

---

## Task 6: LLM Fallback for Ambiguous Cases

**Files:**
- Modify: `src/brand_grouper.py`
- Modify: `tests/test_brand_grouper.py`

**Step 1: Write failing tests for LLM integration**

Add to `tests/test_brand_grouper.py`:
```python
from unittest.mock import patch, MagicMock

class TestLLMFallback:
    """Tests for LLM-based disambiguation."""

    def test_identifies_ambiguous_cases(self):
        from src.brand_grouper import LLMBrandAnalyzer

        groups = [
            BrandGroup(normalized_name="fleet feet running", location_count=5),
            BrandGroup(normalized_name="fleet feet sports", location_count=3),
            BrandGroup(normalized_name="portland running", location_count=4),
        ]

        analyzer = LLMBrandAnalyzer(enabled=False)  # Disabled for this test
        ambiguous = analyzer.find_ambiguous_groups(groups)

        # "fleet feet running" and "fleet feet sports" are ambiguous
        assert len(ambiguous) >= 1

    def test_skips_llm_when_disabled(self):
        from src.brand_grouper import LLMBrandAnalyzer

        groups = [
            BrandGroup(normalized_name="fleet feet running", location_count=5),
            BrandGroup(normalized_name="fleet feet sports", location_count=3),
        ]

        analyzer = LLMBrandAnalyzer(enabled=False)
        result = analyzer.analyze(groups)

        # Should return empty recommendations when disabled
        assert result.merges == []
        assert result.large_chains == []

    @patch('src.brand_grouper.OpenAI')
    def test_calls_openai_for_ambiguous(self, mock_openai_class):
        from src.brand_grouper import LLMBrandAnalyzer

        # Mock OpenAI response
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content='{"merges": [["fleet feet running", "fleet feet sports"]], "large_chains": []}'
                )
            )]
        )

        groups = [
            BrandGroup(normalized_name="fleet feet running", location_count=5),
            BrandGroup(normalized_name="fleet feet sports", location_count=3),
        ]

        analyzer = LLMBrandAnalyzer(enabled=True)
        result = analyzer.analyze(groups)

        assert ["fleet feet running", "fleet feet sports"] in result.merges
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestLLMFallback -v`
Expected: FAIL with "cannot import name 'LLMBrandAnalyzer'"

**Step 3: Implement LLMBrandAnalyzer class**

Add to `src/brand_grouper.py`:
```python
import json
from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


@dataclass
class LLMAnalysisResult:
    """Result from LLM brand analysis."""
    merges: list[list[str]]  # Groups of brand names to merge
    large_chains: list[str]  # Brand names that are large national chains


class LLMBrandAnalyzer:
    """Use LLM to disambiguate brand groups and detect large chains."""

    PROMPT_TEMPLATE = """You are analyzing retail brand names to help identify:
1. Groups that should be merged (same company, different name variations)
2. Brands that are large national chains (50+ locations nationwide)

Here are the brand groups found:
{brand_list}

Respond with JSON only, no explanation:
{{
  "merges": [["brand1", "brand2"], ["brand3", "brand4"]],
  "large_chains": ["brand5", "brand6"]
}}

Rules:
- Only merge if you're confident they're the same company
- Only mark as large_chain if you know it's a major national/international retailer
- If uncertain, don't include it
"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and settings.llm.enabled
        self.model = settings.llm.model
        self.client = None

        if self.enabled and OpenAI and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def find_ambiguous_groups(self, groups: list[BrandGroup]) -> list[list[BrandGroup]]:
        """Find groups that might need LLM disambiguation."""
        ambiguous_sets = []

        # Find groups with similar names (shared prefix)
        names = [(g.normalized_name, g) for g in groups]

        for i, (name1, group1) in enumerate(names):
            similar = [group1]
            words1 = set(name1.split())

            for name2, group2 in names[i+1:]:
                words2 = set(name2.split())
                # Check for significant word overlap
                overlap = words1 & words2
                if len(overlap) >= 1 and len(overlap) / max(len(words1), len(words2)) >= 0.5:
                    similar.append(group2)

            if len(similar) > 1:
                ambiguous_sets.append(similar)

        # Also flag groups near the threshold (8-12 locations)
        borderline = [g for g in groups if 8 <= g.location_count <= 12]
        if borderline:
            ambiguous_sets.append(borderline)

        return ambiguous_sets

    def analyze(self, groups: list[BrandGroup]) -> LLMAnalysisResult:
        """Analyze groups using LLM and return recommendations."""
        if not self.enabled or not self.client:
            return LLMAnalysisResult(merges=[], large_chains=[])

        # Find ambiguous cases
        ambiguous = self.find_ambiguous_groups(groups)
        if not ambiguous:
            return LLMAnalysisResult(merges=[], large_chains=[])

        # Build brand list for prompt
        relevant_groups = set()
        for group_set in ambiguous:
            relevant_groups.update(group_set)

        brand_list = "\n".join(
            f"- {g.normalized_name} ({g.location_count} locations)"
            for g in relevant_groups
        )

        prompt = self.PROMPT_TEMPLATE.format(brand_list=brand_list)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1000
            )

            content = response.choices[0].message.content
            # Parse JSON from response
            result = json.loads(content)

            return LLMAnalysisResult(
                merges=result.get("merges", []),
                large_chains=result.get("large_chains", [])
            )
        except Exception as e:
            # Log error but don't fail the pipeline
            print(f"LLM analysis failed: {e}")
            return LLMAnalysisResult(merges=[], large_chains=[])
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestLLMFallback -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/brand_grouper.py tests/test_brand_grouper.py
git commit -m "feat: add LLMBrandAnalyzer for ambiguous cases"
```

---

## Task 7: Integrate All Components

**Files:**
- Modify: `src/brand_grouper.py`
- Modify: `tests/test_brand_grouper.py`

**Step 1: Write integration test**

Add to `tests/test_brand_grouper.py`:
```python
class TestFullPipeline:
    """Integration tests for the complete brand grouping pipeline."""

    def test_full_pipeline_filters_large_chains(self):
        places = [
            {"name": "Nike Store", "website": "https://nike.com", "city": "Toronto, ON"},
            {"name": "Nike Toronto", "website": "https://nike.com", "city": "Toronto, ON"},
            {"name": "Nike Factory Outlet", "website": "https://nike.com", "city": "Vancouver, BC"},
            {"name": "Local Running Shop", "website": "https://localrunning.com", "city": "Toronto, ON"},
            {"name": "Local Running Shop", "website": "https://localrunning.com", "city": "Vancouver, BC"},
            {"name": "Local Running Shop", "website": "https://localrunning.com", "city": "Montreal, QC"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)
        filtered = grouper.filter_with_blocklist(groups)

        # Nike should be blocked, Local Running Shop should pass
        assert len(filtered) == 1
        assert "local" in filtered[0].normalized_name

    def test_location_suffixes_grouped(self):
        places = [
            {"name": "Healthy Planet - Yonge & Dundas", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet - Queen Street", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet Downtown", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        assert len(groups) == 1
        assert groups[0].location_count == 3
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py::TestFullPipeline -v`
Expected: FAIL (filter_with_blocklist doesn't exist)

**Step 3: Add filter_with_blocklist method to BrandGrouper**

Add to `BrandGrouper` class in `src/brand_grouper.py`:
```python
    def filter_with_blocklist(self, groups: list[BrandGroup]) -> list[BrandGroup]:
        """Filter groups by location count and blocklist."""
        checker = BlocklistChecker()

        filtered = []
        for g in groups:
            # Check location count
            if not (self.min_locations <= g.location_count <= self.max_locations):
                continue

            # Check blocklist
            if checker.is_blocked(g.normalized_name):
                continue

            filtered.append(g)

        return filtered

    def process_with_llm(self, groups: list[BrandGroup]) -> list[BrandGroup]:
        """Process groups with LLM for final disambiguation."""
        analyzer = LLMBrandAnalyzer()
        result = analyzer.analyze(groups)

        # Apply merges
        if result.merges:
            groups = self._apply_merges(groups, result.merges)

        # Filter out LLM-detected large chains
        if result.large_chains:
            large_chain_set = set(result.large_chains)
            groups = [g for g in groups if g.normalized_name not in large_chain_set]

        return groups

    def _apply_merges(self, groups: list[BrandGroup], merges: list[list[str]]) -> list[BrandGroup]:
        """Apply LLM-suggested merges to groups."""
        # Build lookup
        by_name = {g.normalized_name: g for g in groups}
        merged_names = set()

        result = []

        for merge_set in merges:
            # Find groups to merge
            to_merge = [by_name[name] for name in merge_set if name in by_name]
            if len(to_merge) < 2:
                continue

            # Merge into first
            base = to_merge[0]
            for other in to_merge[1:]:
                base.original_names.extend(other.original_names)
                base.location_count += other.location_count
                base.locations.extend(other.locations)
                for city in other.cities:
                    if city not in base.cities:
                        base.cities.append(city)
                merged_names.add(other.normalized_name)

        # Return all groups except those merged away
        for g in groups:
            if g.normalized_name not in merged_names:
                result.append(g)

        return result
```

**Step 4: Run all tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/brand_grouper.py tests/test_brand_grouper.py
git commit -m "feat: integrate blocklist filter and LLM processing"
```

---

## Task 8: Update Pipeline Integration

**Files:**
- Modify: `src/pipeline.py`

**Step 1: Update pipeline to use new brand grouper methods**

In `src/pipeline.py`, update `stage_2_group` method:
```python
    def stage_2_group(self, places: list[dict]) -> list[BrandGroup]:
        """Group places by brand and filter by location count."""
        self._show_stage_header(2, "Brand Grouping", "Normalizing names and grouping by brand")

        with console.status("[cyan]Analyzing brands...[/cyan]"):
            grouper = BrandGrouper(min_locations=3, max_locations=10)
            groups = grouper.group(places)

            # Apply blocklist filter
            filtered = grouper.filter_with_blocklist(groups)

            # Apply LLM disambiguation if enabled
            if settings.llm.enabled:
                console.print("  [dim]• Running LLM disambiguation...[/dim]")
                filtered = grouper.process_with_llm(filtered)

        # Show summary table
        table = Table(box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_row("Total places", str(len(places)))
        table.add_row("Unique brands", str(len(groups)))
        table.add_row("After blocklist filter", str(len(filtered)))
        table.add_row("Brands with 3-10 locations", f"[bold]{len(filtered)}[/bold]")

        console.print(table)

        if filtered:
            console.print(f"\n  [dim]Top brands:[/dim]")
            for brand in sorted(filtered, key=lambda x: x.location_count, reverse=True)[:5]:
                console.print(f"    • {brand.normalized_name.title()} ({brand.location_count} locations)")

        return filtered
```

**Step 2: Run pipeline tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/pipeline.py
git commit -m "feat: integrate improved brand grouper into pipeline"
```

---

## Task 9: Final Integration Test

**Files:**
- Create: `tests/test_brand_grouper_integration.py`

**Step 1: Create integration test with real-world data**

Create `tests/test_brand_grouper_integration.py`:
```python
"""Integration tests using realistic data patterns."""
import pytest
from src.brand_grouper import BrandGrouper, NameNormalizer, BlocklistChecker


class TestRealWorldScenarios:
    """Test scenarios based on actual data patterns."""

    def test_popeyes_supplements_grouped(self):
        """Popeye's Supplements with various Toronto locations should group."""
        places = [
            {"name": "Popeye's Supplements", "website": "http://www.popeyestoronto.com", "city": "Toronto, ON"},
            {"name": "Popeye's Supplements", "website": "http://www.popeyestoronto.com", "city": "Toronto, ON"},
            {"name": "Popeye's Supplements", "website": "https://popeyestoronto.com", "city": "Toronto, ON"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        assert len(groups) == 1
        assert groups[0].location_count == 3

    def test_healthy_planet_locations_grouped(self):
        """Healthy Planet with location suffixes should all group together."""
        places = [
            {"name": "Healthy Planet - Yonge & Dundas", "website": "https://www.healthyplanetcanada.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet - Queen Street", "website": "https://www.healthyplanetcanada.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet Toronto", "website": "https://www.healthyplanetcanada.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet", "website": "https://www.healthyplanetcanada.com", "city": "Vancouver, BC"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        assert len(groups) == 1
        assert groups[0].location_count == 4

    def test_nike_variations_blocked(self):
        """All Nike variations should be blocked by blocklist."""
        places = [
            {"name": "Nike Store", "website": "https://nike.com", "city": "Toronto, ON"},
            {"name": "Nike Factory Outlet", "website": "https://nike.com", "city": "Vancouver, BC"},
            {"name": "Nike Toronto", "website": "https://nike.com", "city": "Toronto, ON"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)
        filtered = grouper.filter_with_blocklist(groups)

        assert len(filtered) == 0

    def test_local_brand_passes_through(self):
        """Local/regional brands should pass through."""
        places = [
            {"name": "Portland Running Company", "website": "https://portlandrunning.com", "city": "Portland, OR"},
            {"name": "Portland Running Company", "website": "https://portlandrunning.com", "city": "Portland, OR"},
            {"name": "Portland Running Company", "website": "https://portlandrunning.com", "city": "Seattle, WA"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)
        filtered = grouper.filter_with_blocklist(groups)

        assert len(filtered) == 1
        assert filtered[0].location_count == 3
```

**Step 2: Run integration tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_brand_grouper_integration.py -v`
Expected: All tests PASS

**Step 3: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_brand_grouper_integration.py
git commit -m "test: add real-world integration tests for brand grouper"
```

---

## Summary

| Task | Component | Purpose |
|------|-----------|---------|
| 1 | requirements.txt | Add openai dependency |
| 2 | config.py, cities.json | Expanded blocklist + LLM config |
| 3 | NameNormalizer | Multi-layer name normalization |
| 4 | BrandGrouper.group() | Domain-aware grouping |
| 5 | BlocklistChecker | Prefix-based blocklist matching |
| 6 | LLMBrandAnalyzer | GPT-4o-mini fallback |
| 7 | BrandGrouper integration | Wire all components together |
| 8 | Pipeline integration | Use new grouper in pipeline |
| 9 | Integration tests | Real-world scenario validation |

**New env var required:** `OPENAI_API_KEY`

**To test after implementation:**
```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
python -m pytest tests/ -v
python -m src --verticals health_wellness --countries us
```
