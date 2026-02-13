# tests/test_bestof_scraper.py
import pytest
from unittest.mock import AsyncMock, patch
from src.scraper.bestof_scraper import BestOfScraper

@pytest.fixture
def mock_search_results():
    return """
    # Best Running Stores in Boston

    1. **Marathon Sports** - The premier running store in New England
       Located at 123 Boylston St. marathonsports.com

    2. **Fleet Feet Boston** - Great selection of shoes
       Visit fleetfeet.com for more info

    3. **Heartbreak Hill Running** - Local favorite
       heartbreakhill.com
    """

@pytest.mark.asyncio
async def test_extracts_brand_names_from_article(mock_search_results):
    scraper = BestOfScraper(firecrawl_api_key="test_key")

    with patch.object(scraper, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_search_results

        results = await scraper.scrape_city("Boston, MA", "running store")

        assert len(results) >= 2
        names = [r.name.lower() for r in results]
        assert any("marathon" in n for n in names)

@pytest.mark.asyncio
async def test_extracts_websites_from_article(mock_search_results):
    scraper = BestOfScraper(firecrawl_api_key="test_key")

    with patch.object(scraper, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_search_results

        results = await scraper.scrape_city("Boston, MA", "running store")

        websites = [r.website for r in results if r.website]
        assert any("marathonsports.com" in w for w in websites)
