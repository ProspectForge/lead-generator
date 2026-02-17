# src/brand_grouper.py
import json
import re
import httpx
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from urllib.parse import urlparse
from src.config import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


import asyncio
from concurrent.futures import ThreadPoolExecutor


def resolve_redirect(url: str, timeout: float = 3.0) -> str:
    """
    Follow URL redirects and return the final URL.

    Args:
        url: The URL to resolve
        timeout: Timeout in seconds for the request

    Returns:
        The final URL after following redirects, or original URL on error
    """
    if not url:
        return url

    # Ensure URL has a scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # Use HEAD request with follow_redirects to get final URL
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.head(url)
            return str(response.url)
    except Exception:
        # On any error, return the original URL
        return url


def resolve_redirects_parallel(urls: list[str], max_workers: int = 10, timeout: float = 3.0) -> dict[str, str]:
    """
    Resolve multiple URLs in parallel.

    Args:
        urls: List of URLs to resolve
        max_workers: Maximum parallel workers
        timeout: Timeout per request

    Returns:
        Dict mapping original URL to final URL
    """
    results = {}
    unique_urls = list(set(url for url in urls if url))

    if not unique_urls:
        return results

    def resolve_one(url: str) -> tuple[str, str]:
        try:
            return (url, resolve_redirect(url, timeout))
        except Exception:
            # On any error, return original URL
            return (url, url)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for original, resolved in executor.map(resolve_one, unique_urls):
            results[original] = resolved

    return results


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
        self.city_names = set(name.lower() for name in settings.get_all_city_names())

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

@dataclass
class LLMAnalysisResult:
    """Result from LLM brand analysis."""
    merges: list  # Groups of brand names to merge
    large_chains: list  # Brand names that are large national chains


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

    def find_ambiguous_groups(self, groups: list) -> list:
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

    def analyze(self, groups: list) -> LLMAnalysisResult:
        """Analyze groups using LLM and return recommendations."""
        if not self.enabled or not self.client:
            return LLMAnalysisResult(merges=[], large_chains=[])

        # Find ambiguous cases
        ambiguous = self.find_ambiguous_groups(groups)
        if not ambiguous:
            return LLMAnalysisResult(merges=[], large_chains=[])

        # Build brand list for prompt
        relevant_groups = []
        seen_names = set()
        for group_set in ambiguous:
            for g in group_set:
                if g.normalized_name not in seen_names:
                    relevant_groups.append(g)
                    seen_names.add(g.normalized_name)

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

@dataclass
class BrandGroup:
    normalized_name: str
    original_names: list[str] = field(default_factory=list)
    location_count: int = 0
    locations: list[dict] = field(default_factory=list)
    website: Optional[str] = None
    cities: list[str] = field(default_factory=list)
    estimated_nationwide: Optional[int] = None  # Estimated total locations
    is_large_chain: bool = False  # Flag for chains that exceed our criteria
    marketplaces: list[str] = field(default_factory=list)
    marketplace_links: dict[str, str] = field(default_factory=dict)
    priority: str = "medium"
    ecommerce_platform: Optional[str] = None  # Detected platform (shopify, woocommerce, etc.)


class BrandGrouper:
    """Groups places by brand using multi-layer normalization and domain matching."""

    def __init__(self, min_locations: int = 3, max_locations: int = 10, resolve_redirects: bool = False):
        self.min_locations = min_locations
        self.max_locations = max_locations
        self.normalizer = NameNormalizer()
        self.resolve_redirects = resolve_redirects
        self._redirect_cache: dict[str, str] = {}  # Cache resolved URLs

    def _resolve_url(self, url: str) -> str:
        """Resolve URL redirects if enabled, with caching."""
        if not url or not self.resolve_redirects:
            return url

        if url not in self._redirect_cache:
            try:
                self._redirect_cache[url] = resolve_redirect(url)
            except Exception:
                # On any error, fall back to original URL
                self._redirect_cache[url] = url

        return self._redirect_cache[url]

    def _get_domain(self, url: str) -> str:
        """Extract normalized domain from URL (after resolving redirects if enabled)."""
        resolved_url = self._resolve_url(url)
        return self.normalizer.extract_domain_hint(resolved_url)

    def _get_group_key(self, name: str, website: str) -> tuple[str, str]:
        """Generate grouping key from name and website."""
        domain = self._get_domain(website) if website else ""
        normalized_name = self.normalizer.normalize(name, domain=website)
        return (normalized_name, domain)

    def group(self, places: list[dict]) -> list[BrandGroup]:
        """Group places by normalized name and domain."""
        # Phase 0: Pre-resolve all URLs in parallel for performance
        if self.resolve_redirects:
            urls = [place.get("website", "") for place in places if place.get("website")]
            resolved = resolve_redirects_parallel(urls, max_workers=50, timeout=3.0)
            self._redirect_cache.update(resolved)

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
