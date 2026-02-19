# src/ecommerce_check.py
import asyncio
import httpx
import random
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
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
    crawl_failed: bool = False  # True when fetching failed entirely
    fail_reason: Optional[str] = None  # Why the fetch failed

class EcommerceChecker:
    DEFAULT_PAGES_TO_CHECK = 3
    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]
    REQUEST_TIMEOUT = 15.0

    # Common shop page paths to probe after the homepage
    SHOP_PATHS = [
        "/shop", "/store", "/products", "/collections",
        "/collections/all", "/shop/all", "/catalog",
    ]

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    # E-commerce platform signatures (high confidence)
    PLATFORM_SIGNATURES = {
        # Existing platforms
        "shopify": [r'cdn\.shopify\.com', r'myshopify\.com', r'shopify-assets'],
        "woocommerce": [r'wp-content/plugins/woocommerce', r'woocommerce', r'wc-add-to-cart', r'wp-json/wc/'],
        "bigcommerce": [r'bigcommerce\.com', r'cdn\.bc'],
        "squarespace": [r'squarespace-commerce', r'sqs-add-to-cart', r'squarespace\.com/commerce'],
        "magento": [r'Mage\.Cookies', r'mage/cookies', r'/static/version\d+/', r'Magento_Ui', r'magento-init', r'data-mage-init', r'varien/js'],
        "shopware": [r'shopware'],
        "prestashop": [r'prestashop'],
        # New platforms
        "wix": [r'wixsite\.com', r'static\.wixstatic\.com', r'wix-ecommerce', r'_api/wix-ecommerce'],
        "ecwid": [r'ecwid\.com', r'app\.ecwid\.com', r'Ecwid\.Cart'],
        "volusion": [r'volusion\.com', r'stor\.vo\.llnwd\.net', r'/v/vspfiles/'],
        "shift4shop": [r'shift4shop\.com', r'3dcart\.com', r'3dcartstores\.com'],
        "opencart": [r'route=product', r'route=checkout'],
        "salesforce_commerce": [r'demandware\.net', r'demandware\.static', r'dw/shop/v'],
        "sap_commerce": [r'/yacceleratorstorefront/'],
        "snipcart": [r'snipcart\.com', r'snipcart-add-item', r'class="snipcart-'],
    }

    # E-commerce action patterns (use explicit separators, not regex wildcards)
    ECOMMERCE_PATTERNS = [
        r'add[\s_\-]to[\s_\-]cart',
        r'add[\s_\-]to[\s_\-]bag',
        r'\bbuy[\s_\-]now\b',
        r'\bshop[\s_\-]now\b',
        r'\bcheckout\b',
        r'shopping[\s_\-]cart',
        r'view[\s_\-]cart',
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

    def __init__(self, pages_to_check: int = None, **kwargs):
        self.pages_to_check = pages_to_check or self.DEFAULT_PAGES_TO_CHECK

    async def _fetch_page(self, url: str, client: httpx.AsyncClient) -> tuple[Optional[str], Optional[str], Optional[httpx.Headers]]:
        """Fetch a single page's HTML with retries. Returns (html, error_reason, headers)."""
        for attempt in range(self.MAX_RETRIES):
            try:
                ua = random.choice(self.USER_AGENTS)
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={
                        "User-Agent": ua,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                    },
                )
                # Retry on rate limit with longer backoff + jitter
                if response.status_code == 429:
                    if attempt < self.MAX_RETRIES - 1:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            delay = min(int(retry_after), 30)
                        else:
                            delay = self.RETRY_DELAYS[attempt]
                        jitter = random.uniform(0.5, 2.0)
                        await asyncio.sleep(delay + jitter)
                        continue
                    return None, "HTTP 429", None
                if response.status_code >= 400:
                    return None, f"HTTP {response.status_code}", None
                return response.text, None, response.headers
            except httpx.TimeoutException:
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                return None, "Timeout", None
            except httpx.ConnectError:
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                    continue
                return None, "Connection failed", None
            except Exception as e:
                return None, str(type(e).__name__), None
        return None, "Max retries", None

    async def _fetch_site_pages(self, url: str) -> tuple[list[str], Optional[str], list[httpx.Headers]]:
        """Fetch homepage + shop pages directly via HTTP. Returns (pages, fail_reason, all_headers)."""
        all_headers = []
        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            # Always fetch homepage first
            homepage, fail_reason, headers = await self._fetch_page(url, client)
            if not homepage:
                return [], fail_reason, []

            pages = [homepage]
            if headers:
                all_headers.append(headers)

            # If we already detect a platform from the homepage, skip probing extra pages
            if self._detect_platform(homepage):
                return pages, None, all_headers

            # Probe common shop paths for additional signals
            pages_needed = self.pages_to_check - 1
            if pages_needed <= 0:
                return pages, None, all_headers

            # Also look for shop links in the homepage HTML
            discovered_paths = self._find_shop_links(homepage, url)
            paths_to_try = discovered_paths + [
                p for p in self.SHOP_PATHS if p not in discovered_paths
            ]

            for path in paths_to_try[:pages_needed * 2]:  # Try more paths than needed
                page_url = urljoin(url + "/", path.lstrip("/"))
                html, _, page_headers = await self._fetch_page(page_url, client)
                if html and len(html) > 500:  # Skip trivial error pages
                    pages.append(html)
                    if page_headers:
                        all_headers.append(page_headers)
                    if len(pages) >= self.pages_to_check:
                        break

            return pages, None, all_headers

    def _find_shop_links(self, html: str, base_url: str) -> list[str]:
        """Extract likely shop/product page paths from homepage HTML."""
        paths = []
        parsed_base = urlparse(base_url)
        # Look for links to shop/product pages in nav, header, etc.
        link_pattern = re.findall(
            r'href=["\']([^"\']*(?:shop|store|products|collections|catalog)[^"\']*)["\']',
            html, re.IGNORECASE
        )
        for href in link_pattern:
            parsed = urlparse(href)
            # Only same-domain or relative paths
            if parsed.netloc and parsed.netloc != parsed_base.netloc:
                continue
            path = parsed.path
            if path and path not in paths and path != "/":
                paths.append(path)
        return paths[:5]

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
        """Check if URL has e-commerce and marketplace presence by fetching pages directly."""
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        base_url = url.rstrip('/')

        # Fetch pages directly via HTTP
        page_contents, fail_reason, page_headers = await self._fetch_site_pages(base_url)

        if not page_contents:
            return EcommerceResult(
                url=url,
                has_ecommerce=False,
                confidence=0.0,
                indicators_found=[],
                platform=None,
                pages_checked=0,
                marketplaces=[],
                marketplace_links={},
                priority="medium",
                crawl_failed=True,
                fail_reason=fail_reason,
            )

        all_indicators = []
        total_score = 0
        platform = None
        pages_checked = len(page_contents)
        all_marketplaces = set()
        all_marketplace_links = {}

        # Analyze all fetched pages
        for content in page_contents:
            # Check for platform
            if not platform:
                platform = self._detect_platform(content)

            # Count indicators
            indicators, score = self._count_indicators(content)
            all_indicators.extend(indicators)
            total_score += score

            # Detect marketplaces
            marketplaces, links = self._detect_marketplaces(content)
            all_marketplaces.update(marketplaces)
            for mp, link in links.items():
                if mp not in all_marketplace_links:
                    all_marketplace_links[mp] = link

        # Calculate final result
        # Require either: a detected platform, OR a payment/price signal + action patterns,
        # OR a very high score from multiple categories
        has_payment_or_price = any(
            "payment:" in i or "price:" in i for i in all_indicators
        )
        has_ecommerce = (
            platform is not None
            or (total_score >= 4 and has_payment_or_price)
            or total_score >= 8
        )
        confidence = min(total_score / 10, 1.0) if has_ecommerce else total_score / 15

        # Determine priority based on marketplace presence
        final_marketplaces = sorted(list(all_marketplaces))
        priority = "high" if final_marketplaces else "medium"

        # If platform detected, high confidence
        if platform:
            return EcommerceResult(
                url=url,
                has_ecommerce=True,
                confidence=0.95,
                indicators_found=[f"platform:{platform}"] + list(set(all_indicators)),
                platform=platform,
                pages_checked=pages_checked,
                marketplaces=final_marketplaces,
                marketplace_links=all_marketplace_links,
                priority=priority
            )

        return EcommerceResult(
            url=url,
            has_ecommerce=has_ecommerce,
            confidence=confidence,
            indicators_found=list(set(all_indicators)),
            platform=platform,
            pages_checked=pages_checked,
            marketplaces=final_marketplaces,
            marketplace_links=all_marketplace_links,
            priority=priority
        )
