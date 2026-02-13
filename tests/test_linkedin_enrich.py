# tests/test_linkedin_enrich.py
import pytest
from unittest.mock import AsyncMock, patch
from src.linkedin_enrich import LinkedInEnricher, Contact

@pytest.fixture
def mock_company_page():
    return {
        "data": {
            "markdown": """
            # Lululemon on LinkedIn

            linkedin.com/company/lululemon

            ## People
            - John Smith - CEO
            - Jane Doe - COO
            - Bob Wilson - Operations Manager
            """
        }
    }

@pytest.mark.asyncio
async def test_finds_company_linkedin_page(mock_company_page):
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_search_linkedin', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = "https://linkedin.com/company/lululemon"

        result = await enricher.find_company("Lululemon", "https://lululemon.com")

        assert result == "https://linkedin.com/company/lululemon"

@pytest.mark.asyncio
async def test_finds_contacts_by_title():
    enricher = LinkedInEnricher(api_key="test_key")

    with patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            Contact(name="John Smith", title="CEO", linkedin_url="https://linkedin.com/in/johnsmith"),
            Contact(name="Jane Doe", title="COO", linkedin_url="https://linkedin.com/in/janedoe"),
        ]

        contacts = await enricher.find_contacts("Lululemon", max_contacts=4)

        assert len(contacts) == 2
        assert contacts[0].title == "CEO"
