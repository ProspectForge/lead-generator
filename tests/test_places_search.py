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


# Nearby Search Tests
@pytest.fixture
def mock_nearby_response():
    return {
        "places": [
            {
                "displayName": {"text": "Local Running Store"},
                "formattedAddress": "456 Suburb Ave, Chicago, IL 60601",
                "websiteUri": "https://localrunning.com",
                "id": "nearby123",
                "location": {"latitude": 41.8781, "longitude": -87.6298}
            }
        ]
    }

@pytest.mark.asyncio
async def test_nearby_search_returns_results(mock_nearby_response):
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_nearby_response

        results = await searcher.nearby_search(
            latitude=41.8781,
            longitude=-87.6298,
            radius_meters=5000,
            included_types=["sporting_goods_store"],
            vertical="sporting_goods"
        )

        assert len(results) == 1
        assert results[0].name == "Local Running Store"
        assert results[0].place_id == "nearby123"

@pytest.mark.asyncio
async def test_nearby_search_uses_correct_endpoint():
    searcher = PlacesSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"places": []}

        await searcher.nearby_search(
            latitude=41.8781,
            longitude=-87.6298,
            radius_meters=5000,
            included_types=["sporting_goods_store"]
        )

        # Verify the payload structure
        call_args = mock_request.call_args
        payload = call_args[0][0]
        assert "locationRestriction" in payload
        assert payload["locationRestriction"]["circle"]["radius"] == 5000


# Grid Point Generation Tests

def test_generate_cardinal_grid_points():
    """Should generate center + 4 cardinal offset points."""
    points = PlacesSearcher.generate_grid_points(
        center_lat=41.8781,
        center_lng=-87.6298,
        offset_km=20,
        mode="cardinal"
    )
    assert len(points) == 5
    # First point should be center
    assert points[0] == (41.8781, -87.6298)
    # North point should have higher latitude
    assert points[1][0] > 41.8781
    assert abs(points[1][1] - (-87.6298)) < 0.001  # Same longitude
    # South point should have lower latitude
    assert points[2][0] < 41.8781
    # East point should have higher longitude (less negative)
    assert points[3][1] > -87.6298
    # West point should have lower longitude (more negative)
    assert points[4][1] < -87.6298


def test_generate_full_grid_points():
    """Should generate center + 8 surrounding points."""
    points = PlacesSearcher.generate_grid_points(
        center_lat=41.8781,
        center_lng=-87.6298,
        offset_km=20,
        mode="full"
    )
    assert len(points) == 9


def test_grid_points_offset_distance():
    """Offset points should be approximately the requested distance."""
    import math
    center_lat, center_lng = 41.8781, -87.6298
    points = PlacesSearcher.generate_grid_points(
        center_lat=center_lat,
        center_lng=center_lng,
        offset_km=20,
        mode="cardinal"
    )
    # Check north point is ~20km away
    north_lat, north_lng = points[1]
    # 1 degree latitude ~= 111km
    lat_diff_km = abs(north_lat - center_lat) * 111
    assert 18 < lat_diff_km < 22  # Allow ~10% tolerance
