# src/config.py
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMSettings:
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"


@dataclass
class EnrichmentSettings:
    """Settings for lead enrichment providers."""
    enabled: bool = True
    provider: str = "linkedin"  # "linkedin" (free/scraping) or "apollo" (paid)
    max_contacts: int = 4
    concurrency: int = 3  # Parallel enrichment requests
    use_playwright: bool = True  # Use Playwright for JS-rendered LinkedIn pages
    cookie_file: str = ""  # Path to LinkedIn cookies JSON for authenticated scraping


@dataclass
class EmailVerificationSettings:
    """Settings for email verification."""
    enabled: bool = False  # Disabled by default
    verify_smtp: bool = False  # SMTP check (slow, often blocked)
    include_risky: bool = False  # Include catch-all/unknown emails


@dataclass
class OutreachSettings:
    """Settings for outreach message generation."""
    llm_provider: str = "openai"       # "openai" or "anthropic"
    llm_model: str = "gpt-4o"          # model name
    default_template: str = ""         # default template filename


@dataclass
class DiscoverySettings:
    """Settings for discovery nearby grid search."""
    nearby_grid_enabled: bool = True
    nearby_grid_offset_km: int = 20
    nearby_grid_radius_meters: int = 15000
    nearby_grid_points: str = "cardinal"  # "cardinal" (5 points) or "full" (9 points)


@dataclass
class Settings:
    google_places_api_key: str = ""
    firecrawl_api_key: str = ""  # Legacy, no longer used
    flaresolverr_url: str = ""
    openai_api_key: str = ""
    apollo_api_key: str = ""
    anthropic_api_key: str = ""
    cities: dict = field(default_factory=dict)
    search_queries: dict = field(default_factory=dict)
    known_large_chains: set = field(default_factory=set)
    chain_filter_max_cities: int = 8
    ecommerce_concurrency: int = 10
    ecommerce_pages_to_check: int = 3
    search_concurrency: int = 10
    llm: LLMSettings = field(default_factory=LLMSettings)
    enrichment: EnrichmentSettings = field(default_factory=EnrichmentSettings)
    email_verification: EmailVerificationSettings = field(default_factory=EmailVerificationSettings)
    outreach: OutreachSettings = field(default_factory=OutreachSettings)
    quality_gate_max_locations: int = 10
    quality_gate_max_employees: int = 500
    health_check_concurrency: int = 10
    discovery: DiscoverySettings = field(default_factory=DiscoverySettings)

    def __post_init__(self):
        self.google_places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "")
        self.flaresolverr_url = os.getenv("FLARESOLVERR_URL", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.apollo_api_key = os.getenv("APOLLO_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

        config_path = Path(__file__).parent.parent / "config" / "cities.json"
        with open(config_path) as f:
            config = json.load(f)

        self.cities = {
            "us": config.get("us", []),
            "canada": config.get("canada", [])
        }
        self.search_queries = config.get("search_queries", {})
        self.known_large_chains = set(config.get("known_large_chains", []))
        self.chain_filter_max_cities = config.get("chain_filter", {}).get("max_cities", 8)
        self.ecommerce_concurrency = config.get("ecommerce", {}).get("concurrency", 10)
        self.ecommerce_pages_to_check = config.get("ecommerce", {}).get("pages_to_check", 3)
        self.search_concurrency = config.get("search", {}).get("concurrency", 10)

        # Load LLM settings
        llm_config = config.get("llm", {})
        self.llm = LLMSettings(
            enabled=llm_config.get("enabled", False),
            provider=llm_config.get("provider", "openai"),
            model=llm_config.get("model", "gpt-4o-mini")
        )

        # Load enrichment settings
        enrichment_config = config.get("enrichment", {})
        self.enrichment = EnrichmentSettings(
            enabled=enrichment_config.get("enabled", True),
            provider=enrichment_config.get("provider", "linkedin"),
            max_contacts=enrichment_config.get("max_contacts", 4),
            concurrency=enrichment_config.get("concurrency", 3),
            use_playwright=enrichment_config.get("use_playwright", True),
            cookie_file=os.getenv("LINKEDIN_COOKIE_FILE", enrichment_config.get("cookie_file", "")),
        )

        # Load email verification settings
        email_config = config.get("email_verification", {})
        self.email_verification = EmailVerificationSettings(
            enabled=email_config.get("enabled", False),
            verify_smtp=email_config.get("verify_smtp", False),
            include_risky=email_config.get("include_risky", False)
        )

        # Load outreach settings
        outreach_config = config.get("outreach", {})
        self.outreach = OutreachSettings(
            llm_provider=outreach_config.get("llm_provider", "openai"),
            llm_model=outreach_config.get("llm_model", "gpt-4o"),
            default_template=outreach_config.get("default_template", ""),
        )

        # Load quality gate settings
        quality_gate_config = config.get("quality_gate", {})
        self.quality_gate_max_locations = quality_gate_config.get("max_locations", 10)
        self.quality_gate_max_employees = quality_gate_config.get("max_employees", 500)

        # Load health check settings
        health_check_config = config.get("health_check", {})
        self.health_check_concurrency = health_check_config.get("concurrency", 10)

        # Load discovery settings
        discovery_config = config.get("discovery", {})
        nearby_grid = discovery_config.get("nearby_grid", {})
        self.discovery = DiscoverySettings(
            nearby_grid_enabled=nearby_grid.get("enabled", True),
            nearby_grid_offset_km=nearby_grid.get("offset_km", 20),
            nearby_grid_radius_meters=nearby_grid.get("radius_meters", 15000),
            nearby_grid_points=nearby_grid.get("points", "cardinal"),
        )

    def get_all_city_names(self) -> list[str]:
        """Returns all city names (just the city part, without state/province)."""
        city_names = []
        for region_cities in self.cities.values():
            for city_full in region_cities:
                # Split on comma to get just the city name
                city_name = city_full.split(",")[0].strip()
                city_names.append(city_name)
        return city_names


settings = Settings()
