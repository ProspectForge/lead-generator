# tests/test_quality_gate.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.pipeline import Pipeline
from src.linkedin_enrich import LinkedInCompanyData, Contact


@pytest.mark.asyncio
async def test_filters_by_apollo_location_count():
    """Leads with apollo_location_count > max are filtered out."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Flaman Fitness",
            "apollo_location_count": 36,
            "employee_count": "",
            "linkedin_company": "https://linkedin.com/company/flaman-fitness",
            "location_count": 6,
        },
        {
            "brand_name": "Good Store",
            "apollo_location_count": 5,
            "employee_count": "",
            "linkedin_company": "",
            "location_count": 5,
        },
    ]

    result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["brand_name"] == "Good Store"


@pytest.mark.asyncio
async def test_filters_by_employee_count():
    """Leads with employee_count > max are filtered out when no location data."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Big Corp",
            "apollo_location_count": None,
            "employee_count": 1500,
            "linkedin_company": "",
            "location_count": 4,
        },
        {
            "brand_name": "Small Biz",
            "apollo_location_count": None,
            "employee_count": 30,
            "linkedin_company": "",
            "location_count": 4,
        },
    ]

    result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["brand_name"] == "Small Biz"


@pytest.mark.asyncio
async def test_filters_by_linkedin_location_count():
    """When Apollo location is null, falls back to LinkedIn scrape."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Chain Store",
            "apollo_location_count": None,
            "employee_count": "",
            "linkedin_company": "https://linkedin.com/company/chain-store",
            "location_count": 7,
        },
    ]

    mock_linkedin_data = LinkedInCompanyData(
        location_count=25,
        employee_range="201-500",
        industry="Retail",
        people=[Contact(name="Boss Man", title="CEO", linkedin_url="https://linkedin.com/in/boss")],
    )

    with patch("src.pipeline.LinkedInEnricher") as mock_enricher_cls:
        mock_enricher = MagicMock()
        mock_enricher.scrape_company_page = AsyncMock(return_value=mock_linkedin_data)
        mock_enricher_cls.return_value = mock_enricher

        result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_linkedin_supplements_contacts():
    """LinkedIn people data fills empty contact slots."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Small Chain",
            "apollo_location_count": 5,
            "employee_count": 40,
            "linkedin_company": "https://linkedin.com/company/small-chain",
            "location_count": 5,
            "contact_1_name": "Existing Contact",
            "contact_1_title": "CEO",
            "contact_1_email": "ceo@small.com",
            "contact_1_phone": "555-1234",
            "contact_1_linkedin": "",
            "contact_2_name": "",
            "contact_2_title": "",
            "contact_2_email": "",
            "contact_2_phone": "",
            "contact_2_linkedin": "",
            "contact_3_name": "",
            "contact_3_title": "",
            "contact_3_email": "",
            "contact_3_phone": "",
            "contact_3_linkedin": "",
            "contact_4_name": "",
            "contact_4_title": "",
            "contact_4_email": "",
            "contact_4_phone": "",
            "contact_4_linkedin": "",
        },
    ]

    mock_linkedin_data = LinkedInCompanyData(
        location_count=5,
        employee_range="11-50",
        industry="Retail",
        people=[
            Contact(name="LI Person A", title="COO", linkedin_url="https://linkedin.com/in/a"),
            Contact(name="LI Person B", title="Director", linkedin_url="https://linkedin.com/in/b"),
        ],
    )

    with patch("src.pipeline.LinkedInEnricher") as mock_enricher_cls:
        mock_enricher = MagicMock()
        mock_enricher.scrape_company_page = AsyncMock(return_value=mock_linkedin_data)
        mock_enricher.find_contacts = AsyncMock(return_value=[
            Contact(name="LI Person A", title="COO", linkedin_url="https://linkedin.com/in/a"),
            Contact(name="LI Person B", title="Director", linkedin_url="https://linkedin.com/in/b"),
        ])
        mock_enricher_cls.return_value = mock_enricher

        result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["contact_1_name"] == "Existing Contact"  # Not overwritten
    assert result[0]["contact_2_name"] == "LI Person A"
    assert result[0]["contact_3_name"] == "LI Person B"


@pytest.mark.asyncio
async def test_no_data_passes_through():
    """Leads with no Apollo or LinkedIn data pass through."""
    pipeline = Pipeline()
    leads = [
        {
            "brand_name": "Unknown Store",
            "apollo_location_count": None,
            "employee_count": "",
            "linkedin_company": "",
            "location_count": 5,
        },
    ]

    result = await pipeline.stage_4b_quality_gate(leads)

    assert len(result) == 1
    assert result[0]["brand_name"] == "Unknown Store"
