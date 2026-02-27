# tests/test_places_search.py
"""Tests for SerpAPI Google Maps search (replaces Google Places API)."""
import json
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.serpapi_search import SerpApiSearcher, PlaceResult


@pytest.fixture
def searcher(tmp_path):
    s = SerpApiSearcher(api_key="test_key")
    s.CACHE_DIR = tmp_path / "search_cache"
    s.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return s


@pytest.fixture
def mock_serpapi_response():
    return {
        "local_results": [
            {
                "title": "Lululemon Athletica",
                "address": "123 Main St, New York, NY 10001",
                "website": "https://lululemon.com",
                "place_id": "place123"
            },
            {
                "title": "Nike Store",
                "address": "456 Broadway, New York, NY 10002",
                "website": "https://nike.com",
                "place_id": "place456"
            }
        ]
    }


# ═══════════════════════════════════════════════════════════════════
# Basic search
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_search_places_returns_results(mock_serpapi_response):
    searcher = SerpApiSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_serpapi_response
        results = await searcher.search("clothing boutique", "New York, NY")

    assert len(results) == 2
    assert results[0].name == "Lululemon Athletica"
    assert results[0].website == "https://lululemon.com"


@pytest.mark.asyncio
async def test_search_places_handles_empty_response():
    searcher = SerpApiSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock) as mock_request:
        mock_request.return_value = {"local_results": []}
        results = await searcher.search("rare store type", "Small Town, USA")

    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_passes_vertical_to_results(searcher):
    mock_data = {
        "local_results": [
            {"title": "S", "address": "1 St, City, ST", "place_id": "x"}
        ]
    }

    with patch.object(searcher, '_make_request', new_callable=AsyncMock, return_value=mock_data):
        results = await searcher.search("query", "City, ST", vertical="health_wellness")

    assert results[0].vertical == "health_wellness"


@pytest.mark.asyncio
async def test_search_handles_missing_fields(searcher):
    mock_data = {
        "local_results": [
            {"title": "Minimal"},
        ]
    }

    with patch.object(searcher, '_make_request', new_callable=AsyncMock, return_value=mock_data):
        results = await searcher.search("query", "City")

    assert len(results) == 1
    assert results[0].address == ""
    assert results[0].website is None
    assert results[0].place_id == ""


@pytest.mark.asyncio
async def test_search_handles_no_local_results_key(searcher):
    mock_data = {"search_information": {"total_results": 0}}

    with patch.object(searcher, '_make_request', new_callable=AsyncMock, return_value=mock_data):
        results = await searcher.search("query", "City")

    assert results == []


# ═══════════════════════════════════════════════════════════════════
# Nearby search
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_nearby_search_returns_results():
    searcher = SerpApiSearcher(api_key="test_key")
    mock_data = {
        "local_results": [
            {"title": "Local Running Store", "address": "456 Suburb Ave, Chicago, IL 60601",
             "website": "https://localrunning.com", "place_id": "nearby123"}
        ]
    }

    with patch.object(searcher, '_make_request', new_callable=AsyncMock, return_value=mock_data):
        results = await searcher.nearby_search(
            latitude=41.8781, longitude=-87.6298,
            radius_meters=5000, included_types=["sporting goods store"], vertical="sporting_goods"
        )

    assert len(results) == 1
    assert results[0].name == "Local Running Store"


@pytest.mark.asyncio
async def test_nearby_search_sends_ll_param():
    searcher = SerpApiSearcher(api_key="test_key")

    with patch.object(searcher, '_make_request', new_callable=AsyncMock, return_value={"local_results": []}) as mock_req:
        await searcher.nearby_search(41.8781, -87.6298, radius_meters=5000, included_types=["sporting goods store"])

    params = mock_req.call_args[0][0]
    assert "ll" in params
    assert "41.8781" in params["ll"]
    assert "-87.6298" in params["ll"]


@pytest.mark.asyncio
async def test_nearby_search_uses_included_types(searcher):
    captured_params = {}

    async def capture_params(params):
        captured_params.update(params)
        return {"local_results": []}

    with patch.object(searcher, '_make_request', side_effect=capture_params):
        await searcher.nearby_search(42.0, -71.0, included_types=["running store", "athletic store"])

    assert captured_params["q"] == "running store"


@pytest.mark.asyncio
async def test_nearby_search_falls_back_to_vertical(searcher):
    captured_params = {}

    async def capture_params(params):
        captured_params.update(params)
        return {"local_results": []}

    with patch.object(searcher, '_make_request', side_effect=capture_params):
        await searcher.nearby_search(42.0, -71.0, vertical="health_wellness")

    assert captured_params["q"] == "health food store"


