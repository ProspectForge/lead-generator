# Marketplace Detection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add marketplace detection (Amazon, eBay, Walmart, Etsy) to the lead generator as a priority signal for qualifying omnichannel retailers.

**Architecture:** Extend the existing `EcommerceChecker` class to detect marketplace links and badges during website crawl. Add `marketplaces` list and `priority` field to output. No new dependencies - uses existing Firecrawl infrastructure.

**Tech Stack:** Python 3.12, pytest, Firecrawl API (existing), regex patterns

---

## Task 1: Add Marketplace Patterns to EcommerceChecker

**Files:**
- Modify: `src/ecommerce_check.py:17-55`

**Step 1: Add marketplace URL patterns**

Add these class constants to `EcommerceChecker` after line 55:

```python
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
```

**Step 2: Verify file saves without syntax errors**

Run: `python -c "from src.ecommerce_check import EcommerceChecker; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/ecommerce_check.py
git commit -m "feat: add marketplace URL and text patterns to EcommerceChecker"
```

---

## Task 2: Update EcommerceResult Dataclass

**Files:**
- Modify: `src/ecommerce_check.py:8-16`
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing test**

Add to `tests/test_ecommerce_check.py`:

```python
def test_ecommerce_result_has_marketplace_fields():
    """EcommerceResult should include marketplace detection fields."""
    result = EcommerceResult(
        url="https://example.com",
        has_ecommerce=True,
        confidence=0.9,
        indicators_found=["platform:shopify"],
        platform="shopify",
        pages_checked=3,
        marketplaces=["amazon", "ebay"],
        marketplace_links={"amazon": "https://amazon.com/stores/example"},
        priority="high"
    )

    assert result.marketplaces == ["amazon", "ebay"]
    assert result.marketplace_links == {"amazon": "https://amazon.com/stores/example"}
    assert result.priority == "high"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py::test_ecommerce_result_has_marketplace_fields -v`
Expected: FAIL with `TypeError: EcommerceResult.__init__() got an unexpected keyword argument 'marketplaces'`

**Step 3: Update EcommerceResult dataclass**

Replace lines 8-16 in `src/ecommerce_check.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py::test_ecommerce_result_has_marketplace_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add marketplace fields to EcommerceResult dataclass"
```

---

## Task 3: Add Marketplace Detection Method

**Files:**
- Modify: `src/ecommerce_check.py`
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing test**

Add to `tests/test_ecommerce_check.py`:

```python
def test_detect_marketplaces_from_links():
    """Should detect marketplace presence from URL patterns."""
    checker = EcommerceChecker(api_key="test_key")

    content = """
    # Our Store

    Find us online:
    - [Amazon Store](https://amazon.com/stores/ExampleBrand)
    - [eBay Shop](https://ebay.com/str/examplebrand)

    Visit our locations for in-person shopping.
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert "amazon" in marketplaces
    assert "ebay" in marketplaces
    assert "amazon" in links
    assert "amazon.com/stores/ExampleBrand" in links["amazon"]


def test_detect_marketplaces_from_text():
    """Should detect marketplace presence from text mentions."""
    checker = EcommerceChecker(api_key="test_key")

    content = """
    # Welcome

    Shop on Amazon for fast Prime shipping!
    Also available on Walmart marketplace.
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert "amazon" in marketplaces
    assert "walmart" in marketplaces


def test_detect_no_marketplaces():
    """Should return empty when no marketplace signals found."""
    checker = EcommerceChecker(api_key="test_key")

    content = """
    # Our Store

    Shop directly on our website for the best prices.
    Free shipping on orders over $50.
    """

    marketplaces, links = checker._detect_marketplaces(content)

    assert marketplaces == []
    assert links == {}
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py::test_detect_marketplaces_from_links tests/test_ecommerce_check.py::test_detect_marketplaces_from_text tests/test_ecommerce_check.py::test_detect_no_marketplaces -v`
Expected: FAIL with `AttributeError: 'EcommerceChecker' object has no attribute '_detect_marketplaces'`

**Step 3: Add _detect_marketplaces method**

Add this method to `EcommerceChecker` class (after `_count_indicators` method, around line 186):

