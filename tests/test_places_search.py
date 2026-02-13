# tests/test_places_search.py
import pytest
from unittest.mock import AsyncMock, patch
from src.places_search import PlacesSearcher, PlaceResult

@pytest.fixture
def mock_places_response():
    return {
        "places": [
            {
                "displayName": {"text": "Lululemon Athletica"},
                "formattedAddress": "123 Main St, New York, NY 10001",
                "websiteUri": "https://lululemon.com",
                "id": "place123"
            },
            {
                "displayName": {"text": "Nike Store"},
                "formattedAddress": "456 Broadway, New York, NY 10002",
                "websiteUri": "https://nike.com",
                "id": "place456"
            }
        ]
    }

@pytest.mark.asyncio
async def test_search_places_returns_results(mock_places_response):
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_places_response

        results = await searcher.search("clothing boutique", "New York, NY")

        assert len(results) == 2
        assert results[0].name == "Lululemon Athletica"
        assert results[0].website == "https://lululemon.com"

@pytest.mark.asyncio
async def test_search_places_handles_empty_response():
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"places": []}

        results = await searcher.search("rare store type", "Small Town, USA")

        assert len(results) == 0
