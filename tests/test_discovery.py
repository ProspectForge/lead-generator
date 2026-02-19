# tests/test_discovery.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.discovery import Discovery

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.serpapi_api_key = "test_key"
    settings.firecrawl_api_key = "test_key"
    settings.cities = {"us": ["Boston, MA"], "canada": ["Toronto, ON"]}
    settings.search_queries = {"running": ["running store"]}
    settings.search_concurrency = 2
    settings.search_mode = "extended"
    settings.lean_cities = {"us": ["Boston, MA"], "canada": []}
    settings.lean_queries = {"running": ["running store"]}
    settings.get_cities_for_mode = lambda: settings.cities
    settings.get_queries_for_mode = lambda: settings.search_queries
    return settings

@pytest.mark.asyncio
async def test_discovery_runs_search(mock_settings):
    discovery = Discovery(mock_settings)

    mock_results = [{"name": "Test Store", "city": "Boston, MA", "website": "https://test.com", "source": "serpapi"}]

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = mock_results
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    results = await discovery.run(verticals=["running"], countries=["us"])

                    mock_gp.assert_called_once()
                    assert len(results) >= 1

@pytest.mark.asyncio
async def test_discovery_runs_nearby_grid_search(mock_settings):
    """Discovery should run nearby grid search when enabled."""
    from unittest.mock import MagicMock
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
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    results = await discovery.run(verticals=["running"], countries=["us"])

                    mock_grid.assert_called_once()
                    assert len(results) >= 1


@pytest.mark.asyncio
async def test_discovery_deduplicates_results(mock_settings):
    discovery = Discovery(mock_settings)

    # Same store from two sources
    gp_results = [{"name": "Fleet Feet", "city": "Boston, MA", "website": "https://fleetfeet.com", "place_id": "abc", "source": "serpapi", "vertical": "running", "address": "123 St"}]
    scrape_results = [{"name": "Fleet Feet Boston", "city": "Boston, MA", "website": "https://fleetfeet.com", "place_id": None, "source": "bestof", "vertical": "running", "address": ""}]

    with patch.object(discovery, '_run_search', new_callable=AsyncMock) as mock_gp:
        mock_gp.return_value = gp_results
        with patch.object(discovery, '_run_nearby_grid_search', new_callable=AsyncMock) as mock_grid:
            mock_grid.return_value = []
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = scrape_results
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    results = await discovery.run(verticals=["running"], countries=["us"])

                    # Should dedupe to 1 result
                    assert len(results) == 1


@pytest.mark.asyncio
async def test_discovery_full_flow_with_grid_search(mock_settings):
    """Integration test: grid search results merge with text search results."""
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
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock, return_value=[]):
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock, return_value=[]):
                    results = await discovery.run(verticals=["running"], countries=["us"])

    assert len(results) == 2
    names = [r["name"] for r in results]
    assert "Downtown Store" in names
    assert "Suburb Store" in names


@pytest.mark.asyncio
async def test_discovery_lean_mode_skips_grid_search(mock_settings):
    """In lean mode, discovery should skip grid search."""
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
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    await discovery.run(verticals=["running"], countries=["us"])

                    # In lean mode, grid search should NOT be called
                    mock_grid.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_extended_mode_runs_grid_search(mock_settings):
    """In extended mode, discovery should run grid search."""
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
            with patch.object(discovery, '_run_scraping', new_callable=AsyncMock) as mock_scrape:
                mock_scrape.return_value = []
                with patch.object(discovery, '_run_brand_expansion', new_callable=AsyncMock) as mock_expand:
                    mock_expand.return_value = []

                    await discovery.run(verticals=["running"], countries=["us"])

                    # In extended mode, grid search SHOULD be called
                    mock_grid.assert_called_once()
