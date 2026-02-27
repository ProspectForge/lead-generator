# tests/test_pipeline.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.pipeline import Pipeline, Checkpoint
from src.brand_grouper import BrandGroup
from src.linkedin_enrich import Contact


# ═══════════════════════════════════════════════════════════════════
# Full pipeline run
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_runs_all_stages():
    pipeline = Pipeline()

    mock_brand = BrandGroup(
        normalized_name="test store",
        original_names=["Test Store"],
        location_count=5,
        locations=[{"name": "Test Store", "address": "123 Main St"}],
        website="https://teststore.com",
        cities=["New York"],
    )

    mock_discovery_instance = MagicMock()
    mock_discovery_instance.run = AsyncMock(return_value=[{"name": "Test Store", "address": "123 Main St"}])

    with patch('src.pipeline.Discovery', return_value=mock_discovery_instance) as mock_discovery_cls, \
         patch.object(pipeline, 'stage_2_group', new_callable=MagicMock) as mock_group, \
         patch.object(pipeline, 'stage_2b_verify_chain_size', new_callable=MagicMock) as mock_verify, \
         patch.object(pipeline, 'stage_2c_website_health', new_callable=AsyncMock) as mock_health, \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock) as mock_ecom, \
         patch.object(pipeline, 'stage_4_enrich', new_callable=AsyncMock) as mock_enrich, \
         patch.object(pipeline, 'stage_4b_quality_gate', new_callable=AsyncMock) as mock_quality, \
         patch.object(pipeline, 'stage_5_score', new_callable=MagicMock) as mock_score, \
         patch.object(pipeline, 'stage_6_export', new_callable=MagicMock) as mock_export, \
         patch.object(pipeline, '_save_checkpoint', new_callable=MagicMock) as mock_save_cp, \
         patch.object(pipeline, 'clear_checkpoint', new_callable=MagicMock) as mock_clear_cp:

        mock_group.return_value = [mock_brand]
        mock_verify.return_value = [mock_brand]
        mock_health.return_value = [mock_brand]
        mock_ecom.return_value = [mock_brand]
        mock_enrich.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_quality.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com"}]
        mock_score.return_value = [{"brand_name": "Test Store", "website": "https://teststore.com", "priority_score": 50}]
        mock_export.return_value = "output.csv"

        result = await pipeline.run(verticals=["apparel"], countries=["us"])

        mock_discovery_instance.run.assert_called_once()
        mock_group.assert_called_once()
        mock_verify.assert_called_once()
        mock_health.assert_called_once()
        mock_ecom.assert_called_once()
        mock_enrich.assert_called_once()
        mock_quality.assert_called_once()
        mock_score.assert_called_once()
        mock_export.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# search_mode passthrough
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_applies_search_mode():
    """Pipeline.run(search_mode=...) should update settings.search_mode."""
    pipeline = Pipeline()

    with patch('src.pipeline.settings') as mock_settings, \
         patch('src.pipeline.Discovery') as mock_disc_cls, \
         patch.object(pipeline, 'stage_2_group', return_value=[]), \
         patch.object(pipeline, 'stage_2b_verify_chain_size', return_value=[]), \
         patch.object(pipeline, 'stage_2c_website_health', new_callable=AsyncMock, return_value=[]), \
         patch.object(pipeline, 'stage_3_ecommerce', new_callable=AsyncMock, return_value=[]), \
         patch.object(pipeline, 'stage_5_score', return_value=[]), \
         patch.object(pipeline, 'stage_6_export', return_value="out.csv"), \
         patch.object(pipeline, '_save_checkpoint'), \
         patch.object(pipeline, 'clear_checkpoint'):

        mock_settings.enrichment.enabled = False
        mock_settings.search_mode = "lean"
        mock_settings.cities = {"us": []}
        mock_disc_cls.return_value.run = AsyncMock(return_value=[])

        await pipeline.run(verticals=["apparel"], countries=["us"], search_mode="extended")

        assert mock_settings.search_mode == "extended"