```python
def _detect_marketplaces(self, content: str) -> tuple[list[str], dict[str, str]]:
    """Detect marketplace presence from content.

    Returns:
        tuple of (list of marketplace names, dict of marketplace -> URL)
    """
    marketplaces_found = set()
    marketplace_links = {}
    content_lower = content.lower()

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
                if re.search(pattern, content_lower, re.IGNORECASE):
                    marketplaces_found.add(marketplace)
                    break

    return sorted(list(marketplaces_found)), marketplace_links
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py::test_detect_marketplaces_from_links tests/test_ecommerce_check.py::test_detect_marketplaces_from_text tests/test_ecommerce_check.py::test_detect_no_marketplaces -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: add _detect_marketplaces method to EcommerceChecker"
```

---

## Task 4: Integrate Marketplace Detection into check() Method

**Files:**
- Modify: `src/ecommerce_check.py:188-251` (the `check` method)
- Test: `tests/test_ecommerce_check.py`

**Step 1: Write the failing test**

Add to `tests/test_ecommerce_check.py`:

```python
@pytest.fixture
def ecommerce_with_marketplace_content():
    return """
    # Welcome to Our Store

    Shop our latest collection

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Also find us on [Amazon](https://amazon.com/stores/OurBrand)!

    Free shipping on orders over $50.00
    """


@pytest.mark.asyncio
async def test_check_returns_marketplace_data(ecommerce_with_marketplace_content):
    """check() should return marketplace detection results."""
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [ecommerce_with_marketplace_content]

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert "amazon" in result.marketplaces
        assert result.priority == "high"


@pytest.mark.asyncio
async def test_check_returns_medium_priority_without_marketplace(ecommerce_page_content):
    """check() should return medium priority when no marketplace found."""
    checker = EcommerceChecker(api_key="test_key")

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [ecommerce_page_content]

        result = await checker.check("https://example.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py::test_check_returns_marketplace_data tests/test_ecommerce_check.py::test_check_returns_medium_priority_without_marketplace -v`
Expected: FAIL (marketplaces will be empty, priority will be "medium" for both)

**Step 3: Update check() method to include marketplace detection**

Replace the `check` method in `src/ecommerce_check.py` (starts around line 188):

```python
async def check(self, url: str) -> EcommerceResult:
    """Check if URL has e-commerce and marketplace presence by crawling multiple pages."""
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
            pages_checked=0,
            marketplaces=[],
            marketplace_links={},
            priority="medium"
        )

    all_indicators = []
    total_score = 0
    platform = None
    pages_checked = len(page_contents)
    all_marketplaces = set()
    all_marketplace_links = {}

    # Analyze all crawled pages
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
    has_ecommerce = total_score >= 4 or platform is not None
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_ecommerce_check.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ecommerce_check.py tests/test_ecommerce_check.py
git commit -m "feat: integrate marketplace detection into check() method"
```

---

## Task 5: Update Pipeline to Pass Marketplace Data Through

**Files:**
- Modify: `src/pipeline.py:338-404` (stage_3_ecommerce method)
- Modify: `src/pipeline.py:420-537` (stage_4_linkedin and export)

**Step 1: Update stage_3_ecommerce to capture marketplace data**

In `src/pipeline.py`, the `stage_3_ecommerce` method currently just filters brands with e-commerce. We need to attach marketplace data to the brand.

Find the `stage_3_ecommerce` method (around line 338) and update it to store marketplace data on each brand:

First, add new fields to `BrandGroup` in `src/brand_grouper.py`. Read the file first:

Run: `head -50 /home/farzin/PROSPECTFORGE/lead-generator/src/brand_grouper.py`

**Step 2: Read brand_grouper.py to understand BrandGroup structure**

(This is a research step - examine the file before modifying)

**Step 3: After examining, update BrandGroup dataclass**

Add to `BrandGroup` in `src/brand_grouper.py`:

```python
# Add these fields to the BrandGroup dataclass
marketplaces: list[str] = field(default_factory=list)
marketplace_links: dict[str, str] = field(default_factory=dict)
priority: str = "medium"
```

**Step 4: Update stage_3_ecommerce in pipeline.py**

Update the `check_brand` inner function and result collection (around lines 364-391):

