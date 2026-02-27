# tests/test_discovery.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.discovery import Discovery, _is_transient_error


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.serpapi_api_key = "test_key"
    settings.cities = {"us": ["Boston, MA"], "canada": ["Toronto, ON"]}
    settings.search_queries = {"running": ["running store"]}
    settings.search_concurrency = 2
    settings.search_mode = "extended"
    settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    settings.lean_queries = {"running": ["running store"]}
    settings.get_cities_for_mode = lambda: settings.cities
    settings.get_queries_for_mode = lambda: settings.search_queries
    return settings


# ═══════════════════════════════════════════════════════════════════
# Basic run
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_discovery_runs_search(mock_settings):
    discovery = Discovery(mock_settings)
    mock_results = [{"name": "Test Store", "city": "Boston, MA", "website": "https://test.com", "source": "serpapi"}]

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = mock_results
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                results = await discovery.run(verticals=["running"], countries=["us"])

                mock_gp.assert_called_once()
                assert len(results) >= 1


# ═══════════════════════════════════════════════════════════════════
# Grid search — mode-aware
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_discovery_runs_nearby_grid_search(mock_settings):
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True
    mock_settings.discovery.nearby_grid_offset_km = 20
    mock_settings.discovery.nearby_grid_radius_meters = 15000
    mock_settings.discovery.nearby_grid_points = "cardinal"

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = [
                {"name": "Suburb Store", "city": "Suburb, MA", "website": "https://suburb.com",
                 "place_id": "grid123", "vertical": "running", "address": "789 Suburb Rd", "source": "nearby_grid"}
            ]
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                results = await discovery.run(verticals=["running"], countries=["us"])

                mock_grid.assert_called_once()
                assert len(results) >= 1


@pytest.mark.asyncio
async def test_discovery_lean_mode_runs_grid_search_when_enabled(mock_settings):
    mock_settings.search_mode = "lean"
    mock_settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    mock_settings.lean_queries = {"running": ["running store"]}
    mock_settings.get_cities_for_mode = lambda: mock_settings.lean_cities
    mock_settings.get_queries_for_mode = lambda: mock_settings.lean_queries
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                await discovery.run(verticals=["running"], countries=["us"])

                # Grid search now runs in all modes when enabled
                mock_grid.assert_called_once()


@pytest.mark.asyncio
async def test_discovery_skips_grid_search_when_disabled(mock_settings):
    mock_settings.search_mode = "lean"
    mock_settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    mock_settings.lean_queries = {"running": ["running store"]}
    mock_settings.get_cities_for_mode = lambda: mock_settings.lean_cities
    mock_settings.get_queries_for_mode = lambda: mock_settings.lean_queries
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = False

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                await discovery.run(verticals=["running"], countries=["us"])

                mock_grid.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_extended_mode_runs_grid_search(mock_settings):
    mock_settings.search_mode = "extended"
    mock_settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    mock_settings.lean_queries = {"running": ["running store"]}
    mock_settings.get_cities_for_mode = lambda: mock_settings.cities
    mock_settings.get_queries_for_mode = lambda: mock_settings.search_queries
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True
    mock_settings.discovery.nearby_grid_offset_km = 20
    mock_settings.discovery.nearby_grid_radius_meters = 15000
    mock_settings.discovery.nearby_grid_points = "cardinal"

    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                await discovery.run(verticals=["running"], countries=["us"])

                mock_grid.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Deduplication
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_discovery_deduplicates_results(mock_settings):
    discovery = Discovery(mock_settings)

    gp_results = [{"name": "Fleet Feet", "city": "Boston, MA", "website": "https://fleetfeet.com", "place_id": "abc", "source": "serpapi", "vertical": "running", "address": "123 St"}]
    scrape_results = [{"name": "Fleet Feet Boston", "city": "Boston, MA", "website": "https://fleetfeet.com", "place_id": None, "source": "bestof", "vertical": "running", "address": ""}]

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = gp_results + scrape_results
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                mock_expand.return_value = []

                results = await discovery.run(verticals=["running"], countries=["us"])

                assert len(results) == 1