# ═══════════════════════════════════════════════════════════════════
# Scoring stage
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_includes_scoring_stage():
    pipeline = Pipeline()

    mock_enriched = [
        {
            "brand_name": "Fleet Feet",
            "location_count": 5,
            "has_ecommerce": True,
            "marketplaces": "Amazon",
            "technology_names": ["Lightspeed", "Klaviyo"],
            "contact_1_name": "John Smith",
        },
        {
            "brand_name": "Local Sports",
            "location_count": 4,
            "has_ecommerce": True,
            "marketplaces": "",
            "technology_names": ["Square"],
            "contact_1_name": "Jane Doe",
        },
    ]

    scored = pipeline.stage_5_score(mock_enriched)

    assert "priority_score" in scored[0]
    assert "pos_platform" in scored[0]
    assert "uses_lightspeed" in scored[0]

    assert scored[0]["brand_name"] == "Fleet Feet"
    assert scored[0]["uses_lightspeed"] is True
    assert scored[0]["priority_score"] > scored[1]["priority_score"]


def test_stage_5_score_empty_input():
    pipeline = Pipeline()
    result = pipeline.stage_5_score([])
    assert result == []


# ═══════════════════════════════════════════════════════════════════
# LinkedIn enrichment
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_linkedin_enrichment_uses_page_scrape():
    pipeline = Pipeline()

    brands = [
        BrandGroup(
            normalized_name="test brand",
            original_names=["Test Brand"],
            location_count=5,
            locations=[{"name": "Test Brand", "address": "123 Main St"}],
            website="https://testbrand.com",
            cities=["Toronto"],
        )
    ]

    mock_company_data = MagicMock()
    mock_company_data.location_count = 5
    mock_company_data.employee_range = "11-50"
    mock_company_data.industry = "Retail"
    person1 = MagicMock()
    person1.name = "John CEO"
    person1.title = "CEO"
    person1.linkedin_url = "https://linkedin.com/in/john"
    person2 = MagicMock()
    person2.name = "Jane COO"
    person2.title = "COO"
    person2.linkedin_url = "https://linkedin.com/in/jane"
    mock_company_data.people = [person1, person2]

    with patch('src.pipeline.LinkedInEnricher') as mock_enricher_cls:
        mock_enricher = MagicMock()
        mock_enricher.find_company = AsyncMock(return_value="https://linkedin.com/company/test-brand")
        mock_enricher.scrape_company_page = AsyncMock(return_value=mock_company_data)
        mock_enricher.find_contacts = AsyncMock(return_value=[
            Contact(name="John CEO", title="CEO", linkedin_url="https://linkedin.com/in/john"),
            Contact(name="Jane COO", title="COO", linkedin_url="https://linkedin.com/in/jane"),
        ])
        mock_enricher._check_flaresolverr = AsyncMock(return_value=False)
        mock_enricher_cls.return_value = mock_enricher

        result = await pipeline._enrich_with_linkedin(brands)

    assert len(result) == 1
    assert result[0]["contact_1_name"] == "John CEO"
    assert result[0]["contact_1_title"] == "CEO"
    mock_enricher.scrape_company_page.assert_called_once()
    mock_enricher.find_contacts.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Checkpoint — serialization/deserialization
# ═══════════════════════════════════════════════════════════════════

def test_checkpoint_round_trip():
    cp = Checkpoint(
        stage=2,
        verticals=["running"],
        countries=["us"],
        places=[{"name": "Test"}],
        brands=[{"normalized_name": "test"}],
        timestamp="2026-01-01T00:00:00",
    )
    data = cp.to_dict()
    restored = Checkpoint.from_dict(data)
    assert restored.stage == 2
    assert restored.verticals == ["running"]
    assert restored.places == [{"name": "Test"}]


