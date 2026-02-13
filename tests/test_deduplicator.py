# tests/test_deduplicator.py
import pytest
from src.deduplicator import Deduplicator, MergedPlace

@pytest.fixture
def duplicate_places():
    return [
        {"name": "Fleet Feet Boston", "address": "123 Main St", "website": "https://fleetfeet.com", "place_id": "abc123", "city": "Boston, MA", "vertical": "running", "source": "google_places"},
        {"name": "Fleet Feet", "address": "123 Main Street", "website": "https://fleetfeet.com", "place_id": None, "city": "Boston, MA", "vertical": "sporting_goods", "source": "franchise_scrape"},
        {"name": "Nike Store", "address": "456 Broadway", "website": "https://nike.com", "place_id": "def456", "city": "Boston, MA", "vertical": "apparel", "source": "google_places"},
    ]

def test_deduplicates_by_website_and_city(duplicate_places):
    deduplicator = Deduplicator()
    merged = deduplicator.deduplicate(duplicate_places)

    # Should merge the two Fleet Feet entries
    assert len(merged) == 2

    fleet_feet = next(m for m in merged if "fleet" in m.name.lower())
    assert fleet_feet.place_id == "abc123"  # Prefers Google Places data
    assert "google_places" in fleet_feet.sources
    assert "franchise_scrape" in fleet_feet.sources

def test_preserves_unique_places(duplicate_places):
    deduplicator = Deduplicator()
    merged = deduplicator.deduplicate(duplicate_places)

    nike = next(m for m in merged if "nike" in m.name.lower())
    assert nike.place_id == "def456"
    assert len(nike.sources) == 1

def test_normalizes_website_domains():
    deduplicator = Deduplicator()

    assert deduplicator._normalize_domain("https://www.fleetfeet.com/store") == "fleetfeet.com"
    assert deduplicator._normalize_domain("http://fleetfeet.com") == "fleetfeet.com"
    assert deduplicator._normalize_domain("fleetfeet.com/about") == "fleetfeet.com"
