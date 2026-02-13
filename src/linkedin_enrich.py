# src/linkedin_enrich.py
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
class CompanyEnrichment:
    company_name: str
    linkedin_company_url: Optional[str]
    contacts: list[Contact]

class LinkedInEnricher:
    FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

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
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.FIRECRAWL_URL,
                headers=self.headers,
                json={"url": url, "formats": ["markdown"]}
            )
            response.raise_for_status()
            return response.json()

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
        except Exception:
            pass

        return contacts

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