@pytest.mark.asyncio
async def test_nearby_search_falls_back_to_retail_store(searcher):
    captured_params = {}

    async def capture_params(params):
        captured_params.update(params)
        return {"local_results": []}

    with patch.object(searcher, '_make_request', side_effect=capture_params):
        await searcher.nearby_search(42.0, -71.0)

    assert captured_params["q"] == "retail store"


# ═══════════════════════════════════════════════════════════════════
# Grid point generation
# ═══════════════════════════════════════════════════════════════════

def test_generate_cardinal_grid_points():
    points = SerpApiSearcher.generate_grid_points(41.8781, -87.6298, offset_km=20, mode="cardinal")
    assert len(points) == 5
    assert points[0] == (41.8781, -87.6298)
    assert points[1][0] > 41.8781  # North
    assert points[2][0] < 41.8781  # South
    assert points[3][1] > -87.6298  # East
    assert points[4][1] < -87.6298  # West


def test_generate_full_grid_points():
    points = SerpApiSearcher.generate_grid_points(41.8781, -87.6298, offset_km=20, mode="full")
    assert len(points) == 9


def test_grid_points_offset_distance():
    center_lat, center_lng = 41.8781, -87.6298
    points = SerpApiSearcher.generate_grid_points(center_lat, center_lng, offset_km=20, mode="cardinal")
    north_lat, _ = points[1]
    lat_diff_km = abs(north_lat - center_lat) * 111
    assert 18 < lat_diff_km < 22


def test_grid_points_center_is_first():
    center = (42.0, -71.0)
    points = SerpApiSearcher.generate_grid_points(*center, offset_km=10, mode="cardinal")
    assert points[0] == center


# ═══════════════════════════════════════════════════════════════════
# Retail types coverage
# ═══════════════════════════════════════════════════════════════════

def test_retail_types_covers_all_verticals():
    expected_verticals = {
        "sporting_goods", "health_wellness", "apparel", "outdoor_camping",
        "pet_supplies", "beauty_cosmetics", "specialty_food",
        "running_athletic", "cycling", "baby_kids", "home_goods"
    }
    assert set(SerpApiSearcher.RETAIL_TYPES.keys()) == expected_verticals
    for vertical, types in SerpApiSearcher.RETAIL_TYPES.items():
        assert len(types) >= 1, f"{vertical} has no types"


# ═══════════════════════════════════════════════════════════════════
# Radius to zoom
# ═══════════════════════════════════════════════════════════════════

def test_radius_to_zoom():
    assert SerpApiSearcher._radius_to_zoom(500) == 15
    assert SerpApiSearcher._radius_to_zoom(1000) == 15
    assert SerpApiSearcher._radius_to_zoom(2000) == 14
    assert SerpApiSearcher._radius_to_zoom(4000) == 13
    assert SerpApiSearcher._radius_to_zoom(5000) == 13
    assert SerpApiSearcher._radius_to_zoom(8000) == 12
    assert SerpApiSearcher._radius_to_zoom(10000) == 12
    assert SerpApiSearcher._radius_to_zoom(15000) == 11
    assert SerpApiSearcher._radius_to_zoom(25000) == 11
    assert SerpApiSearcher._radius_to_zoom(40000) == 10
    assert SerpApiSearcher._radius_to_zoom(50000) == 10
    assert SerpApiSearcher._radius_to_zoom(100000) == 9


# ═══════════════════════════════════════════════════════════════════
# Cache — TTL
# ═══════════════════════════════════════════════════════════════════

def test_cache_ttl_default_is_90_days():
    assert SerpApiSearcher.DEFAULT_CACHE_TTL_DAYS == 90


def test_custom_cache_ttl():
    s = SerpApiSearcher(api_key="key", cache_ttl_days=7)
    assert s.cache_ttl_seconds == 7 * 86400


# ═══════════════════════════════════════════════════════════════════
# Cache — key generation
# ═══════════════════════════════════════════════════════════════════

def test_cache_key_deterministic(searcher):
    params1 = {"q": "running store in Boston", "type": "search", "engine": "google_maps"}
    params2 = {"q": "running store in Boston", "type": "search", "engine": "google_maps"}
    assert searcher._cache_key(params1) == searcher._cache_key(params2)


def test_cache_key_excludes_api_key(searcher):
    params_with = {"q": "test", "api_key": "secret123"}
    params_without = {"q": "test"}
    assert searcher._cache_key(params_with) == searcher._cache_key(params_without)


