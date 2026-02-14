# src/lead_scorer.py
"""Lead scoring module for B2B lead generation pipeline.

Scores leads based on tech stack signals, with Lightspeed users as highest priority.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScoredLead:
    """Represents a scored lead with tech stack analysis results."""

    pos_platform: Optional[str] = None
    detected_marketplaces: list[str] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    uses_lightspeed: bool = False
    priority_score: int = 0


class LeadScorer:
    """Scores leads based on tech stack signals and business attributes.

    Scoring weights:
    - Lightspeed POS: +30 points (highest priority)
    - Has marketplaces: +15 points
    - Multiple marketplaces: +10 points (bonus)
    - 3-5 locations: +15 points
    - 6-10 locations: +10 points
    - Has e-commerce: +10 points
    - Has verified contact: +10 points
    """

    # Known POS platforms to detect
    POS_PLATFORMS = [
        "Lightspeed",
        "Shopify POS",
        "Square",
        "Clover",
        "Toast",
        "Revel",
        "Vend",
        "Heartland",
    ]

    # Known marketplaces to detect
    MARKETPLACES = [
        "Amazon",
        "eBay",
        "Etsy",
        "Walmart",
        "Google Shopping",
        "Facebook Shop",
        "Instagram Shop",
    ]

    # Scoring weights
    WEIGHT_LIGHTSPEED = 30
    WEIGHT_MARKETPLACES = 15
    WEIGHT_MULTIPLE_MARKETPLACES = 10
    WEIGHT_LOCATIONS_3_5 = 15
    WEIGHT_LOCATIONS_6_10 = 10
    WEIGHT_ECOMMERCE = 10
    WEIGHT_CONTACTS = 10

    def score(self, lead: dict) -> ScoredLead:
        """Score a single lead based on tech stack signals.

        Args:
            lead: Dictionary containing lead data with fields like
                  technology_names, marketplaces, location_count, etc.

        Returns:
            ScoredLead with analysis results and priority score.
        """
        # Extract tech stack
        tech_stack = lead.get("technology_names", []) or []

        # Detect POS platform
        pos_platform = self._detect_pos_platform(tech_stack)

        # Check for Lightspeed
        uses_lightspeed = pos_platform == "Lightspeed"

        # Detect marketplaces
        detected_marketplaces = self._detect_marketplaces(lead.get("marketplaces", ""))

        # Calculate priority score
        priority_score = self._calculate_score(
            uses_lightspeed=uses_lightspeed,
            detected_marketplaces=detected_marketplaces,
            location_count=lead.get("location_count", 0),
            has_ecommerce=lead.get("has_ecommerce", False),
            has_contact=bool(lead.get("contact_1_name", "").strip()),
        )

        return ScoredLead(
            pos_platform=pos_platform,
            detected_marketplaces=detected_marketplaces,
            tech_stack=tech_stack,
            uses_lightspeed=uses_lightspeed,
            priority_score=priority_score,
        )

    def score_leads(self, leads: list[dict]) -> list[dict]:
        """Score multiple leads and return sorted by priority.

        Args:
            leads: List of lead dictionaries.

        Returns:
            List of lead dictionaries with added scoring fields,
            sorted by priority_score descending.
        """
        scored_results = []

        for lead in leads:
            scored = self.score(lead)

            # Add scoring fields to lead
            enriched_lead = lead.copy()
            enriched_lead["pos_platform"] = scored.pos_platform
            enriched_lead["detected_marketplaces"] = scored.detected_marketplaces
            enriched_lead["uses_lightspeed"] = scored.uses_lightspeed
            enriched_lead["priority_score"] = scored.priority_score

            scored_results.append(enriched_lead)

        # Sort by priority score descending
        scored_results.sort(key=lambda x: x["priority_score"], reverse=True)

        return scored_results

    def _detect_pos_platform(self, tech_stack: list[str]) -> Optional[str]:
        """Detect POS platform from tech stack.

        Args:
            tech_stack: List of technology names.

        Returns:
            Name of detected POS platform, or None if not found.
        """
        for tech in tech_stack:
            tech_lower = tech.lower()
            for pos in self.POS_PLATFORMS:
                if pos.lower() in tech_lower:
                    return pos
        return None

    def _detect_marketplaces(self, marketplaces_str: str) -> list[str]:
        """Detect marketplaces from comma-separated string.

        Args:
            marketplaces_str: Comma-separated marketplace names.

        Returns:
            List of detected marketplace names.
        """
        if not marketplaces_str:
            return []

        detected = []
        marketplaces_lower = marketplaces_str.lower()

        for marketplace in self.MARKETPLACES:
            if marketplace.lower() in marketplaces_lower:
                detected.append(marketplace)

        return detected

    def _calculate_score(
        self,
        uses_lightspeed: bool,
        detected_marketplaces: list[str],
        location_count: int,
        has_ecommerce: bool,
        has_contact: bool,
    ) -> int:
        """Calculate priority score based on signals.

        Args:
            uses_lightspeed: Whether lead uses Lightspeed POS.
            detected_marketplaces: List of detected marketplaces.
            location_count: Number of business locations.
            has_ecommerce: Whether lead has e-commerce presence.
            has_contact: Whether lead has verified contact.

        Returns:
            Priority score (0-100+).
        """
        score = 0

        # Lightspeed bonus (highest priority)
        if uses_lightspeed:
            score += self.WEIGHT_LIGHTSPEED

        # Marketplace presence
        if detected_marketplaces:
            score += self.WEIGHT_MARKETPLACES

            # Multiple marketplaces bonus
            if len(detected_marketplaces) > 1:
                score += self.WEIGHT_MULTIPLE_MARKETPLACES

        # Location count scoring (3-5 is ideal, 6-10 is good)
        if 3 <= location_count <= 5:
            score += self.WEIGHT_LOCATIONS_3_5
        elif 6 <= location_count <= 10:
            score += self.WEIGHT_LOCATIONS_6_10

        # E-commerce presence
        if has_ecommerce:
            score += self.WEIGHT_ECOMMERCE

        # Verified contact
        if has_contact:
            score += self.WEIGHT_CONTACTS

        return score
