# src/config.py
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    google_places_api_key: str = ""
    firecrawl_api_key: str = ""
    cities: dict = field(default_factory=dict)
    search_queries: dict = field(default_factory=dict)
    known_large_chains: set = field(default_factory=set)
    chain_filter_max_cities: int = 8
    ecommerce_concurrency: int = 10
    ecommerce_pages_to_check: int = 3
    search_concurrency: int = 10

    def __post_init__(self):
        self.google_places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "")

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


settings = Settings()