def test_cache_key_order_independent(searcher):
    params1 = {"q": "test", "type": "search", "engine": "google_maps"}
    params2 = {"engine": "google_maps", "q": "test", "type": "search"}
    assert searcher._cache_key(params1) == searcher._cache_key(params2)


def test_cache_key_different_params_differ(searcher):
    key1 = searcher._cache_key({"q": "running store in Boston"})
    key2 = searcher._cache_key({"q": "running store in Denver"})
    assert key1 != key2


# ═══════════════════════════════════════════════════════════════════
# Cache — hit/miss/expiry
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_search_uses_cache(searcher):
    params = {"q": "running store in Boston, MA", "type": "search", "engine": "google_maps"}
    mock_response = {"local_results": [{"title": "Cached", "address": "1 St", "place_id": "c1"}]}
    searcher._set_cached(params, mock_response)

    with patch("httpx.AsyncClient") as mock_client:
        result = await searcher._make_request(params)

    assert result == mock_response
    mock_client.assert_not_called()


def test_cache_expires(searcher):
    params = {"q": "test", "engine": "google_maps"}
    searcher._set_cached(params, {"local_results": []})

    key = searcher._cache_key(params)
    cache_file = searcher.CACHE_DIR / f"{key}.json"
    data = json.loads(cache_file.read_text())
    data["_cached_at"] = time.time() - (91 * 86400)
    cache_file.write_text(json.dumps(data))

    assert searcher._get_cached(params) is None


def test_cache_valid_at_89_days(searcher):
    params = {"q": "test", "engine": "google_maps"}
    searcher._set_cached(params, {"local_results": []})

    key = searcher._cache_key(params)
    cache_file = searcher.CACHE_DIR / f"{key}.json"
    data = json.loads(cache_file.read_text())
    data["_cached_at"] = time.time() - (89 * 86400)
    cache_file.write_text(json.dumps(data))

    assert searcher._get_cached(params) is not None


def test_cache_corrupted_json_returns_none(searcher):
    params = {"q": "test", "engine": "google_maps"}
    key = searcher._cache_key(params)
    cache_file = searcher.CACHE_DIR / f"{key}.json"
    cache_file.write_text("{corrupt json")
    assert searcher._get_cached(params) is None


def test_cache_miss_returns_none(searcher):
    params = {"q": "never-seen-before", "engine": "google_maps"}
    assert searcher._get_cached(params) is None


# ═══════════════════════════════════════════════════════════════════
# Retry logic
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_retries_on_429(searcher):
    import httpx

    call_count = 0
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"local_results": []}
    mock_response_ok.raise_for_status = MagicMock()

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response_429)
        return mock_response_ok

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result = await searcher._make_request({"q": "test", "engine": "google_maps"})

    assert result == {"local_results": []}
    assert call_count == 3


@pytest.mark.asyncio
async def test_retries_on_timeout(searcher):
    import httpx

    call_count = 0
    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"local_results": []}
    mock_response_ok.raise_for_status = MagicMock()

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.TimeoutException("Timeout")
        return mock_response_ok

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result = await searcher._make_request({"q": "test", "engine": "google_maps"})

    assert call_count == 2


@pytest.mark.asyncio
async def test_non_retryable_error_propagates(searcher):
    import httpx

    mock_response_400 = MagicMock()
    mock_response_400.status_code = 400

    async def mock_get(url, **kwargs):
        raise httpx.HTTPStatusError("400", request=MagicMock(), response=mock_response_400)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await searcher._make_request({"q": "test", "engine": "google_maps"})


@pytest.mark.asyncio
async def test_retries_on_500(searcher):
    import httpx

    call_count = 0
    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.json.return_value = {"local_results": []}
    mock_ok.raise_for_status = MagicMock()

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.HTTPStatusError("500", request=MagicMock(), response=mock_500)
        return mock_ok

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result = await searcher._make_request({"q": "test", "engine": "google_maps"})

    assert call_count == 2


# ═══════════════════════════════════════════════════════════════════
# City extraction
# ═══════════════════════════════════════════════════════════════════

def test_extract_city_from_address_multi_comma():
    result = SerpApiSearcher._extract_city_from_address("123 Main St, Boston, MA 02101, USA")
    assert result == "MA 02101"


def test_extract_city_from_address_two_parts():
    result = SerpApiSearcher._extract_city_from_address("123 Main St, Boston")
    assert result == "123 Main St"


def test_extract_city_from_address_empty():
    assert SerpApiSearcher._extract_city_from_address("") == ""


def test_extract_city_from_address_no_comma():
    assert SerpApiSearcher._extract_city_from_address("Some Place") == ""
