# tests/test_apollo_enrich.py
import pytest
from unittest.mock import AsyncMock, patch
from src.apollo_enrich import ApolloEnricher, ApolloCompany, ApolloContact, ApolloEnrichment


@pytest.fixture
def mock_company_response():
    return {
        "organization": {
            "name": "Fleet Feet",
            "primary_domain": "fleetfeet.com",
            "industry": "Retail",
            "estimated_num_employees": 500,
            "annual_revenue_printed": "$50M-$100M",
            "linkedin_url": "https://linkedin.com/company/fleet-feet",
        }
    }


@pytest.fixture
def mock_people_response():
    return {
        "people": [
            {
                "name": "John Smith",
                "email": "john@fleetfeet.com",
                "phone_numbers": [{"sanitized_number": "+1234567890"}],
                "title": "CEO",
                "linkedin_url": "https://linkedin.com/in/johnsmith",
            },
            {
                "name": "Jane Doe",
                "email": "jane@fleetfeet.com",
                "phone_numbers": [],
                "title": "COO",
                "linkedin_url": "https://linkedin.com/in/janedoe",
            },
        ]
    }


@pytest.mark.asyncio
async def test_search_company_returns_company_data(mock_company_response):
    enricher = ApolloEnricher(api_key="test_key")

    with patch.object(enricher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_company_response

        company = await enricher.search_company("Fleet Feet", "https://fleetfeet.com")

        assert company is not None
        assert company.name == "Fleet Feet"
        assert company.employee_count == 500
        assert company.industry == "Retail"


@pytest.mark.asyncio
async def test_search_contacts_returns_contacts(mock_people_response):
    enricher = ApolloEnricher(api_key="test_key")

    with patch.object(enricher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_people_response

        contacts = await enricher.search_contacts("Fleet Feet", "https://fleetfeet.com")

        assert len(contacts) == 2
        assert contacts[0].name == "John Smith"
        assert contacts[0].email == "john@fleetfeet.com"
        assert contacts[1].title == "COO"


@pytest.mark.asyncio
async def test_enrich_returns_full_enrichment(mock_company_response, mock_people_response):
    enricher = ApolloEnricher(api_key="test_key")

    with patch.object(enricher, '_make_request', new_callable=AsyncMock) as mock_request:
        # First call for company, second for contacts
        mock_request.side_effect = [mock_company_response, mock_people_response]

        result = await enricher.enrich("Fleet Feet", "https://fleetfeet.com")

        assert result is not None
        assert result.company.name == "Fleet Feet"
        assert len(result.contacts) == 2
