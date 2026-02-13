# tests/test_scraper_base.py
import pytest
from unittest.mock import AsyncMock, patch
from src.scraper.base import BaseScraper, ScrapedBrand

@pytest.mark.asyncio
async def test_scraper_fetches_and_parses():
    class TestScraper(BaseScraper):
        async def scrape(self) -> list[ScrapedBrand]:
            html = await self._fetch("https://example.com")
            return [ScrapedBrand(name="Test Brand", category="sporting_goods", website="https://test.com", source="test")]

    scraper = TestScraper(firecrawl_api_key="test_key")

    with patch.object(scraper, '_fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "<html><body>Test</body></html>"

        results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].name == "Test Brand"

def test_scraped_brand_to_dict():
    brand = ScrapedBrand(
        name="Fleet Feet",
        category="running",
        website="https://fleetfeet.com",
        source="franchise_directory",
        estimated_locations=50
    )

    d = brand.to_dict()

    assert d["name"] == "Fleet Feet"
    assert d["source"] == "franchise_directory"
    assert d["estimated_locations"] == 50
