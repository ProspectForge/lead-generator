# tests/test_linkedin_enrich.py
import pytest
from unittest.mock import AsyncMock, patch
from src.linkedin_enrich import LinkedInEnricher, Contact, LinkedInCompanyData

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
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_search_linkedin', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = "https://linkedin.com/company/lululemon"

        result = await enricher.find_company("Lululemon", "https://lululemon.com")

        assert result == "https://linkedin.com/company/lululemon"

@pytest.mark.asyncio
async def test_finds_contacts_by_title():
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            Contact(name="John Smith", title="CEO", linkedin_url="https://linkedin.com/in/johnsmith"),
            Contact(name="Jane Doe", title="COO", linkedin_url="https://linkedin.com/in/janedoe"),
        ]

        contacts = await enricher.find_contacts("Lululemon", max_contacts=4)

        assert len(contacts) == 2
        assert contacts[0].title == "CEO"


@pytest.fixture
def linkedin_company_page_markdown():
    """Realistic LinkedIn company page markdown."""
    return """
# Flaman Fitness

## About

Flaman Fitness is a leading Canadian retailer of fitness equipment.

**Industry:** Retail
**Company size:** 201-500 employees
**Headquarters:** Saskatoon, Saskatchewan
**Founded:** 1959

**Specialties:** Fitness Equipment, Treadmills, Exercise Bikes

36 locations

## People

### Leadership

[**John Macdonell**](https://www.linkedin.com/in/john-macdonell)
CEO

[**Sarah Thompson**](https://www.linkedin.com/in/sarah-thompson-fitness)
Chief Operating Officer

[**Mike Rodriguez**](https://www.linkedin.com/in/mike-rodriguez-ab)
Director of Operations

[**Lisa Chen**](https://www.linkedin.com/in/lisa-chen-retail)
Marketing Manager
"""


@pytest.fixture
def linkedin_page_no_locations():
    """LinkedIn page without location count."""
    return """
# Small Store Co

## About

**Industry:** Retail
**Company size:** 11-50 employees

## People

[**Jane Owner**](https://www.linkedin.com/in/jane-owner)
Founder & CEO
"""


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_locations(linkedin_company_page_markdown):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert result.location_count == 36


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_people(linkedin_company_page_markdown):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert len(result.people) >= 3
    # Check first person
    assert result.people[0].name == "John Macdonell"
    assert "CEO" in result.people[0].title


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_employee_range(linkedin_company_page_markdown):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert result.employee_range == "201-500"


@pytest.mark.asyncio
async def test_scrape_company_page_handles_missing_locations(linkedin_page_no_locations):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_page_no_locations

        result = await enricher.scrape_company_page("https://linkedin.com/company/small-store")

    assert result.location_count is None
    assert len(result.people) >= 1


@pytest.mark.asyncio
async def test_scrape_company_page_handles_fetch_failure():
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("Connection failed")

        result = await enricher.scrape_company_page("https://linkedin.com/company/broken")

    assert result.location_count is None
    assert result.people == []
