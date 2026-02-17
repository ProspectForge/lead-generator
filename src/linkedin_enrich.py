# src/linkedin_enrich.py
import asyncio
import httpx
import re
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
    FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds

    TARGET_TITLES = [
        "owner", "founder", "co-founder",
        "ceo", "chief executive",
        "coo", "chief operating",
        "president",
        "operations manager", "director of operations",
        "inventory manager", "supply chain manager",
        "retail manager", "store manager"
    ]

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def _fetch_page(self, url: str) -> dict:
        """Fetch page with retry logic."""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        self.FIRECRAWL_URL,
                        headers=self.headers,
                        json={"url": url, "formats": ["markdown"]}
                    )
                    # Check for insufficient credits specifically
                    if response.status_code == 402:
                        raise RuntimeError("Firecrawl API credits exhausted - add credits at https://firecrawl.dev/pricing")
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (503, 429, 500) and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise
        raise last_error

    async def _search_linkedin(self, company_name: str, website: str) -> Optional[str]:
        # Use Google search via Firecrawl to find LinkedIn company page
        search_url = f"https://www.google.com/search?q=site:linkedin.com/company+{company_name.replace(' ', '+')}"
        try:
            data = await self._fetch_page(search_url)
            content = data.get("data", {}).get("markdown", "")

            # Extract LinkedIn company URL from results
            match = re.search(r'linkedin\.com/company/[\w-]+', content)
            if match:
                return f"https://{match.group(0)}"
        except RuntimeError:
            raise  # Re-raise credit exhaustion errors
        except Exception:
            pass
        return None

    async def _search_people(self, company_name: str) -> list[Contact]:
        contacts = []
        search_url = f"https://www.google.com/search?q=site:linkedin.com/in+{company_name.replace(' ', '+')}+CEO+OR+COO+OR+founder+OR+operations"

        try:
            data = await self._fetch_page(search_url)
            content = data.get("data", {}).get("markdown", "")

            # Extract LinkedIn profile URLs and try to parse names/titles
            profile_matches = re.findall(r'linkedin\.com/in/([\w-]+)', content)

            for profile_id in profile_matches[:4]:  # Max 4 contacts
                contacts.append(Contact(
                    name=profile_id.replace("-", " ").title(),
                    title="(to be verified)",
                    linkedin_url=f"https://linkedin.com/in/{profile_id}"
                ))
        except RuntimeError:
            raise  # Re-raise credit exhaustion errors
        except Exception:
            pass

        return contacts

    def _parse_company_page(self, markdown: str) -> LinkedInCompanyData:
        """Parse LinkedIn company page markdown to extract structured data."""
        location_count = None
        employee_range = None
        industry = None
        people = []

        # Extract location count - patterns like "36 locations" or "36 associated members"
        loc_match = re.search(r'(\d+)\s+locations?\b', markdown, re.IGNORECASE)
        if loc_match:
            location_count = int(loc_match.group(1))

        # Extract employee range - patterns like "201-500 employees" or "Company size: 201-500"
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

        # Extract people - look for LinkedIn profile links with names and titles
        # Pattern: [**Name**](linkedin_url)\n Title
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

        # Fallback: look for simpler patterns like "Name\nTitle" near linkedin URLs
        if not people:
            simple_pattern = re.findall(
                r'([\w\s]+?)\s*[-–—|]\s*(?:https?://)?linkedin\.com/in/([\w-]+)',
                markdown
            )
            for name, profile_id in simple_pattern:
                name = name.strip()
                if len(name) > 2 and len(name) < 60:
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
        """Scrape a LinkedIn company page and extract structured data."""
        try:
            data = await self._fetch_page(linkedin_url)
            markdown = data.get("data", {}).get("markdown", "")
            if not markdown:
                return LinkedInCompanyData(location_count=None, employee_range=None, industry=None, people=[])
            return self._parse_company_page(markdown)
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
