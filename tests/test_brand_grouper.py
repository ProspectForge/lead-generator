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