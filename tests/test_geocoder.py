# tests/test_geocoder.py
import pytest
from unittest.mock import AsyncMock, patch
from src.geocoder import CityGeocoder


@pytest.mark.asyncio
async def test_geocode_city_returns_coordinates():
    """Should return lat/lng for a city string."""
    geocoder = CityGeocoder(api_key="test_key")

    mock_response = {
        "results": [{
            "geometry": {"location": {"lat": 41.8781, "lng": -87.6298}}
        }]
    }

    with patch.object(geocoder, '_geocode_api', new_callable=AsyncMock) as mock_api:
        mock_api.return_value = mock_response
        lat, lng = await geocoder.geocode("Chicago, IL")

    assert abs(lat - 41.8781) < 0.01
    assert abs(lng - (-87.6298)) < 0.01


@pytest.mark.asyncio
async def test_geocode_uses_cache():
    """Should return cached coordinates without API call."""
    geocoder = CityGeocoder(api_key="test_key")
    geocoder._cache = {"Chicago, IL": (41.8781, -87.6298)}

    with patch.object(geocoder, '_geocode_api', new_callable=AsyncMock) as mock_api:
        lat, lng = await geocoder.geocode("Chicago, IL")
        mock_api.assert_not_called()

    assert lat == 41.8781


@pytest.mark.asyncio
async def test_geocode_batch():
    """Should geocode a list of cities, using cache when available."""
    geocoder = CityGeocoder(api_key="test_key")
    geocoder._cache = {"Boston, MA": (42.3601, -71.0589)}

    mock_response = {
        "results": [{
            "geometry": {"location": {"lat": 40.7128, "lng": -74.0060}}
        }]
    }

    with patch.object(geocoder, '_geocode_api', new_callable=AsyncMock) as mock_api:
        mock_api.return_value = mock_response
        # Also patch _save_cache to avoid file writes during tests
        with patch.object(geocoder, '_save_cache'):
            results = await geocoder.geocode_batch(["Boston, MA", "New York, NY"])

    assert "Boston, MA" in results
    assert "New York, NY" in results
    # Only New York should have triggered an API call
    mock_api.assert_called_once()
