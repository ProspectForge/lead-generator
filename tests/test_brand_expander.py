# tests/test_brand_expander.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.brand_expander import BrandExpander
from src.places_search import PlaceResult

@pytest.fixture
def mock_search_results():
    return {
        "Toronto, ON": [
            PlaceResult(name="Fleet Feet Toronto", address="123 Queen St", website="https://fleetfeet.com", place_id="tor1", city="Toronto, ON", vertical="running")
        ],
        "Vancouver, BC": [
            PlaceResult(name="Fleet Feet Vancouver", address="456 Robson St", website="https://fleetfeet.com", place_id="van1", city="Vancouver, BC", vertical="running")
        ],
        "Montreal, QC": []  # No results
    }

@pytest.mark.asyncio
async def test_expand_brand_searches_all_cities(mock_search_results):
    expander = BrandExpander(api_key="test_key")
    cities = ["Toronto, ON", "Vancouver, BC", "Montreal, QC"]

    async def mock_search(query, city, vertical=""):
        return mock_search_results.get(city, [])

    with patch.object(expander.searcher, 'search', side_effect=mock_search):
        results = await expander.expand_brand(
            brand_name="Fleet Feet",
            known_website="https://fleetfeet.com",
            cities=cities,
            vertical="running"
        )

        assert len(results) == 2  # Found in 2 of 3 cities
        assert all("fleet" in r["name"].lower() for r in results)

@pytest.mark.asyncio
async def test_expand_brand_filters_by_domain():
    expander = BrandExpander(api_key="test_key")

    mixed_results = [
        PlaceResult(name="Fleet Feet", address="123 St", website="https://fleetfeet.com", place_id="a", city="NYC", vertical="running"),
        PlaceResult(name="Other Running Store", address="456 St", website="https://other.com", place_id="b", city="NYC", vertical="running"),
    ]

    with patch.object(expander.searcher, 'search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mixed_results

        results = await expander.expand_brand(
            brand_name="Fleet Feet",
            known_website="https://fleetfeet.com",
            cities=["New York, NY"],
            vertical="running"
        )

        # Should only return the Fleet Feet result
        assert len(results) == 1
        assert "fleetfeet.com" in results[0]["website"]
