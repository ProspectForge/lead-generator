# tests/test_config.py
import pytest
from src.config import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test_serpapi_key")

    settings = Settings()

    assert settings.serpapi_api_key == "test_serpapi_key"

def test_settings_loads_cities_config():
    settings = Settings()

    assert "us" in settings.cities
    assert "canada" in settings.cities
    # Expanded city lists: ~780 US cities and ~125 Canada cities (pop >= 50k)
    assert len(settings.cities["us"]) >= 700
    assert len(settings.cities["canada"]) >= 100

def test_settings_loads_search_queries():
    settings = Settings()

    assert "health_wellness" in settings.search_queries
    assert "sporting_goods" in settings.search_queries
    assert "apparel" in settings.search_queries

def test_settings_loads_quality_gate_config():
    settings = Settings()

    assert settings.quality_gate_max_locations == 10
    assert settings.quality_gate_max_employees == 500

def test_settings_loads_health_check_config():
    settings = Settings()

    assert settings.health_check_concurrency == 50

def test_discovery_settings_loaded():
    """Discovery nearby grid settings should load from config."""
    from src.config import Settings
    s = Settings()
    assert hasattr(s, 'discovery')
    assert s.discovery.nearby_grid_enabled is True
    assert s.discovery.nearby_grid_offset_km == 20
    assert s.discovery.nearby_grid_radius_meters == 15000
    assert s.discovery.nearby_grid_points == "cardinal"

def test_ecommerce_playwright_fallback_settings():
    """Playwright fallback settings should load from config."""
    from src.config import Settings
    s = Settings()
    assert s.ecommerce_playwright_fallback_enabled is True
    assert s.ecommerce_playwright_fallback_max_percent == 20
    assert s.ecommerce_playwright_fallback_timeout == 15

def test_settings_loads_search_mode():
    settings = Settings()
    assert settings.search_mode in ("lean", "extended")

def test_settings_loads_lean_cities():
    settings = Settings()
    assert "us" in settings.lean_cities
    assert "canada" in settings.lean_cities
    assert len(settings.lean_cities["us"]) >= 40
    assert len(settings.lean_cities["canada"]) >= 10

def test_settings_loads_lean_queries():
    settings = Settings()
    assert "health_wellness" in settings.lean_queries
    assert len(settings.lean_queries["health_wellness"]) >= 2
    assert len(settings.lean_queries["health_wellness"]) <= 5

def test_settings_get_cities_for_mode_lean():
    settings = Settings()
    settings.search_mode = "lean"
    cities = settings.get_cities_for_mode()
    assert len(cities["us"]) < len(settings.cities["us"])

def test_settings_get_cities_for_mode_extended():
    settings = Settings()
    settings.search_mode = "extended"
    cities = settings.get_cities_for_mode()
    assert cities["us"] == settings.cities["us"]

def test_settings_get_queries_for_mode_lean():
    settings = Settings()
    settings.search_mode = "lean"
    queries = settings.get_queries_for_mode()
    assert len(queries["health_wellness"]) <= 5

def test_settings_get_queries_for_mode_extended():
    settings = Settings()
    settings.search_mode = "extended"
    queries = settings.get_queries_for_mode()
    assert len(queries["health_wellness"]) >= 10
