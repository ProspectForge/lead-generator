# src/brand_grouper.py
import re
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

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
