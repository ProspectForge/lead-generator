# tests/test_config.py
import pytest
from src.config import Settings, DiscoverySettings, EnrichmentSettings, LLMSettings


# ═══════════════════════════════════════════════════════════════════
# Environment variable loading
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test_serpapi_key")
    settings = Settings()
    assert settings.serpapi_api_key == "test_serpapi_key"


def test_settings_loads_apollo_key(monkeypatch):
    monkeypatch.setenv("APOLLO_API_KEY", "test_apollo_key")
    settings = Settings()
    assert settings.apollo_api_key == "test_apollo_key"


def test_settings_loads_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    settings = Settings()
    assert settings.openai_api_key == "test_openai_key"


# ═══════════════════════════════════════════════════════════════════
# City config loading
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_cities_config():
    settings = Settings()
    assert "us" in settings.cities
    assert "canada" in settings.cities
    assert len(settings.cities["us"]) >= 700
    assert len(settings.cities["canada"]) >= 100


def test_settings_cities_are_strings():
    settings = Settings()
    for city in settings.cities["us"][:10]:
        assert isinstance(city, str)
        assert "," in city


# ═══════════════════════════════════════════════════════════════════
# Search queries loading
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_search_queries():
    settings = Settings()
    assert "health_wellness" in settings.search_queries
    assert "sporting_goods" in settings.search_queries
    assert "apparel" in settings.search_queries


def test_search_queries_have_entries():
    settings = Settings()
    for vertical, queries in settings.search_queries.items():
        assert len(queries) >= 1, f"Vertical {vertical} has no queries"


# ═══════════════════════════════════════════════════════════════════
# Quality gate config
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_quality_gate_config():
    settings = Settings()
    assert settings.quality_gate_max_locations == 10
    assert settings.quality_gate_max_employees == 500


# ═══════════════════════════════════════════════════════════════════
# Health check config
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_health_check_config():
    settings = Settings()
    assert settings.health_check_concurrency == 50


# ═══════════════════════════════════════════════════════════════════
# Discovery settings
# ═══════════════════════════════════════════════════════════════════

def test_discovery_settings_loaded():
    s = Settings()
    assert hasattr(s, 'discovery')
    assert s.discovery.nearby_grid_enabled is True
    assert s.discovery.nearby_grid_offset_km == 30
    assert s.discovery.nearby_grid_radius_meters == 15000
    assert s.discovery.nearby_grid_points == "cardinal"


def test_discovery_settings_is_dataclass():
    s = Settings()
    assert isinstance(s.discovery, DiscoverySettings)


# ═══════════════════════════════════════════════════════════════════
# Playwright fallback settings
# ═══════════════════════════════════════════════════════════════════

def test_ecommerce_playwright_fallback_settings():
    s = Settings()
    assert s.ecommerce_playwright_fallback_enabled is True
    assert s.ecommerce_playwright_fallback_max_percent == 20
    assert s.ecommerce_playwright_fallback_timeout == 15


# ═══════════════════════════════════════════════════════════════════
# Search mode
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_search_mode():
    settings = Settings()
    assert settings.search_mode in ("lean", "extended")


def test_settings_search_mode_is_lean_by_default():
    settings = Settings()
    assert settings.search_mode == "lean"


# ═══════════════════════════════════════════════════════════════════
# Lean cities
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_lean_cities():
    settings = Settings()
    assert "us" in settings.lean_cities
    assert "canada" in settings.lean_cities
    assert len(settings.lean_cities["us"]) >= 40
    assert len(settings.lean_cities["canada"]) >= 10


def test_lean_cities_are_subset_of_full_cities():
    settings = Settings()
    assert len(settings.lean_cities["us"]) < len(settings.cities["us"])
    assert len(settings.lean_cities["canada"]) < len(settings.cities["canada"])


def test_lean_cities_are_strings():
    settings = Settings()
    for city in settings.lean_cities["us"]:
        assert isinstance(city, str)
        assert "," in city


# ═══════════════════════════════════════════════════════════════════
# Lean queries
# ═══════════════════════════════════════════════════════════════════

