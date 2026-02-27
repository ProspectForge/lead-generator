# src/linkedin_enrich.py
import asyncio
import httpx
import re
import json
from dataclasses import dataclass, field
from pathlib import Path
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
    about: Optional[str] = None

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

    def __init__(self, flaresolverr_url: Optional[str] = None, cookie_file: Optional[str] = None, **kwargs):
        """Initialize enricher.

        Args:
            flaresolverr_url: FlareSolverr endpoint URL. Falls back to direct HTTP.
            cookie_file: Path to LinkedIn cookies JSON for authenticated Playwright scraping.
        """
        self.flaresolverr_url = (flaresolverr_url or self.DEFAULT_FLARESOLVERR_URL).strip()
        self._flaresolverr_available: Optional[bool] = None
        self._cookie_file = cookie_file
        # Playwright state (lazy-initialized via start_browser())
        self._playwright = None
        self._browser = None
        self._browser_context = None

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_company_slug(linkedin_url: str) -> Optional[str]:
        """Extract slug from a LinkedIn company URL."""
        match = re.search(r'linkedin\.com/company/([\w-]+)', linkedin_url)
        return match.group(1) if match else None

    @staticmethod
    def _is_authwall(html: str) -> bool:
        """Detect if LinkedIn returned an auth wall instead of content."""
        indicators = [
            'authwall', 'sign in to linkedin', 'join linkedin',
            'login-form', '"loginform"', 'signup-form',
        ]
        html_lower = html.lower()
        return any(indicator in html_lower for indicator in indicators)

    def _filter_by_target_titles(self, contacts: list[Contact]) -> list[Contact]:
        """Filter contacts to those matching TARGET_TITLES."""
        filtered = []
        for contact in contacts:
            title_lower = contact.title.lower()
            if any(target in title_lower for target in self.TARGET_TITLES):
                filtered.append(contact)
        return filtered

    # ── HTTP fetching ────────────────────────────────────────────────

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

    # ── Playwright browser lifecycle ────────────────────────────────

    @staticmethod
    def _load_cookies(cookie_file: str) -> list[dict]:
        """Load LinkedIn cookies from a JSON file for authenticated scraping.

        Expected format: list of {name, value, domain, ...} objects.
        The minimum required cookie is 'li_at' from linkedin.com.
        """
        try:
            path = Path(cookie_file)
            if not path.is_file():
                return []
            with open(path) as f:
                cookies = json.load(f)
            if not isinstance(cookies, list):
                return []
            return [c for c in cookies if isinstance(c, dict) and "name" in c and "value" in c and "domain" in c]
        except (json.JSONDecodeError, OSError):
            return []

    async def start_browser(self):
        """Launch headless Chromium and create a browser context. Idempotent."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._browser_context = await self._browser.new_context(user_agent=self.USER_AGENT)
            # Load cookies for authenticated scraping if available
            if self._cookie_file:
                cookies = self._load_cookies(self._cookie_file)
                if cookies:
                    await self._browser_context.add_cookies(cookies)
        except Exception:
            # Playwright not installed or browser launch failed — will fall back to other methods
            await self.close_browser()

    async def close_browser(self):
        """Shut down Playwright browser. Safe to call when never started."""
        if self._browser_context:
            try:
                await self._browser_context.close()
            except Exception:
                pass
            self._browser_context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def _fetch_via_playwright(self, url: str) -> Optional[str]:
        """Fetch a page using Playwright headless Chromium (best JS rendering)."""
        if not self._browser_context:
            return None
        url = url.strip()
        page = None
        try:
            page = await self._browser_context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)  # Let JS render
            return await page.content()
        except Exception:
            return None
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    # ── FlareSolverr fetching ─────────────────────────────────────

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
        """Fetch a page's HTML with JS rendering fallback chain.

        When use_flaresolverr=True (i.e., JS rendering requested):
        1. Playwright (if browser started) — best local JS rendering
        2. FlareSolverr (if available) — remote JS rendering
        3. Direct HTTP — no JS, limited LinkedIn data
        """
        if use_flaresolverr:
            # Try Playwright first (local, fast, best JS rendering)
            if self._browser_context:
                result = await self._fetch_via_playwright(url)
                if result:
                    return result

            # Fall back to FlareSolverr
            if await self._check_flaresolverr():
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

    # ── Search engines (DDG / Google) ────────────────────────────────

    async def _search_linkedin(self, company_name: str, website: str) -> Optional[str]:
        """Find LinkedIn company URL via search engines."""
        from urllib.parse import unquote

        # Try DuckDuckGo HTML search (more bot-friendly than Google)
        query = f"site:linkedin.com/company {company_name}"
        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

        html = await self._fetch_html(search_url)
        if html:
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
        """Find LinkedIn profiles for company executives via DDG search (fallback)."""
        from urllib.parse import unquote

        contacts = []
        query = f"site:linkedin.com/in {company_name} CEO OR COO OR founder OR owner OR operations"
        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

        html = await self._fetch_html(search_url)
        if not html:
            return contacts

        result_links = re.findall(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

        seen_slugs = set()
        for href, title_html in result_links:
            decoded_href = unquote(href)
            slug_match = re.search(r'linkedin\.com/in/([\w-]+)', decoded_href)
            if not slug_match:
                continue

            slug = slug_match.group(1)
            if slug in seen_slugs or slug in ("in", "pub", "dir"):
                continue
            seen_slugs.add(slug)

            title_text = re.sub(r'<[^>]+>', '', title_html).strip()
            parts = re.split(r'\s*[-–—|]\s*', title_text)
            parts = [p.strip() for p in parts if p.strip().lower() != "linkedin"]

            if not parts:
                continue

            name = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else ""

            if len(name) < 3 or len(name) > 50:
                continue
            if re.match(r'^[\w-]+$', name) and '-' in name:
                continue

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

    # ── LinkedIn page parsers ────────────────────────────────────────

    def _parse_people_html(self, html: str) -> list[Contact]:
        """Parse LinkedIn HTML (company page or people page) for contact profiles.

        Multi-layered extraction:
        1. Embedded JSON data (publicIdentifier, firstName/lastName)
        2. <a> tags with /in/ links + surrounding text for name and title
        """
        contacts = []
        seen_slugs = set()

        # Layer 1: Look for embedded JSON data in <script> tags
        # LinkedIn sometimes embeds profile data as JSON objects
        script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for block in script_blocks:
            if '"publicIdentifier"' not in block and '"firstName"' not in block:
                continue
            try:
                # Try to extract profile objects from JSON-like structures
                # Pattern: {"firstName":"John","lastName":"Doe","headline":"CEO",...,"publicIdentifier":"john-doe"}
                profile_matches = re.finditer(
                    r'\{[^{}]*?"firstName"\s*:\s*"([^"]+)"[^{}]*?"lastName"\s*:\s*"([^"]+)"[^{}]*?'
                    r'"headline"\s*:\s*"([^"]*)"[^{}]*?"publicIdentifier"\s*:\s*"([\w-]+)"[^{}]*?\}',
                    block
                )
                for m in profile_matches:
                    first, last, headline, slug = m.group(1), m.group(2), m.group(3), m.group(4)
                    if slug in seen_slugs or slug in ("in", "pub", "dir"):
                        continue
                    name = f"{first} {last}".strip()
                    if 2 < len(name) < 60:
                        seen_slugs.add(slug)
                        contacts.append(Contact(
                            name=name,
                            title=headline or "(see LinkedIn profile)",
                            linkedin_url=f"https://www.linkedin.com/in/{slug}"
                        ))

                # Also try reversed field order
                profile_matches2 = re.finditer(
                    r'\{[^{}]*?"publicIdentifier"\s*:\s*"([\w-]+)"[^{}]*?'
                    r'"firstName"\s*:\s*"([^"]+)"[^{}]*?"lastName"\s*:\s*"([^"]+)"[^{}]*?'
                    r'"headline"\s*:\s*"([^"]*)"[^{}]*?\}',
                    block
                )
                for m in profile_matches2:
                    slug, first, last, headline = m.group(1), m.group(2), m.group(3), m.group(4)
                    if slug in seen_slugs or slug in ("in", "pub", "dir"):
                        continue
                    name = f"{first} {last}".strip()
                    if 2 < len(name) < 60:
                        seen_slugs.add(slug)
                        contacts.append(Contact(
                            name=name,
                            title=headline or "(see LinkedIn profile)",
                            linkedin_url=f"https://www.linkedin.com/in/{slug}"
                        ))
            except Exception:
                continue

        # Layer 2: Parse <a> tags with /in/ profile links
        # Find all links pointing to LinkedIn profiles and extract name + title from context
        link_pattern = re.compile(
            r'<a[^>]*href="[^"]*linkedin\.com/in/([\w-]+)[^"]*"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        for match in link_pattern.finditer(html):
            slug = match.group(1)
            if slug in seen_slugs or slug in ("in", "pub", "dir"):
                continue

            # Extract name from the link text (strip HTML tags)
            link_text = re.sub(r'<[^>]+>', ' ', match.group(2)).strip()
            link_text = re.sub(r'\s+', ' ', link_text).strip()

            # Skip if link text is not a name (too short, too long, looks like URL)
            if not link_text or len(link_text) < 3 or len(link_text) > 60:
                continue
            if re.match(r'^[\w-]+$', link_text) and '-' in link_text:
                continue

            # Look for title in the HTML after this link (next ~500 chars)
            after = html[match.end():match.end() + 500]
            # Strip tags and get first non-empty line as the title
            clean_after = re.sub(r'<[^>]+>', '\n', after)
            lines = [l.strip() for l in clean_after.split('\n') if l.strip()]

            title = ""
            for line in lines[:3]:
                # Skip lines that are just the name repeated or too short
                if line.lower() == link_text.lower() or len(line) < 3:
                    continue
                # Skip lines that look like "View profile" or navigation
                if re.match(r'^(view|see|connect|follow|message)\b', line, re.IGNORECASE):
                    continue
                title = line[:100]  # Cap length
                break

            if not title:
                title = "(see LinkedIn profile)"

            seen_slugs.add(slug)
            contacts.append(Contact(
                name=link_text,
                title=title,
                linkedin_url=f"https://www.linkedin.com/in/{slug}"
            ))

        return contacts

    def _parse_company_html(self, html: str) -> LinkedInCompanyData:
        """Parse LinkedIn company page HTML for structured data."""
        location_count = None
        employee_range = None
        industry = None
        about = None

        # Try JSON-LD structured data first (most reliable)
        jsonld_matches = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        for jsonld_str in jsonld_matches:
            try:
                data = json.loads(jsonld_str)
                if isinstance(data, dict):
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
                        if data.get("numberOfLocations"):
                            location_count = int(data["numberOfLocations"])
                        if data.get("description"):
                            about = data["description"]
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

        # Parse meta tags
        desc_match = re.search(
            r'<meta[^>]*(?:name=["\']description["\']|property=["\']og:description["\'])[^>]*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if desc_match:
            desc = desc_match.group(1)
            if not about:
                about = desc

            if not employee_range:
                emp_match = re.search(r'(\d+[\-–]\d+)\s*employees', desc, re.IGNORECASE)
                if emp_match:
                    employee_range = emp_match.group(1).replace('–', '-')

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

        # Extract people using the shared people HTML parser
        people = self._parse_people_html(html)[:4]

        return LinkedInCompanyData(
            location_count=location_count,
            employee_range=employee_range,
            industry=industry,
            people=people,
            about=about,
        )

    def _parse_company_page(self, markdown: str) -> LinkedInCompanyData:
        """Parse LinkedIn company page markdown to extract structured data.

        Kept for backward compatibility with tests that provide markdown content.
        """
        location_count = None
        employee_range = None
        industry = None
        people = []

        loc_match = re.search(r'(\d+)\s+locations?\b', markdown, re.IGNORECASE)
        if loc_match:
            location_count = int(loc_match.group(1))

        emp_match = re.search(r'(\d+[\-–]\d+)\s*employees', markdown, re.IGNORECASE)
        if not emp_match:
            emp_match = re.search(r'[Cc]ompany\s+size[:\s]*(\d+[\-–]\d+)', markdown)
        if emp_match:
            employee_range = emp_match.group(1).replace('–', '-')

        ind_match = re.search(r'\*\*Industry:?\*\*\s*(.+)', markdown)
        if not ind_match:
            ind_match = re.search(r'Industry[:\s]+([A-Z][^\n]+)', markdown)
        if ind_match:
            industry = ind_match.group(1).strip()

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

    # ── LinkedIn page scrapers ───────────────────────────────────────

    async def scrape_company_page(self, linkedin_url: str) -> LinkedInCompanyData:
        """Scrape a LinkedIn company page and extract structured data.

        Uses FlareSolverr if available for full JS-rendered content.
        """
        try:
            content = await self._fetch_html(linkedin_url, use_flaresolverr=True)
            if not content:
                return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])
            if "<html" in content.lower() or "<!doctype" in content.lower():
                return self._parse_company_html(content)
            else:
                return self._parse_company_page(content)
        except Exception:
            return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])

    async def scrape_people_page(self, linkedin_url: str) -> list[Contact]:
        """Scrape /company/{slug}/people/ for employee contacts.

        Uses FlareSolverr for JS rendering (required for LinkedIn).
        Returns empty list if scraping fails or hits authwall.
        """
        slug = self._extract_company_slug(linkedin_url)
        if not slug:
            return []

        people_url = f"https://www.linkedin.com/company/{slug}/people/"

        try:
            html = await self._fetch_html(people_url, use_flaresolverr=True)
            if not html:
                return []

            if self._is_authwall(html):
                return []

            return self._parse_people_html(html)
        except Exception:
            return []

    # ── Public API ───────────────────────────────────────────────────

    async def find_company(self, company_name: str, website: str) -> Optional[str]:
        return await self._search_linkedin(company_name, website)

    async def find_contacts(
        self,
        company_name: str,
        linkedin_url: Optional[str] = None,
        max_contacts: int = 4
    ) -> list[Contact]:
        """Find contacts, preferring LinkedIn people page scrape, falling back to DDG.

        Args:
            company_name: Company name for DDG search fallback
            linkedin_url: LinkedIn company URL (if known) for direct scraping
            max_contacts: Maximum contacts to return
        """
        contacts = []

        # Primary: scrape LinkedIn people page
        if linkedin_url:
            raw_contacts = await self.scrape_people_page(linkedin_url)
            # Prefer decision-makers
            contacts = self._filter_by_target_titles(raw_contacts)
            # If no title-filtered results, take any contacts we found
            if not contacts and raw_contacts:
                contacts = raw_contacts

        # Fallback: DDG search
        if not contacts:
            contacts = await self._search_people(company_name)

        return contacts[:max_contacts]

    async def enrich(self, company_name: str, website: str) -> CompanyEnrichment:
        """Full enrichment: find company URL -> scrape company page -> scrape people -> combine.

        Fallback chain for contacts:
        1. People page scrape via FlareSolverr (best quality)
        2. Company page people extraction (featured employees)
        3. DDG search (last resort)
        """
        # Step 1: Find LinkedIn company URL
        linkedin_url = await self.find_company(company_name, website)

        # Step 2: Scrape company page for org data
        company_data = None
        if linkedin_url:
            company_data = await self.scrape_company_page(linkedin_url)

        # Step 3: Find contacts (people page scrape -> DDG fallback)
        contacts = await self.find_contacts(company_name, linkedin_url=linkedin_url)

        # Step 4: Merge contacts from company page if we found people there too
        if company_data and company_data.people:
            existing_slugs = set()
            for c in contacts:
                slug_m = re.search(r'/in/([\w-]+)', c.linkedin_url)
                if slug_m:
                    existing_slugs.add(slug_m.group(1))

            for person in company_data.people:
                slug_m = re.search(r'/in/([\w-]+)', person.linkedin_url)
                if slug_m and slug_m.group(1) not in existing_slugs:
                    contacts.append(person)
                    existing_slugs.add(slug_m.group(1))

        return CompanyEnrichment(
            company_name=company_name,
            linkedin_company_url=linkedin_url,
            contacts=contacts[:4]
        )