```python
async def check_brand(brand: BrandGroup, progress, task) -> tuple[BrandGroup, bool]:
    """Check a single brand with semaphore for rate limiting."""
    async with semaphore:
        try:
            result = await checker.check(brand.website)
            # Attach marketplace data to brand
            brand.marketplaces = result.marketplaces
            brand.marketplace_links = result.marketplace_links
            brand.priority = result.priority
            progress.advance(task)
            return (brand, result.has_ecommerce)
        except Exception as e:
            console.print(f"  [red]✗ Error: {brand.normalized_name.title()}: {e}[/red]")
            progress.advance(task)
            return (brand, False)
```

**Step 5: Update stage_4_linkedin to include marketplace data in output**

In the `stage_4_linkedin` method, update the enriched dict (around line 481-500) to include:

```python
enriched.append({
    "brand_name": brand_name,
    "location_count": brand.location_count,
    "website": brand.website,
    "has_ecommerce": True,
    "marketplaces": ", ".join(brand.marketplaces),  # NEW
    "priority": brand.priority,  # NEW
    "cities": ", ".join(brand.cities[:5]),
    "linkedin_company": result.linkedin_company_url or "",
    # ... rest of contacts ...
})
```

**Step 6: Update stage_5_export to sort by priority**

In `stage_5_export` method, sort the data before export:

```python
def stage_5_export(self, data: list[dict]) -> str:
    """Export to CSV, sorted by priority."""
    # ... existing checks ...

    with console.status("[cyan]Writing CSV...[/cyan]"):
        df = pd.DataFrame(data)
        # Sort by priority (high first), then by location count
        if 'priority' in df.columns:
            df = df.sort_values(
                by=['priority', 'location_count'],
                ascending=[True, False]  # 'high' < 'medium' alphabetically, so ascending=True puts high first
            )
        # ... rest of export ...
```

Wait - 'high' > 'medium' alphabetically, so we need ascending=False. Let me fix:

```python
# Sort: high priority first, then by location count descending
if 'priority' in df.columns:
    priority_order = {'high': 0, 'medium': 1}
    df['_priority_sort'] = df['priority'].map(priority_order)
    df = df.sort_values(by=['_priority_sort', 'location_count'], ascending=[True, False])
    df = df.drop(columns=['_priority_sort'])
```

**Step 7: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/brand_grouper.py src/pipeline.py
git commit -m "feat: pass marketplace data through pipeline and sort by priority"
```

---

## Task 6: Update Pipeline Checkpoint Serialization

**Files:**
- Modify: `src/pipeline.py:148-172` (_serialize_brand and _deserialize_brand)

**Step 1: Update serialization to include new fields**

Update `_serialize_brand`:

```python
def _serialize_brand(self, brand: BrandGroup) -> dict:
    """Serialize a BrandGroup to dict for checkpoint."""
    return {
        "normalized_name": brand.normalized_name,
        "original_names": brand.original_names,
        "location_count": brand.location_count,
        "locations": brand.locations,
        "website": brand.website,
        "cities": brand.cities,
        "estimated_nationwide": brand.estimated_nationwide,
        "is_large_chain": brand.is_large_chain,
        "marketplaces": brand.marketplaces,  # NEW
        "marketplace_links": brand.marketplace_links,  # NEW
        "priority": brand.priority,  # NEW
    }
```

Update `_deserialize_brand`:

```python
def _deserialize_brand(self, data: dict) -> BrandGroup:
    """Deserialize a dict to BrandGroup."""
    return BrandGroup(
        normalized_name=data["normalized_name"],
        original_names=data.get("original_names", []),
        location_count=data.get("location_count", 0),
        locations=data.get("locations", []),
        website=data.get("website"),
        cities=data.get("cities", []),
        estimated_nationwide=data.get("estimated_nationwide"),
        is_large_chain=data.get("is_large_chain", False),
        marketplaces=data.get("marketplaces", []),  # NEW
        marketplace_links=data.get("marketplace_links", {}),  # NEW
        priority=data.get("priority", "medium"),  # NEW
    )
```

**Step 2: Run tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_pipeline.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/pipeline.py
git commit -m "feat: update checkpoint serialization for marketplace fields"
```

---

## Task 7: Add Integration Test

**Files:**
- Create: `tests/test_marketplace_detection.py`

**Step 1: Create integration test file**

