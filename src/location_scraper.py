# src/location_scraper.py
"""Scrape brand websites for store location pages.

Finds location/store-finder pages on a brand's website and extracts
addresses from JSON-LD structured data, schema.org microdata, or HTML.
Results are cached for 90 days per domain.
"""
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Common paths where retailers list their store locations
LOCATION_PATHS = [
    "/locations",
    "/stores",
    "/store-locator",
    "/find-a-store",
    "/our-stores",
    "/store-finder",
    "/find-store",
    "/storelocator",
    "/all-locations",
    "/retail-locations",
]

# Keywords in nav links that suggest a location page
LOCATION_LINK_KEYWORDS = [
    "location", "store", "find", "visit", "near",
    "branch", "dealer", "retailer", "showroom",
]

# JSON-LD types that represent physical locations
LOCATION_SCHEMA_TYPES = {
    "Store", "LocalBusiness", "Restaurant", "RetailStore",
    "SportingGoodsStore", "HealthAndBeautyBusiness",
    "ShoppingCenter", "GroceryStore",
}

DEFAULT_CACHE_TTL_DAYS = 90


class LocationScraper:
    """Scrapes brand websites for store location data."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
        timeout: float = 15.0,
    ):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "location_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_seconds = cache_ttl_days * 86400
        self.timeout = timeout

    # -- Cache ────────────────────────────────────────────────────────

    def _cache_key(self, url: str) -> str:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return hashlib.sha256(domain.encode()).hexdigest()[:16]

    def _get_cached(self, url: str) -> Optional[list[dict]]:
        key = self._cache_key(url)
        cache_file = self.cache_dir / f"{key}.json"
        if not cache_file.exists():
            return None
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("_cached_at", 0) > self.cache_ttl_seconds:
                return None
            return data.get("locations")
        except (json.JSONDecodeError, KeyError):
            return None

    def _set_cached(self, url: str, locations: list[dict]):
        key = self._cache_key(url)
        cache_file = self.cache_dir / f"{key}.json"
        domain = urlparse(url).netloc.lower().lstrip("www.")
        cache_file.write_text(json.dumps({
            "_cached_at": time.time(),
            "_domain": domain,
            "locations": locations,
        }, indent=2))

    # -- URL Discovery ────────────────────────────────────────────────

    def _build_candidate_urls(self, base_url: str) -> list[str]:
        """Build list of candidate location page URLs to try."""
        parsed = urlparse(base_url if base_url.startswith(("http://", "https://")) else f"https://{base_url}")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return [f"{origin}{path}" for path in LOCATION_PATHS]

    def _find_location_links(self, html: str, base_url: str) -> list[str]:
        """Parse HTML for nav/footer links that point to location pages."""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            text = (a_tag.get_text() or "").lower().strip()
            href_lower = href.lower()

            if any(kw in text or kw in href_lower for kw in LOCATION_LINK_KEYWORDS):
                full_url = urljoin(base_url, href)
                if full_url not in links:
                    links.append(full_url)
        return links

    # -- HTML Parsing ─────────────────────────────────────────────────

    def _parse_locations_from_html(self, html: str) -> list[dict]:
        """Extract location data from HTML using JSON-LD, then fallback to address patterns."""
        locations = []

        # Try JSON-LD first (most reliable)
        locations = self._parse_json_ld(html)
        if locations:
            return locations

        # Try address-pattern extraction as fallback
        locations = self._parse_address_patterns(html)
        return locations

    def _parse_json_ld(self, html: str) -> list[dict]:
        """Extract locations from JSON-LD structured data."""
        soup = BeautifulSoup(html, "html.parser")
        locations = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            items = data if isinstance(data, list) else [data]

            # Handle @graph containers
            expanded = []
            for item in items:
                if isinstance(item, dict) and "@graph" in item:
                    expanded.extend(item["@graph"])
                else:
                    expanded.append(item)

            for item in expanded:
                if not isinstance(item, dict):
                    continue
                schema_type = item.get("@type", "")
                if isinstance(schema_type, list):
                    schema_type = schema_type[0] if schema_type else ""

                if schema_type in LOCATION_SCHEMA_TYPES:
                    loc = self._extract_address_from_schema(item)
                    if loc:
                        locations.append(loc)

        return locations

    def _extract_address_from_schema(self, item: dict) -> Optional[dict]:
        """Extract address dict from a schema.org JSON-LD item."""
        address = item.get("address", {})
        if isinstance(address, str):
            return {"name": item.get("name", ""), "address": address, "city": "", "state": ""}

        if isinstance(address, dict):
            street = address.get("streetAddress", "")
            city = address.get("addressLocality", "")
            state = address.get("addressRegion", "")
            if city or street:
                full_address = ", ".join(filter(None, [street, city, state]))
                return {
                    "name": item.get("name", ""),
                    "address": full_address,
                    "city": city,
                    "state": state,
                }
        return None

    def _parse_address_patterns(self, html: str) -> list[dict]:
        """Fallback: extract US/CA addresses via regex patterns."""
        us_pattern = r'(\d{1,5}\s+[\w\s.]+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Hwy|Circle|Loop|Trail)\.?)\s*,?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*,?\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?'
        locations = []
        seen = set()

        for match in re.finditer(us_pattern, html):
            street, city, state, zipcode = match.groups()
            key = f"{street.strip().lower()}|{city.strip().lower()}"
            if key not in seen:
                seen.add(key)
                locations.append({
                    "name": "",
                    "address": f"{street.strip()}, {city.strip()}, {state}",
                    "city": city.strip(),
                    "state": state,
                })

        return locations

    # -- Main Entry Point ─────────────────────────────────────────────

    async def scrape(self, website_url: str) -> list[dict]:
        """Scrape a brand's website for store locations.

        Returns list of {name, address, city, state} dicts, or [] if no
        locations found. Results are cached for 90 days by domain.
        """
        # Cache first
        cached = self._get_cached(website_url)
        if cached is not None:
            return cached

        if not website_url.startswith(("http://", "https://")):
            website_url = f"https://{website_url}"

        locations = []

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; LeadGen/1.0)"},
            ) as client:
                # Step 1: Try common location paths
                candidate_urls = self._build_candidate_urls(website_url)
                for url in candidate_urls:
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            locations = self._parse_locations_from_html(resp.text)
                            if locations:
                                break
                    except (httpx.TimeoutException, httpx.ConnectError):
                        continue

                # Step 2: If nothing found, check homepage for location nav links
                if not locations:
                    try:
                        resp = await client.get(website_url)
                        if resp.status_code == 200:
                            link_urls = self._find_location_links(resp.text, website_url)
                            for link_url in link_urls[:5]:
                                try:
                                    resp2 = await client.get(link_url)
                                    if resp2.status_code == 200:
                                        locations = self._parse_locations_from_html(resp2.text)
                                        if locations:
                                            break
                                except (httpx.TimeoutException, httpx.ConnectError):
                                    continue
                    except (httpx.TimeoutException, httpx.ConnectError):
                        pass

        except Exception as e:
            logger.warning("Location scrape failed for %s: %s", website_url, e)

        # Cache result (even empty -- avoids retrying sites with no locations)
        self._set_cached(website_url, locations)
        return locations
