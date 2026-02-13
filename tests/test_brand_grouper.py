# tests/test_brand_grouper.py
import pytest
from src.brand_grouper import BrandGrouper, BrandGroup

@pytest.fixture
def sample_places():
    return [
        {"name": "Lululemon Athletica", "address": "NYC", "website": "https://lululemon.com", "city": "New York, NY"},
        {"name": "Lululemon", "address": "LA", "website": "https://lululemon.com", "city": "Los Angeles, CA"},
        {"name": "Lululemon Athletica Store", "address": "Chicago", "website": "https://lululemon.com", "city": "Chicago, IL"},
        {"name": "Nike Store", "address": "NYC", "website": "https://nike.com", "city": "New York, NY"},
        {"name": "Nike", "address": "Boston", "website": "https://nike.com", "city": "Boston, MA"},
        {"name": "Local Boutique", "address": "Austin", "website": "https://local.com", "city": "Austin, TX"},
    ]

def test_group_by_brand_normalizes_names(sample_places):
    grouper = BrandGrouper()
    groups = grouper.group(sample_places)

    # Lululemon variations should be grouped together
    lulu_group = next((g for g in groups if "lululemon" in g.normalized_name.lower()), None)
    assert lulu_group is not None
    assert lulu_group.location_count == 3

def test_filter_by_location_count(sample_places):
    grouper = BrandGrouper(min_locations=3, max_locations=10)
    groups = grouper.group(sample_places)
    filtered = grouper.filter(groups)

    # Only Lululemon has 3+ locations
    assert len(filtered) == 1
    assert filtered[0].location_count == 3

def test_excludes_over_max_locations():
    places = [{"name": f"BigChain Store {i}", "address": f"City {i}", "website": "https://bigchain.com", "city": f"City {i}"} for i in range(15)]

    grouper = BrandGrouper(min_locations=3, max_locations=10)
    groups = grouper.group(places)
    filtered = grouper.filter(groups)

    assert len(filtered) == 0  # 15 locations exceeds max of 10