```python
# tests/test_marketplace_detection.py
"""Integration tests for marketplace detection feature."""
import pytest
from unittest.mock import AsyncMock, patch
from src.ecommerce_check import EcommerceChecker


@pytest.mark.asyncio
async def test_full_marketplace_detection_flow():
    """Test complete marketplace detection from website content."""
    checker = EcommerceChecker(api_key="test_key")

    # Simulate a website with Shopify e-commerce AND Amazon/eBay presence
    mock_content = """
    # Welcome to Acme Supplements

    ## Shop Our Products

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Price: $29.99

    ## Also Available On

    - [Shop on Amazon](https://amazon.com/stores/AcmeSupplements)
    - [Our eBay Store](https://ebay.com/str/acmesupplements)

    Free shipping via Shopify!
    cdn.shopify.com/assets/store.js
    """

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_content]

        result = await checker.check("https://acmesupplements.com")

        # Should detect e-commerce
        assert result.has_ecommerce is True
        assert result.platform == "shopify"

        # Should detect marketplaces
        assert "amazon" in result.marketplaces
        assert "ebay" in result.marketplaces
        assert len(result.marketplaces) == 2

        # Should have high priority
        assert result.priority == "high"

        # Should capture links
        assert "amazon" in result.marketplace_links
        assert "amazon.com/stores/AcmeSupplements" in result.marketplace_links["amazon"]


@pytest.mark.asyncio
async def test_ecommerce_without_marketplace():
    """Test e-commerce site without marketplace presence."""
    checker = EcommerceChecker(api_key="test_key")

    mock_content = """
    # Local Fitness Store

    [Add to Cart](/cart)
    [Checkout](/checkout)

    Price: $49.99

    Powered by Shopify
    cdn.shopify.com/assets/store.js
    """

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_content]

        result = await checker.check("https://localfitness.com")

        assert result.has_ecommerce is True
        assert result.marketplaces == []
        assert result.priority == "medium"


@pytest.mark.asyncio
async def test_detects_walmart_and_etsy():
    """Test detection of Walmart and Etsy marketplaces."""
    checker = EcommerceChecker(api_key="test_key")

    mock_content = """
    # Handmade Crafts

    [Buy Now](/shop)
    $19.99

    Available on Walmart marketplace!
    Visit our Etsy shop: https://etsy.com/shop/HandmadeCrafts
    """

    with patch.object(checker, '_crawl_site', new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = [mock_content]

        result = await checker.check("https://handmadecrafts.com")

        assert "walmart" in result.marketplaces
        assert "etsy" in result.marketplaces
        assert result.priority == "high"
```

**Step 2: Run integration tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_marketplace_detection.py -v`
Expected: PASS (3 tests)

**Step 3: Run full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_marketplace_detection.py
git commit -m "test: add integration tests for marketplace detection"
```

---

## Task 8: Final Verification and Cleanup

**Step 1: Run full test suite with coverage**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest --cov=src --cov-report=term-missing -v`
Expected: ALL PASS, good coverage on new code

**Step 2: Verify imports work**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -c "from src.pipeline import Pipeline; from src.ecommerce_check import EcommerceChecker, EcommerceResult; print('All imports OK')"`
Expected: `All imports OK`

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete marketplace detection feature

- Add marketplace URL and text pattern detection
- Extend EcommerceResult with marketplaces, marketplace_links, priority
- Integrate detection into check() method
- Pass marketplace data through pipeline
- Sort output by priority (high first)
- Add comprehensive tests"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add marketplace patterns | `src/ecommerce_check.py` |
| 2 | Update EcommerceResult dataclass | `src/ecommerce_check.py`, `tests/test_ecommerce_check.py` |
| 3 | Add _detect_marketplaces method | `src/ecommerce_check.py`, `tests/test_ecommerce_check.py` |
| 4 | Integrate into check() method | `src/ecommerce_check.py`, `tests/test_ecommerce_check.py` |
| 5 | Update pipeline to pass data through | `src/brand_grouper.py`, `src/pipeline.py` |
| 6 | Update checkpoint serialization | `src/pipeline.py` |
| 7 | Add integration tests | `tests/test_marketplace_detection.py` |
| 8 | Final verification | - |

**Estimated time:** 45-60 minutes
