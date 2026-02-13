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
