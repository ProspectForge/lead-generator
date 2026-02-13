# src/ecommerce_check.py
import httpx
from dataclasses import dataclass
from typing import Optional
import re

@dataclass
class EcommerceResult:
    url: str
    has_ecommerce: bool
    confidence: float
    indicators_found: list[str]

class EcommerceChecker:
    FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

    # Patterns indicating e-commerce functionality
    ECOMMERCE_PATTERNS = [
        r'add.to.cart',
        r'checkout',
        r'shopping.cart',
        r'buy.now',
        r'shop.now',
        r'add.to.bag',
        r'/cart',
        r'/checkout',
        r'/shop',
        r'/store',
        r'price:\s*\$',
        r'\$\d+\.\d{2}',
        r'free.shipping',
        r'add.to.wishlist',
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

    async def check(self, url: str) -> EcommerceResult:
        try:
            data = await self._fetch_page(url)
            content = data.get("data", {}).get("markdown", "").lower()

            indicators_found = []
            for pattern in self.ECOMMERCE_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    indicators_found.append(pattern)

            confidence = min(len(indicators_found) / 5, 1.0)  # Max confidence at 5+ indicators
            has_ecommerce = len(indicators_found) >= 2

            return EcommerceResult(
                url=url,
                has_ecommerce=has_ecommerce,
                confidence=confidence,
                indicators_found=indicators_found
            )
        except Exception as e:
            return EcommerceResult(
                url=url,
                has_ecommerce=False,
                confidence=0.0,
                indicators_found=[f"error: {str(e)}"]
            )
