# src/scraper/bestof_scraper.py
import re
from typing import Optional
from .base import BaseScraper, ScrapedBrand

class BestOfScraper(BaseScraper):
    """Scrapes 'best of' articles to find local retailers."""

    SEARCH_TEMPLATES = [
        "best {query} in {city}",
        "top {query} {city}",
        "independent {query} {city}",
    ]

    # Patterns to extract business names
    NAME_PATTERNS = [
        r'\*\*([^*]+)\*\*',  # **Bold Name**
        r'^\d+\.\s+(.+?)(?:\s*[-–—]|$)',  # 1. Name - description
        r'^#+\s+(.+?)$',  # # Header Name
    ]

    # Pattern to extract URLs
    URL_PATTERN = r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)'

    async def scrape_city(self, city: str, query: str) -> list[ScrapedBrand]:
        """Scrape best-of articles for a specific city and query."""
        brands = []

        # Build search URL
        search_query = f"best {query} in {city}"
        search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"

        try:
            content = await self._fetch(search_url)
            brands.extend(self._extract_brands(content, city, query))
        except Exception:
            pass

        return brands

    def _extract_brands(self, content: str, city: str, query: str) -> list[ScrapedBrand]:
        """Extract brand names and websites from article content."""
        brands = []
        seen_names = set()

        lines = content.split('\n')

        for i, line in enumerate(lines):
            # Try to extract a business name
            name = self._extract_name(line)
            if not name or len(name) < 3 or len(name) > 100:
                continue

            # Skip if already seen
            normalized = name.lower().strip()
            if normalized in seen_names:
                continue
            seen_names.add(normalized)

            # Try to find a website in nearby lines
            context = '\n'.join(lines[max(0, i-1):min(len(lines), i+3)])
            website = self._extract_website(context)

            # Skip generic terms
            if self._is_generic(name):
                continue

            brands.append(ScrapedBrand(
                name=name,
                category=query,
                website=website,
                source="bestof_article"
            ))

        return brands

    def _extract_name(self, line: str) -> Optional[str]:
        """Extract a business name from a line."""
        for pattern in self.NAME_PATTERNS:
            match = re.search(pattern, line, re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Clean up
                name = re.sub(r'\[.*?\]', '', name)  # Remove markdown links
                name = re.sub(r'\(.*?\)', '', name)  # Remove parentheticals
                return name.strip()
        return None

    def _extract_website(self, content: str) -> Optional[str]:
        """Extract a website URL from content."""
        match = re.search(self.URL_PATTERN, content)
        if match:
            domain = match.group(1)
            # Skip common non-business domains
            skip_domains = ['google.com', 'facebook.com', 'instagram.com', 'twitter.com', 'yelp.com']
            if not any(skip in domain for skip in skip_domains):
                return f"https://{domain}"
        return None

    def _is_generic(self, name: str) -> bool:
        """Check if a name is too generic to be a business."""
        generic = ['store', 'shop', 'best', 'top', 'list', 'guide', 'review']
        name_lower = name.lower()
        return any(name_lower == g or name_lower == f"the {g}" for g in generic)

    async def scrape(self) -> list[ScrapedBrand]:
        """Not used - use scrape_city instead."""
        return []