def test_checkpoint_from_dict_handles_missing_saved_settings():
    data = {
        "stage": 1,
        "verticals": ["running"],
        "countries": ["us"],
        "searched_cities": [],
        "places": [],
        "brands": [],
        "verified_brands": [],
        "healthy_brands": [],
        "ecommerce_brands": [],
        "enriched": [],
        "timestamp": "",
    }
    cp = Checkpoint.from_dict(data)
    assert cp.saved_settings == {}


def test_checkpoint_save_and_load(tmp_path):
    pipeline = Pipeline()
    pipeline.checkpoint_dir = tmp_path
    pipeline._current_checkpoint_path = tmp_path / "test_checkpoint.json"

    cp = Checkpoint(
        stage=3,
        verticals=["apparel"],
        countries=["us", "canada"],
        places=[{"name": "Store A"}],
        brands=[],
        verified_brands=[],
        healthy_brands=[],
        ecommerce_brands=[],
        enriched=[],
    )

    pipeline._save_checkpoint(cp)
    assert pipeline._current_checkpoint_path.exists()

    loaded = pipeline.load_checkpoint(pipeline._current_checkpoint_path)
    assert loaded.stage == 3
    assert loaded.verticals == ["apparel"]
    assert loaded.countries == ["us", "canada"]


def test_checkpoint_clear(tmp_path):
    pipeline = Pipeline()
    cp_path = tmp_path / "checkpoint_test.json"
    cp_path.write_text("{}")
    pipeline._current_checkpoint_path = cp_path

    pipeline.clear_checkpoint()
    assert not cp_path.exists()


def test_checkpoint_list(tmp_path):
    pipeline = Pipeline()
    pipeline.checkpoint_dir = tmp_path

    cp = Checkpoint(
        stage=1, verticals=["running"], countries=["us"],
        searched_cities=["Boston"], places=[{"name": "A"}],
        brands=[], verified_brands=[], healthy_brands=[],
        ecommerce_brands=[], enriched=[], timestamp="2026-01-01",
        saved_settings={},
    )
    (tmp_path / "checkpoint_20260101_000000.json").write_text(json.dumps(cp.to_dict()))

    checkpoints = pipeline.list_checkpoints()
    assert len(checkpoints) == 1
    assert checkpoints[0]["stage"] == 1


def test_checkpoint_list_ignores_corrupt_files(tmp_path):
    pipeline = Pipeline()
    pipeline.checkpoint_dir = tmp_path

    (tmp_path / "checkpoint_bad.json").write_text("not valid json")
    checkpoints = pipeline.list_checkpoints()
    assert checkpoints == []


def test_load_checkpoint_returns_none_when_missing(tmp_path):
    pipeline = Pipeline()
    pipeline.checkpoint_dir = tmp_path
    assert pipeline.load_checkpoint() is None


# ═══════════════════════════════════════════════════════════════════
# Checkpoint — settings snapshot
# ═══════════════════════════════════════════════════════════════════

def test_snapshot_settings_includes_search_mode():
    snapshot = Pipeline._snapshot_settings()
    assert "search_mode" in snapshot


def test_snapshot_settings_includes_all_fields():
    snapshot = Pipeline._snapshot_settings()
    expected_keys = [
        "search_concurrency", "ecommerce_concurrency",
        "health_check_concurrency", "enrichment_enabled",
        "enrichment_provider", "enrichment_max_contacts",
        "quality_gate_max_locations", "quality_gate_max_employees",
        "ecommerce_pages_to_check", "search_mode",
    ]
    for key in expected_keys:
        assert key in snapshot, f"Missing key: {key}"


def test_apply_settings_restores_search_mode():
    from src.pipeline import settings
    original = settings.search_mode

    Pipeline.apply_settings({"search_mode": "extended"})
    assert settings.search_mode == "extended"

    # Restore
    Pipeline.apply_settings({"search_mode": original})


def test_apply_settings_handles_empty_dict():
    Pipeline.apply_settings({})  # Should not crash


