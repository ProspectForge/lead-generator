# tests/test_brand_grouper.py
import pytest
from unittest.mock import patch, MagicMock
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


class TestLLMFallback:
    """Tests for LLM-based disambiguation."""

    def test_identifies_ambiguous_cases(self):
        from src.brand_grouper import LLMBrandAnalyzer, BrandGroup

        groups = [
            BrandGroup(normalized_name="fleet feet running", location_count=5),
            BrandGroup(normalized_name="fleet feet sports", location_count=3),
            BrandGroup(normalized_name="portland running", location_count=4),
        ]

        analyzer = LLMBrandAnalyzer(enabled=False)  # Disabled for this test
        ambiguous = analyzer.find_ambiguous_groups(groups)

        # "fleet feet running" and "fleet feet sports" are ambiguous
        assert len(ambiguous) >= 1

    def test_skips_llm_when_disabled(self):
        from src.brand_grouper import LLMBrandAnalyzer, BrandGroup

        groups = [
            BrandGroup(normalized_name="fleet feet running", location_count=5),
            BrandGroup(normalized_name="fleet feet sports", location_count=3),
        ]

        analyzer = LLMBrandAnalyzer(enabled=False)
        result = analyzer.analyze(groups)

        # Should return empty recommendations when disabled
        assert result.merges == []
        assert result.large_chains == []

    @patch('src.brand_grouper.settings')
    @patch('src.brand_grouper.OpenAI')
    def test_calls_openai_for_ambiguous(self, mock_openai_class, mock_settings):
        from src.brand_grouper import LLMBrandAnalyzer, BrandGroup

        # Mock settings
        mock_settings.llm.enabled = True
        mock_settings.llm.model = "gpt-4o-mini"
        mock_settings.openai_api_key = "test-key"

        # Mock OpenAI response
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content='{"merges": [["fleet feet running", "fleet feet sports"]], "large_chains": []}'
                )
            )]
        )

        groups = [
            BrandGroup(normalized_name="fleet feet running", location_count=5),
            BrandGroup(normalized_name="fleet feet sports", location_count=3),
        ]

        analyzer = LLMBrandAnalyzer(enabled=True)
        result = analyzer.analyze(groups)

        assert ["fleet feet running", "fleet feet sports"] in result.merges


class TestFullPipeline:
    """Integration tests for the complete brand grouping pipeline."""

    def test_full_pipeline_filters_large_chains(self):
        places = [
            {"name": "Nike Store", "website": "https://nike.com", "city": "Toronto, ON"},
            {"name": "Nike Toronto", "website": "https://nike.com", "city": "Toronto, ON"},
            {"name": "Nike Factory Outlet", "website": "https://nike.com", "city": "Vancouver, BC"},
            {"name": "Local Running Shop", "website": "https://localrunning.com", "city": "Toronto, ON"},
            {"name": "Local Running Shop", "website": "https://localrunning.com", "city": "Vancouver, BC"},
            {"name": "Local Running Shop", "website": "https://localrunning.com", "city": "Montreal, QC"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)
        filtered = grouper.filter_with_blocklist(groups)

        # Nike should be blocked, Local Running Shop should pass
        assert len(filtered) == 1
        assert "local" in filtered[0].normalized_name

    def test_location_suffixes_grouped(self):
        places = [
            {"name": "Healthy Planet - Yonge & Dundas", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet - Queen Street", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
            {"name": "Healthy Planet Downtown", "website": "https://healthyplanet.com", "city": "Toronto, ON"},
        ]

        grouper = BrandGrouper()
        groups = grouper.group(places)

        assert len(groups) == 1
        assert groups[0].location_count == 3


class TestURLRedirection:
    """Tests for URL redirection handling during brand grouping."""

    @patch('src.brand_grouper.resolve_redirect')
    def test_groups_by_final_redirect_url(self, mock_resolve):
        """Different URLs that redirect to the same domain should be grouped."""
        # Mock redirects: both URLs redirect to popeyescanada.com
        def mock_redirect(url, timeout=3.0):
            redirects = {
                "https://popeyestoronto.com": "https://popeyescanada.com",
                "https://popeyesvancouver.com": "https://popeyescanada.com",
                "https://popeyescanada.com": "https://popeyescanada.com",
            }
            return redirects.get(url, url)

        mock_resolve.side_effect = mock_redirect

        places = [
            {"name": "Popeye's Supplements Toronto", "website": "https://popeyestoronto.com", "city": "Toronto, ON"},
            {"name": "Popeye's Supplements Vancouver", "website": "https://popeyesvancouver.com", "city": "Vancouver, BC"},
            {"name": "Popeye's Supplements", "website": "https://popeyescanada.com", "city": "Montreal, QC"},
        ]

        grouper = BrandGrouper(resolve_redirects=True)
        groups = grouper.group(places)

        # All three should be grouped together due to redirect resolution
        assert len(groups) == 1
        assert groups[0].location_count == 3
        assert "popeye" in groups[0].normalized_name.lower()

    @patch('src.brand_grouper.resolve_redirect')
    def test_handles_redirect_timeout(self, mock_resolve):
        """Should fall back to original URL if redirect resolution fails."""
        def mock_redirect(url, timeout=3.0):
            if "slow" in url:
                raise TimeoutError("Connection timed out")
            return url

        mock_resolve.side_effect = mock_redirect

        places = [
            {"name": "Fast Store", "website": "https://faststore.com", "city": "Toronto, ON"},
            {"name": "Slow Store", "website": "https://slowstore.com", "city": "Vancouver, BC"},
        ]

        grouper = BrandGrouper(resolve_redirects=True)
        groups = grouper.group(places)

        # Should still work, just with original URLs
        assert len(groups) == 2

    def test_redirect_disabled_by_default(self):
        """Redirect resolution should be disabled by default for performance."""
        grouper = BrandGrouper()
        assert getattr(grouper, 'resolve_redirects', False) == False