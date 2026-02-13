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

    def _create_key(self, place: dict) -> str:
        """Create a deduplication key for a place."""
        domain = self._normalize_domain(place.get("website", ""))
        city = place.get("city", "").lower().strip()

        if domain and city:
            return f"{domain}|{city}"

        # Fallback to normalized name + city
        name = self._normalize_name(place.get("name", ""))
        return f"{name}|{city}"

    def deduplicate(self, places: list[dict]) -> list[MergedPlace]:
        """Deduplicate and merge places from multiple sources."""
        grouped: dict[str, list[dict]] = {}

        for place in places:
            key = self._create_key(place)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(place)

        merged = []
        for key, group in grouped.items():
            merged.append(self._merge_group(group))

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