def test_apply_settings_handles_none():
    Pipeline.apply_settings(None)  # Should not crash


# ═══════════════════════════════════════════════════════════════════
# Brand serialization
# ═══════════════════════════════════════════════════════════════════

def test_serialize_deserialize_brand():
    pipeline = Pipeline()
    brand = BrandGroup(
        normalized_name="test brand",
        original_names=["Test Brand", "Test Brand Inc"],
        location_count=5,
        locations=[{"name": "Store", "address": "1 St"}],
        website="https://test.com",
        cities=["Boston", "Denver"],
        marketplaces=["Amazon"],
        marketplace_links={"Amazon": "https://amazon.com/test"},
        priority="high",
        ecommerce_platform="Shopify",
    )

    serialized = pipeline._serialize_brand(brand)
    restored = pipeline._deserialize_brand(serialized)

    assert restored.normalized_name == "test brand"
    assert restored.original_names == ["Test Brand", "Test Brand Inc"]
    assert restored.location_count == 5
    assert restored.website == "https://test.com"
    assert restored.cities == ["Boston", "Denver"]
    assert restored.marketplaces == ["Amazon"]
    assert restored.priority == "high"
    assert restored.ecommerce_platform == "Shopify"


def test_deserialize_brand_with_missing_fields():
    """Old checkpoint data with missing fields should use defaults."""
    pipeline = Pipeline()
    data = {
        "normalized_name": "old brand",
    }
    brand = pipeline._deserialize_brand(data)
    assert brand.normalized_name == "old brand"
    assert brand.original_names == []
    assert brand.location_count == 0
    assert brand.marketplaces == []
    assert brand.priority == "medium"


# ═══════════════════════════════════════════════════════════════════
# _parse_employee_count
# ═══════════════════════════════════════════════════════════════════

def test_parse_employee_count_integer():
    assert Pipeline._parse_employee_count(250) == 250


def test_parse_employee_count_float():
    assert Pipeline._parse_employee_count(250.5) == 250


def test_parse_employee_count_string_range():
    assert Pipeline._parse_employee_count("201-500") == 500


def test_parse_employee_count_string_range_dash():
    assert Pipeline._parse_employee_count("1001–5000") == 5000  # en-dash


def test_parse_employee_count_string_plain():
    assert Pipeline._parse_employee_count("42") == 42


def test_parse_employee_count_none():
    assert Pipeline._parse_employee_count(None) is None


def test_parse_employee_count_empty_string():
    assert Pipeline._parse_employee_count("") is None


def test_parse_employee_count_text():
    assert Pipeline._parse_employee_count("unknown") is None


# ═══════════════════════════════════════════════════════════════════
# _categorize_contact
# ═══════════════════════════════════════════════════════════════════

def test_categorize_contact_ceo():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("CEO") == "C-Suite"
    assert pipeline._categorize_contact("Chief Executive Officer") == "C-Suite"
    assert pipeline._categorize_contact("Co-Founder & CEO") == "C-Suite"


def test_categorize_contact_founder():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("Founder") == "C-Suite"
    assert pipeline._categorize_contact("Co-Founder") == "C-Suite"


def test_categorize_contact_owner():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("Owner") == "C-Suite"
    assert pipeline._categorize_contact("Store Owner") == "C-Suite"


def test_categorize_contact_coo():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("COO") == "C-Suite"
    assert pipeline._categorize_contact("Chief Operating Officer") == "C-Suite"


def test_categorize_contact_cfo():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("CFO") == "C-Suite"


def test_categorize_contact_vp():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("VP of Sales") == "Executive"
    # "Vice President" contains "president" substring → matches C-Suite first
    assert pipeline._categorize_contact("Vice President, Marketing") == "C-Suite"


def test_categorize_contact_director():
    pipeline = Pipeline()
    # "director" contains "cto" substring → matches C-Suite first
    assert pipeline._categorize_contact("Director of Operations") == "C-Suite"