@pytest.mark.asyncio
async def test_discovery_full_flow_with_grid_search(mock_settings):
    mock_settings.discovery = MagicMock()
    mock_settings.discovery.nearby_grid_enabled = True
    mock_settings.discovery.nearby_grid_offset_km = 20
    mock_settings.discovery.nearby_grid_radius_meters = 15000
    mock_settings.discovery.nearby_grid_points = "cardinal"

    discovery = Discovery(mock_settings)

    text_results = [
        {"name": "Downtown Store", "city": "Boston, MA", "website": "https://downtown.com",
         "place_id": "text1", "vertical": "running", "address": "1 Main St", "source": "serpapi"}
    ]
    grid_results = [
        {"name": "Suburb Store", "city": "Cambridge, MA", "website": "https://suburb.com",
         "place_id": "grid1", "vertical": "running", "address": "2 Suburb Rd", "source": "nearby_grid"}
    ]

    with patch.object(discovery, '_run_search', new_callable=AsyncMock, return_value=text_results):
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock, return_value=grid_results):
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock, return_value=[]):
                results = await discovery.run(verticals=["running"], countries=["us"])

    assert len(results) == 2
    names = [r["name"] for r in results]
    assert "Downtown Store" in names
    assert "Suburb Store" in names


# ═══════════════════════════════════════════════════════════════════
# _build_city_list — mode-aware
# ═══════════════════════════════════════════════════════════════════

def test_build_city_list_uses_mode_cities(mock_settings):
    mock_settings.get_cities_for_mode = lambda: {"us": ["Boston, MA", "Denver, CO"], "canada": ["Toronto, ON"]}
    discovery = Discovery(mock_settings)
    cities = discovery._build_city_list(["us"])
    assert cities == ["Boston, MA", "Denver, CO"]


def test_build_city_list_multiple_countries(mock_settings):
    mock_settings.get_cities_for_mode = lambda: {"us": ["Boston, MA"], "canada": ["Toronto, ON"]}
    discovery = Discovery(mock_settings)
    cities = discovery._build_city_list(["us", "canada"])
    assert "Boston, MA" in cities
    assert "Toronto, ON" in cities


def test_build_city_list_unknown_country(mock_settings):
    mock_settings.get_cities_for_mode = lambda: {"us": ["Boston, MA"]}
    discovery = Discovery(mock_settings)
    cities = discovery._build_city_list(["uk"])
    assert cities == []


def test_build_city_list_empty_countries(mock_settings):
    discovery = Discovery(mock_settings)
    cities = discovery._build_city_list([])
    assert cities == []


# ═══════════════════════════════════════════════════════════════════
# _is_transient_error
# ═══════════════════════════════════════════════════════════════════

def test_transient_error_429():
    import httpx
    response = MagicMock()
    response.status_code = 429
    error = httpx.HTTPStatusError("429", request=MagicMock(), response=response)
    assert _is_transient_error(error) is True


def test_transient_error_503():
    import httpx
    response = MagicMock()
    response.status_code = 503
    error = httpx.HTTPStatusError("503", request=MagicMock(), response=response)
    assert _is_transient_error(error) is True


def test_transient_error_500():
    import httpx
    response = MagicMock()
    response.status_code = 500
    error = httpx.HTTPStatusError("500", request=MagicMock(), response=response)
    assert _is_transient_error(error) is True


def test_transient_error_timeout():
    import httpx
    error = httpx.TimeoutException("timeout")
    assert _is_transient_error(error) is True


def test_non_transient_error_400():
    import httpx
    response = MagicMock()
    response.status_code = 400
    error = httpx.HTTPStatusError("400", request=MagicMock(), response=response)
    assert _is_transient_error(error) is False


def test_non_transient_error_generic():
    error = ValueError("something went wrong")
    assert _is_transient_error(error) is False


# ═══════════════════════════════════════════════════════════════════
# _merged_to_dict
# ═══════════════════════════════════════════════════════════════════

