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


settings = Settings()