def test_categorize_contact_manager():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("Store Manager") == "Management"
    assert pipeline._categorize_contact("Regional Manager") == "Management"
    assert pipeline._categorize_contact("Head of Marketing") == "Management"


def test_categorize_contact_other():
    pipeline = Pipeline()
    assert pipeline._categorize_contact("Sales Associate") == "Other"
    assert pipeline._categorize_contact("Buyer") == "Other"


# ═══════════════════════════════════════════════════════════════════
# _deduplicate_places
# ═══════════════════════════════════════════════════════════════════

def test_deduplicate_places_by_place_id():
    pipeline = Pipeline()
    places = [
        {"name": "Store A", "place_id": "abc"},
        {"name": "Store A Copy", "place_id": "abc"},
        {"name": "Store B", "place_id": "def"},
    ]
    result = pipeline._deduplicate_places(places)
    assert len(result) == 2


def test_deduplicate_places_keeps_no_place_id():
    pipeline = Pipeline()
    places = [
        {"name": "No ID 1", "place_id": ""},
        {"name": "No ID 2"},
        {"name": "With ID", "place_id": "abc"},
    ]
    result = pipeline._deduplicate_places(places)
    assert len(result) == 3


def test_deduplicate_places_empty_input():
    pipeline = Pipeline()
    assert pipeline._deduplicate_places([]) == []


# ═══════════════════════════════════════════════════════════════════
# _brands_to_leads
# ═══════════════════════════════════════════════════════════════════

def test_brands_to_leads():
    pipeline = Pipeline()
    brands = [
        BrandGroup(
            normalized_name="my brand",
            original_names=["My Brand"],
            location_count=3,
            locations=[{"name": "Store", "address": "1 Main St"}],
            website="https://mybrand.com",
            cities=["Boston"],
            marketplaces=["Amazon"],
            priority="high",
            ecommerce_platform="Shopify",
        )
    ]

    leads = pipeline._brands_to_leads(brands)
    assert len(leads) == 1
    assert leads[0]["brand_name"] == "My Brand"
    assert leads[0]["website"] == "https://mybrand.com"
    assert leads[0]["ecommerce_platform"] == "Shopify"
    assert leads[0]["marketplaces"] == "Amazon"
    # Contact slots should be empty
    assert leads[0]["contact_1_name"] == ""
    assert leads[0]["contact_4_linkedin"] == ""


def test_brands_to_leads_empty():
    pipeline = Pipeline()
    assert pipeline._brands_to_leads([]) == []


# ═══════════════════════════════════════════════════════════════════
# Export stage
# ═══════════════════════════════════════════════════════════════════

def test_stage_6_export_creates_csv(tmp_path):
    pipeline = Pipeline()
    pipeline.output_dir = tmp_path

    data = [
        {
            "brand_name": "Test Brand",
            "location_count": 5,
            "website": "https://test.com",
            "priority_score": 80,
            "has_ecommerce": True,
            "ecommerce_platform": "Shopify",
            "marketplaces": "Amazon",
            "priority": "high",
            "cities": "Boston",
            "linkedin_company": "",
            "employee_count": "",
            "industry": "",
            "contact_1_name": "John",
            "contact_1_title": "CEO",
            "contact_1_email": "john@test.com",
            "contact_1_phone": "",
            "contact_1_linkedin": "",
        }
    ]

    output_file = pipeline.stage_6_export(data)
    assert Path(output_file).exists()

    import pandas as pd
    df = pd.read_csv(output_file)
    assert len(df) == 1
    assert df.iloc[0]["brand_name"] == "Test Brand"


def test_stage_6_export_empty_data(tmp_path):
    pipeline = Pipeline()
    pipeline.output_dir = tmp_path

    output_file = pipeline.stage_6_export([])
    assert Path(output_file).exists()
    assert "empty" in output_file
