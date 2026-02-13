# src/brand_grouper.py
import re
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
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

class BrandGrouper:
    # Common suffixes to strip for normalization
    STRIP_PATTERNS = [
        r'\s+(inc\.?|llc\.?|ltd\.?|corp\.?)$',
        r'\s+(store|shop|boutique|outlet)$',
        r'\s+(athletica|athletics)$',
        r'\s+#?\d+$',  # Store numbers
    ]

    def __init__(self, min_locations: int = 3, max_locations: int = 10):
        self.min_locations = min_locations
        self.max_locations = max_locations

    def _normalize_name(self, name: str) -> str:
        normalized = name.lower().strip()
        for pattern in self.STRIP_PATTERNS:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        return normalized.strip()

    def group(self, places: list[dict]) -> list[BrandGroup]:
        groups: dict[str, BrandGroup] = defaultdict(lambda: BrandGroup(normalized_name=""))

        for place in places:
            name = place.get("name", "")
            normalized = self._normalize_name(name)

            if not normalized:
                continue

            if groups[normalized].normalized_name == "":
                groups[normalized].normalized_name = normalized

            groups[normalized].original_names.append(name)
            groups[normalized].location_count += 1
            groups[normalized].locations.append(place)

            if place.get("website") and not groups[normalized].website:
                groups[normalized].website = place["website"]

            city = place.get("city", "")
            if city and city not in groups[normalized].cities:
                groups[normalized].cities.append(city)

        return list(groups.values())

    def filter(self, groups: list[BrandGroup]) -> list[BrandGroup]:
        return [
            g for g in groups
            if self.min_locations <= g.location_count <= self.max_locations
        ]
