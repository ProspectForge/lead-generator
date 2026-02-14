# tests/test_lead_scorer.py
import pytest
from src.lead_scorer import LeadScorer, ScoredLead


@pytest.fixture
def lightspeed_lead():
    return {
        "brand_name": "Fleet Feet",
        "location_count": 5,
        "has_ecommerce": True,
        "marketplaces": "Amazon, Etsy",
        "technology_names": ["Lightspeed", "Klaviyo", "Stripe"],
        "contact_1_name": "John Smith",
    }


@pytest.fixture
def non_lightspeed_lead():
    return {
        "brand_name": "Local Sports",
        "location_count": 4,
        "has_ecommerce": True,
        "marketplaces": "",
        "technology_names": ["Square", "Mailchimp"],
        "contact_1_name": "Jane Doe",
    }


@pytest.fixture
def no_tech_data_lead():
    return {
        "brand_name": "Unknown Store",
        "location_count": 3,
        "has_ecommerce": True,
        "marketplaces": "",
        "technology_names": [],
        "contact_1_name": "",
    }


def test_scores_lightspeed_highest(lightspeed_lead):
    scorer = LeadScorer()
    result = scorer.score(lightspeed_lead)

    assert result.uses_lightspeed is True
    assert result.priority_score >= 70  # High score for Lightspeed + marketplaces + contacts


def test_extracts_pos_platform(lightspeed_lead, non_lightspeed_lead):
    scorer = LeadScorer()

    result1 = scorer.score(lightspeed_lead)
    assert result1.pos_platform == "Lightspeed"

    result2 = scorer.score(non_lightspeed_lead)
    assert result2.pos_platform == "Square"


def test_extracts_marketplaces(lightspeed_lead):
    scorer = LeadScorer()
    result = scorer.score(lightspeed_lead)

    assert "Amazon" in result.detected_marketplaces
    assert "Etsy" in result.detected_marketplaces


def test_handles_missing_tech_data(no_tech_data_lead):
    scorer = LeadScorer()
    result = scorer.score(no_tech_data_lead)

    assert result.pos_platform is None
    assert result.uses_lightspeed is False
    assert result.priority_score < 50  # Low score without tech signals


def test_location_count_affects_score():
    scorer = LeadScorer()

    lead_5_locations = {"location_count": 5, "technology_names": [], "marketplaces": "", "has_ecommerce": True, "contact_1_name": ""}
    lead_8_locations = {"location_count": 8, "technology_names": [], "marketplaces": "", "has_ecommerce": True, "contact_1_name": ""}

    score_5 = scorer.score(lead_5_locations)
    score_8 = scorer.score(lead_8_locations)

    # 3-5 locations scores higher than 6-10
    assert score_5.priority_score > score_8.priority_score


def test_multiple_marketplaces_bonus():
    scorer = LeadScorer()

    lead_one_mp = {"location_count": 5, "technology_names": [], "marketplaces": "Amazon", "has_ecommerce": True, "contact_1_name": ""}
    lead_two_mp = {"location_count": 5, "technology_names": [], "marketplaces": "Amazon, Etsy", "has_ecommerce": True, "contact_1_name": ""}

    score_one = scorer.score(lead_one_mp)
    score_two = scorer.score(lead_two_mp)

    assert score_two.priority_score > score_one.priority_score


def test_score_leads_sorts_by_priority():
    scorer = LeadScorer()

    leads = [
        {"brand_name": "Low Score", "location_count": 3, "technology_names": [], "marketplaces": "", "has_ecommerce": True, "contact_1_name": ""},
        {"brand_name": "High Score", "location_count": 5, "technology_names": ["Lightspeed"], "marketplaces": "Amazon", "has_ecommerce": True, "contact_1_name": "John"},
        {"brand_name": "Medium Score", "location_count": 4, "technology_names": ["Square"], "marketplaces": "", "has_ecommerce": True, "contact_1_name": "Jane"},
    ]

    scored = scorer.score_leads(leads)

    # Should be sorted by priority_score descending
    assert scored[0]["brand_name"] == "High Score"
    assert scored[0]["priority_score"] > scored[1]["priority_score"]
    assert scored[1]["priority_score"] > scored[2]["priority_score"]

    # Should have scoring fields added
    assert "pos_platform" in scored[0]
    assert "uses_lightspeed" in scored[0]
    assert "detected_marketplaces" in scored[0]
    assert "priority_score" in scored[0]