def test_settings_loads_lean_queries():
    settings = Settings()
    assert "health_wellness" in settings.lean_queries
    assert len(settings.lean_queries["health_wellness"]) >= 2
    assert len(settings.lean_queries["health_wellness"]) <= 5


def test_lean_queries_fewer_than_full_queries():
    settings = Settings()
    for vertical in settings.lean_queries:
        if vertical in settings.search_queries:
            assert len(settings.lean_queries[vertical]) <= len(settings.search_queries[vertical])


# ═══════════════════════════════════════════════════════════════════
# get_cities_for_mode
# ═══════════════════════════════════════════════════════════════════

def test_settings_get_cities_for_mode_lean():
    settings = Settings()
    settings.search_mode = "lean"
    cities = settings.get_cities_for_mode()
    assert len(cities["us"]) < len(settings.cities["us"])
    assert cities == settings.lean_cities


def test_settings_get_cities_for_mode_extended():
    settings = Settings()
    settings.search_mode = "extended"
    cities = settings.get_cities_for_mode()
    assert cities["us"] == settings.cities["us"]
    assert cities == settings.cities


def test_get_cities_for_mode_returns_lean_cities_object():
    settings = Settings()
    settings.search_mode = "lean"
    assert settings.get_cities_for_mode() is settings.lean_cities


def test_get_cities_for_mode_returns_full_cities_object():
    settings = Settings()
    settings.search_mode = "extended"
    assert settings.get_cities_for_mode() is settings.cities


# ═══════════════════════════════════════════════════════════════════
# get_queries_for_mode
# ═══════════════════════════════════════════════════════════════════

def test_settings_get_queries_for_mode_lean():
    settings = Settings()
    settings.search_mode = "lean"
    queries = settings.get_queries_for_mode()
    assert len(queries["health_wellness"]) <= 5
    assert queries == settings.lean_queries


def test_settings_get_queries_for_mode_extended():
    settings = Settings()
    settings.search_mode = "extended"
    queries = settings.get_queries_for_mode()
    assert len(queries["health_wellness"]) >= 10
    assert queries == settings.search_queries


# ═══════════════════════════════════════════════════════════════════
# get_all_city_names
# ═══════════════════════════════════════════════════════════════════

def test_get_all_city_names():
    settings = Settings()
    names = settings.get_all_city_names()
    assert len(names) > 0
    for name in names[:10]:
        assert "," not in name


def test_get_all_city_names_includes_known_cities():
    settings = Settings()
    names = settings.get_all_city_names()
    assert "Boston" in names
    assert "Toronto" in names


# ═══════════════════════════════════════════════════════════════════
# Enrichment settings
# ═══════════════════════════════════════════════════════════════════

def test_enrichment_settings_loaded():
    settings = Settings()
    assert isinstance(settings.enrichment, EnrichmentSettings)
    assert settings.enrichment.provider in ("linkedin", "apollo")
    assert settings.enrichment.max_contacts >= 1


def test_enrichment_concurrency_loaded():
    settings = Settings()
    assert settings.enrichment.concurrency >= 1


# ═══════════════════════════════════════════════════════════════════
# LLM settings
# ═══════════════════════════════════════════════════════════════════

def test_llm_settings_loaded():
    settings = Settings()
    assert isinstance(settings.llm, LLMSettings)
    assert settings.llm.provider in ("openai", "anthropic")


# ═══════════════════════════════════════════════════════════════════
# Chain filter config
# ═══════════════════════════════════════════════════════════════════

def test_known_large_chains_loaded():
    settings = Settings()
    assert isinstance(settings.known_large_chains, set)
    assert len(settings.known_large_chains) >= 1


def test_chain_filter_max_cities_loaded():
    settings = Settings()
    assert settings.chain_filter_max_cities >= 1


# ═══════════════════════════════════════════════════════════════════
# Concurrency
# ═══════════════════════════════════════════════════════════════════

def test_search_concurrency_loaded():
    settings = Settings()
    assert settings.search_concurrency >= 1


def test_ecommerce_concurrency_loaded():
    settings = Settings()
    assert settings.ecommerce_concurrency >= 1
