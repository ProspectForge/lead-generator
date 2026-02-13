# tests/test_config.py
import pytest
from src.config import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test_google_key")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test_firecrawl_key")

    settings = Settings()

    assert settings.google_places_api_key == "test_google_key"
    assert settings.firecrawl_api_key == "test_firecrawl_key"

def test_settings_loads_cities_config():
    settings = Settings()

    assert "us" in settings.cities
    assert "canada" in settings.cities
    assert len(settings.cities["us"]) == 35
    assert len(settings.cities["canada"]) == 15

def test_settings_loads_search_queries():
    settings = Settings()

    assert "health_wellness" in settings.search_queries
    assert "sporting_goods" in settings.search_queries
    assert "apparel" in settings.search_queries
