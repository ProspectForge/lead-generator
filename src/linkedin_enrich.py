# src/linkedin_enrich.py
import asyncio
import httpx
import re
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class Contact:
    name: str
    title: str
    linkedin_url: str

@dataclass
class LinkedInCompanyData:
    """Data extracted from a LinkedIn company page."""
    location_count: Optional[int]
    employee_range: Optional[str]
    industry: Optional[str]
    people: list[Contact]

@dataclass
class CompanyEnrichment:
    company_name: str
    linkedin_company_url: Optional[str]
    contacts: list[Contact]

class LinkedInEnricher:
    MAX_RETRIES = 2
    RETRY_DELAYS = [1, 2]
    REQUEST_TIMEOUT = 15.0
    DEFAULT_FLARESOLVERR_URL = "http://localhost:8191/v1"
    FLARESOLVERR_TIMEOUT = 60000  # ms

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    TARGET_TITLES = [
        "owner", "founder", "co-founder",
        "ceo", "chief executive",
        "coo", "chief operating",
        "president",
        "operations manager", "director of operations",
        "inventory manager", "supply chain manager",
        "retail manager", "store manager"
    ]

    def __init__(self, flaresolverr_url: Optional[str] = None, **kwargs):
        """Initialize enricher.

        Args:
            flaresolverr_url: FlareSolverr endpoint URL. If provided, uses it for
                JS-rendered page fetching (LinkedIn pages). Falls back to direct HTTP.
                Example: "https://flaresolverr-production-196c.up.railway.app/v1"
        """
        self.flaresolverr_url = flaresolverr_url or self.DEFAULT_FLARESOLVERR_URL
        self._flaresolverr_available: Optional[bool] = None

    async def _check_flaresolverr(self) -> bool:
        """Check if FlareSolverr is reachable."""
        if self._flaresolverr_available is not None:
            return self._flaresolverr_available
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.flaresolverr_url)
                self._flaresolverr_available = response.status_code == 200
        except Exception:
            self._flaresolverr_available = False
        return self._flaresolverr_available

    async def _fetch_via_flaresolverr(self, url: str) -> Optional[str]:
        """Fetch a page using FlareSolverr (handles Cloudflare, JS rendering)."""
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    self.flaresolverr_url,
                    json={
                        "cmd": "request.get",
                        "url": url,
                        "maxTimeout": self.FLARESOLVERR_TIMEOUT,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    solution = data.get("solution", {})
                    return solution.get("response", None)
        except Exception:
            pass
        return None

    async def _fetch_html(self, url: str, use_flaresolverr: bool = False) -> Optional[str]:
        """Fetch a page's HTML. Uses FlareSolverr if available and requested."""
        if use_flaresolverr and await self._check_flaresolverr():
            result = await self._fetch_via_flaresolverr(url)
            if result:
                return result

        # Direct HTTP fallback
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    response = await client.get(
                        url,
                        follow_redirects=True,
                        headers={
                            "User-Agent": self.USER_AGENT,
                            "Accept": "text/html,application/xhtml+xml",
                            "Accept-Language": "en-US,en;q=0.9",
                        },
                    )
                    if response.status_code >= 400:
                        return None
                    return response.text
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                return None
            except Exception:
                return None
        return None

    async def _search_linkedin(self, company_name: str, website: str) -> Optional[str]:
        """Find LinkedIn company URL via search engines."""
        from urllib.parse import unquote

        # Try DuckDuckGo HTML search (more bot-friendly than Google)
        query = f"site:linkedin.com/company {company_name}"
        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

        html = await self._fetch_html(search_url)
        if html:
            # URL-decode to handle DuckDuckGo redirect URLs
            decoded = unquote(html)
            match = re.search(r'linkedin\.com/company/([\w-]+)', decoded)
            if match:
                slug = match.group(1)
                if slug not in ("company", "companies"):
                    return f"https://www.linkedin.com/company/{slug}"

        # Fallback: try Google search
        google_url = f"https://www.google.com/search?q=site:linkedin.com/company+{company_name.replace(' ', '+')}"
        html = await self._fetch_html(google_url)
        if html:
            decoded = unquote(html)
            match = re.search(r'linkedin\.com/company/([\w-]+)', decoded)
            if match:
                slug = match.group(1)
                if slug not in ("company", "companies"):
                    return f"https://www.linkedin.com/company/{slug}"

        return None

    async def _search_people(self, company_name: str) -> list[Contact]:
        """Find LinkedIn profiles for company executives via search."""
        from urllib.parse import unquote

        contacts = []
        query = f"site:linkedin.com/in {company_name} CEO OR COO OR founder OR owner OR operations"
        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

        html = await self._fetch_html(search_url)
        if not html:
            return contacts

        # DuckDuckGo HTML results have structured elements:
        #   <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Flinkedin.com%2Fin%2Fslug">Title</a>
        #   <a class="result__snippet">Snippet text</a>
        # Title format is typically: "Name - Title - LinkedIn" or "Name - Title | LinkedIn"

        # Extract result blocks: (href, title_text)
        result_links = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

        seen_slugs = set()
        for href, title_html in result_links:
            # URL-decode the redirect URL to get actual LinkedIn URL
            decoded_href = unquote(href)
            slug_match = re.search(r'linkedin\.com/in/([\w-]+)', decoded_href)
            if not slug_match:
                continue

            slug = slug_match.group(1)
            if slug in seen_slugs or slug in ("in", "pub", "dir"):
                continue
            seen_slugs.add(slug)

            # Parse name and title from the search result title
            # Clean HTML tags from title
            title_text = re.sub(r'<[^>]+>', '', title_html).strip()

            # LinkedIn titles are typically: "Name - Title - LinkedIn"
            # or "Name - Title at Company | LinkedIn"
            parts = re.split(r'\s*[-–—|]\s*', title_text)
            # Remove "LinkedIn" from parts
            parts = [p.strip() for p in parts if p.strip().lower() != "linkedin"]

            if not parts:
                continue

            name = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else ""

            # Skip if name looks like a URL slug or is too short/long
            if len(name) < 3 or len(name) > 50:
                continue
            if re.match(r'^[\w-]+$', name) and '-' in name:
                # Looks like a URL slug, not a real name
                continue

            # Clean up title - remove "at Company" suffix if present
            title = re.sub(r'\s+at\s+.*$', '', title, flags=re.IGNORECASE).strip()
            if not title:
                title = "(see LinkedIn profile)"

            contacts.append(Contact(
                name=name,
                title=title,
                linkedin_url=f"https://www.linkedin.com/in/{slug}"
            ))
            if len(contacts) >= 4:
                break

        return contacts

    def _parse_company_html(self, html: str) -> LinkedInCompanyData:
        """Parse LinkedIn company page HTML for structured data."""
        location_count = None
        employee_range = None
        industry = None
        people = []

        # Try JSON-LD structured data first (most reliable)
        jsonld_matches = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        for jsonld_str in jsonld_matches:
            try:
                data = json.loads(jsonld_str)
                if isinstance(data, dict):
                    # Extract from Organization schema
                    if data.get("@type") == "Organization":
                        if data.get("numberOfEmployees"):
                            emp = data["numberOfEmployees"]
                            if isinstance(emp, dict):
                                min_val = emp.get("value", emp.get("minValue", ""))
                                max_val = emp.get("maxValue", "")
                                if min_val and max_val:
                                    employee_range = f"{min_val}-{max_val}"
                                elif min_val:
                                    employee_range = str(min_val)
                        if data.get("industry"):
                            industry = data["industry"]
                        # Look for number of locations
                        if data.get("numberOfLocations"):
                            location_count = int(data["numberOfLocations"])
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

        # Parse meta tags for additional data
        # og:description often has company size info
        desc_match = re.search(
            r'<meta[^>]*(?:name=["\']description["\']|property=["\']og:description["\'])[^>]*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if desc_match:
            desc = desc_match.group(1)

            # Extract employee range from description
            if not employee_range:
                emp_match = re.search(r'(\d+[\-–]\d+)\s*employees', desc, re.IGNORECASE)
                if emp_match:
                    employee_range = emp_match.group(1).replace('–', '-')

            # Extract industry from description
            if not industry:
                ind_match = re.search(r'(?:industry|sector)[:\s]+([^|.]+)', desc, re.IGNORECASE)
                if ind_match:
                    industry = ind_match.group(1).strip()

        # Look for location count in the page text
        if location_count is None:
            loc_match = re.search(r'(\d+)\s+locations?\b', html, re.IGNORECASE)
            if loc_match:
                location_count = int(loc_match.group(1))

        # Look for employee range in visible text if not found yet
        if not employee_range:
            emp_match = re.search(r'(\d+[\-–]\d+)\s*employees', html, re.IGNORECASE)
            if emp_match:
                employee_range = emp_match.group(1).replace('–', '-')

        # Extract people from JS-rendered HTML (available when using FlareSolverr)
        # Look for profile cards with names, titles, and LinkedIn URLs
        people_pattern = re.findall(
            r'linkedin\.com/in/([\w-]+)[^>]*>([^<]+)</a>[^<]*<[^>]*>([^<]+)',
            html
        )
        for profile_id, name, title in people_pattern:
            name = name.strip()
            title = title.strip()
            if 2 < len(name) < 60 and title:
                people.append(Contact(
                    name=name,
                    title=title,
                    linkedin_url=f"https://www.linkedin.com/in/{profile_id}"
                ))
                if len(people) >= 4:
                    break

        return LinkedInCompanyData(
            location_count=location_count,
            employee_range=employee_range,
            industry=industry,
            people=people,
        )

    def _parse_company_page(self, markdown: str) -> LinkedInCompanyData:
        """Parse LinkedIn company page markdown to extract structured data.

        Kept for backward compatibility with tests that provide markdown content.
        """
        location_count = None
        employee_range = None
        industry = None
        people = []

        # Extract location count
        loc_match = re.search(r'(\d+)\s+locations?\b', markdown, re.IGNORECASE)
        if loc_match:
            location_count = int(loc_match.group(1))

        # Extract employee range
        emp_match = re.search(r'(\d+[\-–]\d+)\s*employees', markdown, re.IGNORECASE)
        if not emp_match:
            emp_match = re.search(r'[Cc]ompany\s+size[:\s]*(\d+[\-–]\d+)', markdown)
        if emp_match:
            employee_range = emp_match.group(1).replace('–', '-')

        # Extract industry
        ind_match = re.search(r'\*\*Industry:?\*\*\s*(.+)', markdown)
        if not ind_match:
            ind_match = re.search(r'Industry[:\s]+([A-Z][^\n]+)', markdown)
        if ind_match:
            industry = ind_match.group(1).strip()

        # Extract people with LinkedIn profile links
        people_pattern = re.findall(
            r'\[\*\*(.+?)\*\*\]\(https?://(?:www\.)?linkedin\.com/in/([\w-]+)\)\s*\n\s*(.+)',
            markdown
        )
        for name, profile_id, title in people_pattern:
            people.append(Contact(
                name=name.strip(),
                title=title.strip(),
                linkedin_url=f"https://www.linkedin.com/in/{profile_id}"
            ))

        # Fallback pattern
        if not people:
            simple_pattern = re.findall(
                r'([\w\s]+?)\s*[-–—|]\s*(?:https?://)?linkedin\.com/in/([\w-]+)',
                markdown
            )
            for name, profile_id in simple_pattern:
                name = name.strip()
                if 2 < len(name) < 60:
                    people.append(Contact(
                        name=name,
                        title="(see LinkedIn profile)",
                        linkedin_url=f"https://www.linkedin.com/in/{profile_id}"
                    ))

        return LinkedInCompanyData(
            location_count=location_count,
            employee_range=employee_range,
            industry=industry,
            people=people,
        )

    async def scrape_company_page(self, linkedin_url: str) -> LinkedInCompanyData:
        """Scrape a LinkedIn company page and extract structured data.

        Uses FlareSolverr if available for full JS-rendered content.
        """
        try:
            content = await self._fetch_html(linkedin_url, use_flaresolverr=True)
            if not content:
                return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])
            # Detect if content is HTML or markdown and parse accordingly
            if "<html" in content.lower() or "<!doctype" in content.lower():
                return self._parse_company_html(content)
            else:
                return self._parse_company_page(content)
        except Exception:
            return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])

    async def find_company(self, company_name: str, website: str) -> Optional[str]:
        return await self._search_linkedin(company_name, website)

    async def find_contacts(self, company_name: str, max_contacts: int = 4) -> list[Contact]:
        contacts = await self._search_people(company_name)
        return contacts[:max_contacts]

    async def enrich(self, company_name: str, website: str) -> CompanyEnrichment:
        linkedin_url = await self.find_company(company_name, website)
        contacts = await self.find_contacts(company_name)

        return CompanyEnrichment(
            company_name=company_name,
            linkedin_company_url=linkedin_url,
            contacts=contacts
        )
