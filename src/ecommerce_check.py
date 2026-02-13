# src/ecommerce_check.py
import asyncio
import httpx
from dataclasses import dataclass, field
from typing import Optional
import re

@dataclass
class EcommerceResult:
    url: str
    has_ecommerce: bool
    confidence: float
    indicators_found: list[str] = field(default_factory=list)
    platform: Optional[str] = None
    pages_checked: int = 0
    marketplaces: list[str] = field(default_factory=list)
    marketplace_links: dict[str, str] = field(default_factory=dict)
    priority: str = "medium"  # "high" if marketplaces, "medium" otherwise

class EcommerceChecker:
    FIRECRAWL_CRAWL_URL = "https://api.firecrawl.dev/v2/crawl"
    DEFAULT_PAGES_TO_CHECK = 3
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds
    POLL_INTERVAL = 2  # Seconds between status checks
    MAX_POLL_TIME = 60  # Maximum seconds to wait for crawl completion

    # E-commerce platform signatures (high confidence)
    PLATFORM_SIGNATURES = {
        "shopify": [r'cdn\.shopify\.com', r'myshopify\.com', r'shopify-assets'],
        "woocommerce": [r'woocommerce', r'wc-cart', r'add_to_cart'],
        "bigcommerce": [r'bigcommerce\.com', r'cdn\.bc'],
        "squarespace": [r'squarespace.*commerce', r'sqs-add-to-cart'],
        "magento": [r'mage/', r'magento', r'varien'],
        "shopware": [r'shopware'],
        "prestashop": [r'prestashop'],
    }

    # E-commerce action patterns
    ECOMMERCE_PATTERNS = [
        r'add.to.cart',
        r'add.to.bag',
        r'buy.now',
        r'shop.now',
        r'checkout',
        r'shopping.cart',
        r'view.cart',
    ]

    # Payment indicators
    PAYMENT_PATTERNS = [
        r'stripe\.com',
        r'paypal\.com',
        r'square\.com',
        r'klarna',
        r'afterpay',
        r'affirm',
    ]

    # Price patterns
    PRICE_PATTERNS = [
        r'\$\d+\.\d{2}',
        r'USD\s*\d+',
        r'CAD\s*\d+',
    ]

    # Marketplace URL patterns
    MARKETPLACE_PATTERNS = {
        "amazon": [
            r'amazon\.com/stores/',
            r'amazon\.com/sp\?seller=',
            r'amazon\.com/s\?me=',
            r'amazon\.ca/stores/',
            r'amazon\.co\.uk/stores/',
        ],
        "ebay": [
            r'ebay\.com/str/',
            r'ebay\.com/usr/',
            r'ebay\.ca/str/',
            r'ebay\.co\.uk/str/',
        ],
        "walmart": [
            r'walmart\.com/seller/',
            r'marketplace\.walmart\.com',
        ],
        "etsy": [
            r'etsy\.com/shop/',
        ],
    }

    # Marketplace text/badge indicators
    MARKETPLACE_TEXT_PATTERNS = {
        "amazon": [
            r'shop\s+on\s+amazon',
            r'buy\s+on\s+amazon',
            r'available\s+on\s+amazon',
            r'our\s+amazon\s+store',
            r'amazon\s+prime',
            r'find\s+us\s+on\s+amazon',
        ],
        "ebay": [
            r'shop\s+on\s+ebay',
            r'our\s+ebay\s+store',
            r'find\s+us\s+on\s+ebay',
            r'ebay\s+store',
        ],
        "walmart": [
            r'available\s+on\s+walmart',
            r'shop\s+on\s+walmart',
            r'walmart\s+marketplace',
        ],
        "etsy": [
            r'shop\s+on\s+etsy',
            r'our\s+etsy\s+shop',
            r'find\s+us\s+on\s+etsy',
        ],
    }

    def __init__(self, api_key: str, pages_to_check: int = None):
        self.api_key = api_key
        self.pages_to_check = pages_to_check or self.DEFAULT_PAGES_TO_CHECK
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def _start_crawl(self, url: str, client: httpx.AsyncClient) -> Optional[str]:
        """Start a crawl job and return the job ID."""
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.post(
                    self.FIRECRAWL_CRAWL_URL,
                    headers=self.headers,
                    json={
                        "url": url,
                        "limit": self.pages_to_check,
                        "scrapeOptions": {
                            "formats": ["markdown"]
                        }
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("id")
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (503, 429, 500) and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                return None
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                return None
            except Exception:
                return None
        return None

    async def _poll_crawl_status(self, crawl_id: str, client: httpx.AsyncClient) -> Optional[list[dict]]:
        """Poll for crawl completion and return the crawled pages."""
        status_url = f"{self.FIRECRAWL_CRAWL_URL}/{crawl_id}"
        elapsed = 0

        while elapsed < self.MAX_POLL_TIME:
            try:
                response = await client.get(status_url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                status = data.get("status")
                if status == "completed":
                    return data.get("data", [])
                elif status == "failed":
                    return None

                # Still processing, wait and poll again
                await asyncio.sleep(self.POLL_INTERVAL)
                elapsed += self.POLL_INTERVAL

            except Exception:
                return None

        return None  # Timeout

    async def _crawl_site(self, url: str) -> list[str]:
        """Crawl site using Firecrawl v2 crawl endpoint, return list of page contents."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Start the crawl
            crawl_id = await self._start_crawl(url, client)
            if not crawl_id:
                return []

            # Poll for results
            pages = await self._poll_crawl_status(crawl_id, client)
            if not pages:
                return []

            # Extract markdown content from each page
            contents = []
            for page in pages:
                markdown = page.get("markdown", "")
                if markdown:
                    contents.append(markdown)

            return contents

    def _detect_platform(self, content: str) -> Optional[str]:
        """Detect e-commerce platform from content."""
        content_lower = content.lower()
        for platform, patterns in self.PLATFORM_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    return platform
        return None

    def _count_indicators(self, content: str) -> tuple[list[str], int]:
        """Count e-commerce indicators in content."""
        content_lower = content.lower()
        indicators = []
        score = 0

        # Check e-commerce action patterns (weight: 2)
        for pattern in self.ECOMMERCE_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                indicators.append(f"action:{pattern}")
                score += 2

        # Check payment patterns (weight: 3)
        for pattern in self.PAYMENT_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                indicators.append(f"payment:{pattern}")
                score += 3

        # Check price patterns (weight: 1)
        for pattern in self.PRICE_PATTERNS:
            if re.search(pattern, content_lower):
                indicators.append(f"price:{pattern}")
                score += 1
                break  # Only count once

        return indicators, score

    def _detect_marketplaces(self, content: str) -> tuple[list[str], dict[str, str]]:
        """Detect marketplace presence from content.

        Returns:
            tuple of (list of marketplace names, dict of marketplace -> URL)
        """
        marketplaces_found = set()
        marketplace_links = {}

        # Check URL patterns (also try to extract the actual URL)
        for marketplace, patterns in self.MARKETPLACE_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    marketplaces_found.add(marketplace)
                    # Try to extract full URL
                    url_pattern = rf'https?://[^\s\)\]"\'<>]*{pattern}[^\s\)\]"\'<>]*'
                    url_match = re.search(url_pattern, content, re.IGNORECASE)
                    if url_match and marketplace not in marketplace_links:
                        marketplace_links[marketplace] = url_match.group(0)
                    break

        # Check text/badge patterns
        for marketplace, patterns in self.MARKETPLACE_TEXT_PATTERNS.items():
            if marketplace not in marketplaces_found:
                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        marketplaces_found.add(marketplace)
                        break

        return sorted(list(marketplaces_found)), marketplace_links

    async def check(self, url: str) -> EcommerceResult:
        """Check if URL has e-commerce by crawling multiple pages."""
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        base_url = url.rstrip('/')

        # Crawl the site (up to pages_to_check pages)
        page_contents = await self._crawl_site(base_url)

        if not page_contents:
            # Crawl failed, return negative result
            return EcommerceResult(
                url=url,
                has_ecommerce=False,
                confidence=0.0,
                indicators_found=[],
                platform=None,
                pages_checked=0
            )

        all_indicators = []
        total_score = 0
        platform = None
        pages_checked = len(page_contents)

        # Analyze all crawled pages
        for content in page_contents:
            # Check for platform
            if not platform:
                platform = self._detect_platform(content)

            # Count indicators
            indicators, score = self._count_indicators(content)
            all_indicators.extend(indicators)
            total_score += score

            # If platform detected, high confidence
            if platform:
                return EcommerceResult(
                    url=url,
                    has_ecommerce=True,
                    confidence=0.95,
                    indicators_found=[f"platform:{platform}"] + list(set(all_indicators)),
                    platform=platform,
                    pages_checked=pages_checked
                )

            # Early exit if score is high enough
            if total_score >= 6:
                break

        # Calculate final result
        has_ecommerce = total_score >= 4 or platform is not None
        confidence = min(total_score / 10, 1.0) if has_ecommerce else total_score / 15

        return EcommerceResult(
            url=url,
            has_ecommerce=has_ecommerce,
            confidence=confidence,
            indicators_found=list(set(all_indicators)),
            platform=platform,
            pages_checked=pages_checked
        )