def test_merged_to_dict(mock_settings):
    from src.deduplicator import MergedPlace
    discovery = Discovery(mock_settings)
    merged = MergedPlace(
        name="Test", address="123 St", website="https://test.com",
        place_id="abc", city="Boston", vertical="running"
    )
    result = discovery._merged_to_dict(merged)
    assert result["name"] == "Test"
    assert result["website"] == "https://test.com"
    assert result["place_id"] == "abc"
    assert result["city"] == "Boston"
    assert result["vertical"] == "running"


# ═══════════════════════════════════════════════════════════════════
# All stages empty
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_discovery_all_stages_empty(mock_settings):
    discovery = Discovery(mock_settings)

    with patch.object(discovery, '_run_search', new_callable=AsyncMock, return_value=[]):
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock, return_value=[]):
            with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock, return_value=[]):
                results = await discovery.run(verticals=["running"], countries=["us"])

    assert results == []


# ═══════════════════════════════════════════════════════════════════
# Brand expansion
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_brand_expansion_calls_expander(mock_settings):
    discovery = Discovery(mock_settings)

    places = [
        {"name": "Brand A", "website": "https://branda.com", "city": "Boston", "vertical": "running", "place_id": "1", "address": "1 St"},
        {"name": "Brand A Cambridge", "website": "https://branda.com", "city": "Cambridge", "vertical": "running", "place_id": "2", "address": "2 St"},
    ]

    expanded = [
        {"name": "Brand A Miami", "address": "3 St", "website": "https://branda.com",
         "place_id": None, "city": "Miami", "vertical": "running", "source": "location_scrape"}
    ]

    with patch.object(discovery.expander, 'should_expand', return_value=True):
        with patch.object(discovery.expander, 'expand_brand', new_callable=AsyncMock, return_value=expanded):
            results = await discovery._run_brand_expansion(places, ["us"])

    assert len(results) == 1
    assert results[0]["source"] == "location_scrape"


@pytest.mark.asyncio
async def test_brand_expansion_skips_no_website(mock_settings):
    discovery = Discovery(mock_settings)

    places = [
        {"name": "No Website", "website": None, "city": "Boston", "vertical": "running", "place_id": "1", "address": "1 St"},
        {"name": "No Website 2", "website": "", "city": "Denver", "vertical": "running", "place_id": "2", "address": "2 St"},
    ]

    results = await discovery._run_brand_expansion(places, ["us"])
    assert results == []


@pytest.mark.asyncio
async def test_brand_expansion_respects_limit(mock_settings):
    from src.discovery import BRANDS_TO_EXPAND_LIMIT
    discovery = Discovery(mock_settings)

    places = []
    for i in range(BRANDS_TO_EXPAND_LIMIT + 10):
        places.append({
            "name": f"Brand {i}", "website": f"https://brand{i}.com",
            "city": "Boston", "vertical": "running", "place_id": str(i), "address": f"{i} St"
        })
        places.append({
            "name": f"Brand {i} Denver", "website": f"https://brand{i}.com",
            "city": "Denver", "vertical": "running", "place_id": f"{i}b", "address": f"{i} St"
        })

    expand_call_count = 0

    async def mock_expand(*args, **kwargs):
        nonlocal expand_call_count
        expand_call_count += 1
        return []

    with patch.object(discovery.expander, 'should_expand', return_value=True):
        with patch.object(discovery.expander, 'expand_brand', side_effect=mock_expand):
            await discovery._run_brand_expansion(places, ["us"])

    assert expand_call_count <= BRANDS_TO_EXPAND_LIMIT


@pytest.mark.asyncio
async def test_brand_expansion_handles_exception(mock_settings):
    """Expansion errors should be caught and logged, not crash."""
    discovery = Discovery(mock_settings)

    places = [
        {"name": "Error Brand", "website": "https://error.com", "city": "Boston", "vertical": "running", "place_id": "1", "address": "1 St"},
        {"name": "Error Brand 2", "website": "https://error.com", "city": "Denver", "vertical": "running", "place_id": "2", "address": "2 St"},
    ]

    with patch.object(discovery.expander, 'should_expand', return_value=True):
        with patch.object(discovery.expander, 'expand_brand', new_callable=AsyncMock, side_effect=Exception("scrape failed")):
            results = await discovery._run_brand_expansion(places, ["us"])

    assert results == []
