# src/deduplicator.py
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

@dataclass
class MergedPlace:
    name: str
    address: str
    website: Optional[str]
    place_id: Optional[str]
    city: str
    vertical: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 1.0

class Deduplicator:
    """Merges places from multiple sources, removing duplicates."""

    def _normalize_domain(self, url: str) -> str:
        """Extract and normalize domain from URL."""
        if not url:
            return ""

        # Add scheme if missing
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _normalize_name(self, name: str) -> str:
        """Normalize business name for comparison."""
        name = name.lower().strip()
        # Remove common suffixes
        suffixes = [" inc", " llc", " ltd", " corp", " store", " shop", " boutique"]
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.strip()

    def _normalize_address(self, address: str) -> str:
        """Normalize address for dedup comparison.

        Standardizes street suffixes and removes suite/unit so that
        '123 Main St' and '123 Main Street' produce the same key,
        while '123 Main St' and '456 Broadway' remain distinct.
        """
        addr = address.lower().strip()
        # Remove suite/unit/apt numbers
        addr = re.sub(r'\b(suite|ste|unit|apt|#)\s*\w+', '', addr)
        # Normalize common street suffixes to canonical form
        suffix_map = {
            r'\bstreet\b': 'st', r'\bavenue\b': 'ave', r'\bboulevard\b': 'blvd',
            r'\bdrive\b': 'dr', r'\blane\b': 'ln', r'\broad\b': 'rd',
            r'\bcourt\b': 'ct', r'\bplace\b': 'pl', r'\bparkway\b': 'pkwy',
            r'\bcircle\b': 'cir', r'\bhighway\b': 'hwy', r'\bterrace\b': 'ter',
        }
        for pattern, replacement in suffix_map.items():
            addr = re.sub(pattern, replacement, addr)
        addr = re.sub(r'\s+', ' ', addr).strip()
        return addr

    def _brand_key(self, place: dict) -> str:
        """Create a brand+city key (without address) for initial grouping."""
        domain = self._normalize_domain(place.get("website", ""))
        city = place.get("city", "").lower().strip()
        if domain and city:
            return f"{domain}|{city}"
        name = self._normalize_name(place.get("name", ""))
        return f"{name}|{city}"

    def deduplicate(self, places: list[dict]) -> list[MergedPlace]:
        """Deduplicate and merge places from multiple sources.

        Groups by brand+city first, then splits by address within each
        group so that multiple physical locations in the same city are
        preserved while true duplicates (same address or missing address)
        are merged.
        """
        # Phase 1: group by brand + city
        brand_city_groups: dict[str, list[dict]] = {}
        for place in places:
            key = self._brand_key(place)
            if key not in brand_city_groups:
                brand_city_groups[key] = []
            brand_city_groups[key].append(place)

        merged = []
        for _key, group in brand_city_groups.items():
            # Phase 2: within each brand+city group, sub-group by address
            addr_groups: dict[str, list[dict]] = {}
            no_addr: list[dict] = []

            for place in group:
                addr = self._normalize_address(place.get("address", ""))
                if addr:
                    if addr not in addr_groups:
                        addr_groups[addr] = []
                    addr_groups[addr].append(place)
                else:
                    no_addr.append(place)

            if addr_groups:
                # Merge no-address entries into the first address group
                # (they're likely the same location from a source lacking address data)
                first_key = next(iter(addr_groups))
                addr_groups[first_key].extend(no_addr)

                for addr_group in addr_groups.values():
                    merged.append(self._merge_group(addr_group))
            else:
                # All entries lack addresses — merge them all
                merged.append(self._merge_group(no_addr))

        return merged

    def _merge_group(self, group: list[dict]) -> MergedPlace:
        """Merge a group of duplicate places into one."""
        # Sort by source priority: google_places > brand_expansion > scraped
        priority = {"google_places": 0, "brand_expansion": 1}
        group.sort(key=lambda p: priority.get(p.get("source", ""), 2))

        # Take best values from each field
        primary = group[0]
        sources = list(set(p.get("source", "unknown") for p in group))

        # Find best place_id (prefer non-None)
        place_id = next((p.get("place_id") for p in group if p.get("place_id")), None)

        # Find best website
        website = next((p.get("website") for p in group if p.get("website")), None)

        return MergedPlace(
            name=primary.get("name", ""),
            address=primary.get("address", ""),
            website=website,
            place_id=place_id,
            city=primary.get("city", ""),
            vertical=primary.get("vertical", ""),
            sources=sources,
            confidence=1.0 if len(group) == 1 else 0.95
        )
