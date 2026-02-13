# src/apollo_enrich.py
"""
Apollo.io enrichment module for B2B contact data.

To enable:
1. Get API key from https://app.apollo.io/
2. Set APOLLO_API_KEY in .env
3. Set enrichment.provider = "apollo" in config/cities.json

Apollo provides:
- Verified email addresses
- Phone numbers
- Job titles
- Company data (size, industry, revenue)
"""
import asyncio
import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class ApolloContact:
    name: str
    email: Optional[str]
    phone: Optional[str]
    title: str
    linkedin_url: Optional[str]


@dataclass
class ApolloCompany:
    name: str
    domain: str
    industry: Optional[str]
    employee_count: Optional[int]
    estimated_revenue: Optional[str]
    linkedin_url: Optional[str]


@dataclass
class ApolloEnrichment:
    company: ApolloCompany
    contacts: list[ApolloContact]


class ApolloEnricher:
    """Enriches leads using Apollo.io API."""

    BASE_URL = "https://api.apollo.io/v1"
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]

    # Target titles for decision makers
    TARGET_TITLES = [
        "owner", "founder", "co-founder",
        "ceo", "chief executive officer",
        "coo", "chief operating officer",
        "president",
        "general manager",
        "operations manager", "director of operations",
        "vp operations", "vice president operations",
    ]

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

    async def _make_request(self, endpoint: str, payload: dict) -> dict:
        """Make API request with retry logic."""
        url = f"{self.BASE_URL}/{endpoint}"
        payload["api_key"] = self.api_key

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url,
                        headers=self.headers,
                        json=payload
                    )

                    # Handle rate limiting
                    if response.status_code == 429:
                        if attempt < self.MAX_RETRIES - 1:
                            await asyncio.sleep(self.RETRY_DELAYS[attempt])
                            continue

                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (503, 500) and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                raise

        raise last_error

    async def search_company(self, company_name: str, domain: str) -> Optional[ApolloCompany]:
        """Search for a company by name and domain."""
        try:
            # Use domain search for better accuracy
            data = await self._make_request("organizations/enrich", {
                "domain": domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            })

            org = data.get("organization")
            if not org:
                return None

            return ApolloCompany(
                name=org.get("name", company_name),
                domain=org.get("primary_domain", domain),
                industry=org.get("industry"),
                employee_count=org.get("estimated_num_employees"),
                estimated_revenue=org.get("annual_revenue_printed"),
                linkedin_url=org.get("linkedin_url"),
            )

        except Exception:
            return None

    async def search_contacts(
        self,
        company_name: str,
        domain: str,
        max_contacts: int = 4
    ) -> list[ApolloContact]:
        """Search for decision-maker contacts at a company."""
        contacts = []

        try:
            # Search for people at the company with target titles
            data = await self._make_request("mixed_people/search", {
                "q_organization_domains": domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0],
                "person_titles": self.TARGET_TITLES,
                "page": 1,
                "per_page": max_contacts,
            })

            people = data.get("people", [])

            for person in people[:max_contacts]:
                contacts.append(ApolloContact(
                    name=person.get("name", ""),
                    email=person.get("email"),
                    phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                    title=person.get("title", ""),
                    linkedin_url=person.get("linkedin_url"),
                ))

        except Exception:
            pass

        return contacts

    async def enrich(
        self,
        company_name: str,
        website: str,
        max_contacts: int = 4
    ) -> Optional[ApolloEnrichment]:
        """
        Full enrichment: company data + contacts.

        Args:
            company_name: Name of the company
            website: Company website URL
            max_contacts: Maximum contacts to return

        Returns:
            ApolloEnrichment with company and contacts data
        """
        # Get company data
        company = await self.search_company(company_name, website)
        if not company:
            # Create minimal company object if not found
            domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            company = ApolloCompany(
                name=company_name,
                domain=domain,
                industry=None,
                employee_count=None,
                estimated_revenue=None,
                linkedin_url=None,
            )

        # Get contacts
        contacts = await self.search_contacts(company_name, website, max_contacts)

        return ApolloEnrichment(
            company=company,
            contacts=contacts,
        )
