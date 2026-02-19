# tests/test_linkedin_enrich.py
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from src.linkedin_enrich import LinkedInEnricher, Contact, LinkedInCompanyData

@pytest.fixture
def mock_company_page():
    return {
        "data": {
            "markdown": """
            # Lululemon on LinkedIn

            linkedin.com/company/lululemon

            ## People
            - John Smith - CEO
            - Jane Doe - COO
            - Bob Wilson - Operations Manager
            """
        }
    }

@pytest.mark.asyncio
async def test_finds_company_linkedin_page(mock_company_page):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_search_linkedin', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = "https://linkedin.com/company/lululemon"

        result = await enricher.find_company("Lululemon", "https://lululemon.com")

        assert result == "https://linkedin.com/company/lululemon"

@pytest.mark.asyncio
async def test_finds_contacts_by_title():
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            Contact(name="John Smith", title="CEO", linkedin_url="https://linkedin.com/in/johnsmith"),
            Contact(name="Jane Doe", title="COO", linkedin_url="https://linkedin.com/in/janedoe"),
        ]

        contacts = await enricher.find_contacts("Lululemon", max_contacts=4)

        assert len(contacts) == 2
        assert contacts[0].title == "CEO"


@pytest.fixture
def linkedin_company_page_markdown():
    """Realistic LinkedIn company page markdown."""
    return """
# Flaman Fitness

## About

Flaman Fitness is a leading Canadian retailer of fitness equipment.

**Industry:** Retail
**Company size:** 201-500 employees
**Headquarters:** Saskatoon, Saskatchewan
**Founded:** 1959

**Specialties:** Fitness Equipment, Treadmills, Exercise Bikes

36 locations

## People

### Leadership

[**John Macdonell**](https://www.linkedin.com/in/john-macdonell)
CEO

[**Sarah Thompson**](https://www.linkedin.com/in/sarah-thompson-fitness)
Chief Operating Officer

[**Mike Rodriguez**](https://www.linkedin.com/in/mike-rodriguez-ab)
Director of Operations

[**Lisa Chen**](https://www.linkedin.com/in/lisa-chen-retail)
Marketing Manager
"""


@pytest.fixture
def linkedin_page_no_locations():
    """LinkedIn page without location count."""
    return """
# Small Store Co

## About

**Industry:** Retail
**Company size:** 11-50 employees

## People

[**Jane Owner**](https://www.linkedin.com/in/jane-owner)
Founder & CEO
"""


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_locations(linkedin_company_page_markdown):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert result.location_count == 36


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_people(linkedin_company_page_markdown):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert len(result.people) >= 3
    # Check first person
    assert result.people[0].name == "John Macdonell"
    assert "CEO" in result.people[0].title


@pytest.mark.asyncio
async def test_scrape_company_page_extracts_employee_range(linkedin_company_page_markdown):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_company_page_markdown

        result = await enricher.scrape_company_page("https://linkedin.com/company/flaman-fitness-ca")

    assert result.employee_range == "201-500"


@pytest.mark.asyncio
async def test_scrape_company_page_handles_missing_locations(linkedin_page_no_locations):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = linkedin_page_no_locations

        result = await enricher.scrape_company_page("https://linkedin.com/company/small-store")

    assert result.location_count is None
    assert len(result.people) >= 1


@pytest.mark.asyncio
async def test_scrape_company_page_handles_fetch_failure():
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("Connection failed")

        result = await enricher.scrape_company_page("https://linkedin.com/company/broken")

    assert result.location_count is None
    assert result.people == []


# ── People page parsing tests ────────────────────────────────────

@pytest.fixture
def people_page_html_with_links():
    """LinkedIn people page HTML with profile links."""
    return """
    <html>
    <body>
    <div class="org-people-profiles-module">
        <a href="https://www.linkedin.com/in/john-macdonell">John Macdonell</a>
        <div class="title">CEO at Flaman Fitness</div>

        <a href="https://www.linkedin.com/in/sarah-thompson-fit">Sarah Thompson</a>
        <div class="title">Chief Operating Officer</div>

        <a href="https://www.linkedin.com/in/mike-rodriguez-ops">Mike Rodriguez</a>
        <div class="title">Director of Operations</div>

        <a href="https://www.linkedin.com/in/dev-intern-123">Dev Intern</a>
        <div class="title">Software Engineering Intern</div>
    </div>
    </body>
    </html>
    """


@pytest.fixture
def people_page_html_with_json():
    """LinkedIn people page HTML with embedded JSON profile data."""
    return """
    <html>
    <body>
    <script type="application/javascript">
    {"included":[{"firstName":"Alice","lastName":"Johnson","headline":"Founder & CEO","publicIdentifier":"alice-johnson-ceo"}]}
    </script>
    </body>
    </html>
    """


@pytest.fixture
def authwall_html():
    """LinkedIn authwall page HTML."""
    return """
    <html>
    <head><title>Sign In to LinkedIn</title></head>
    <body>
    <div class="authwall">
        <h1>Join LinkedIn</h1>
        <form id="loginForm">
            <input type="email" name="session_key" />
        </form>
    </div>
    </body>
    </html>
    """


def test_parse_people_html_extracts_from_links(people_page_html_with_links):
    enricher = LinkedInEnricher()
    contacts = enricher._parse_people_html(people_page_html_with_links)

    assert len(contacts) >= 3
    slugs = [c.linkedin_url.split("/in/")[-1] for c in contacts]
    assert "john-macdonell" in slugs
    assert "sarah-thompson-fit" in slugs
    assert "mike-rodriguez-ops" in slugs

    # Check name and title extraction
    john = next(c for c in contacts if "john-macdonell" in c.linkedin_url)
    assert john.name == "John Macdonell"


def test_parse_people_html_extracts_from_json(people_page_html_with_json):
    enricher = LinkedInEnricher()
    contacts = enricher._parse_people_html(people_page_html_with_json)

    assert len(contacts) >= 1
    alice = contacts[0]
    assert alice.name == "Alice Johnson"
    assert "Founder" in alice.title or "CEO" in alice.title
    assert "alice-johnson-ceo" in alice.linkedin_url


def test_parse_people_html_deduplicates():
    """Profiles found in both JSON and links should not be duplicated."""
    enricher = LinkedInEnricher()
    html = """
    <html>
    <script>{"firstName":"John","lastName":"Doe","headline":"CEO","publicIdentifier":"john-doe"}</script>
    <body>
    <a href="https://www.linkedin.com/in/john-doe">John Doe</a>
    <div>CEO</div>
    </body>
    </html>
    """
    contacts = enricher._parse_people_html(html)
    slugs = [c.linkedin_url.split("/in/")[-1] for c in contacts]
    assert slugs.count("john-doe") == 1


def test_parse_people_html_empty():
    enricher = LinkedInEnricher()
    contacts = enricher._parse_people_html("<html><body>No profiles here</body></html>")
    assert contacts == []


# ── Authwall detection tests ─────────────────────────────────────

def test_is_authwall_detects_login_page(authwall_html):
    assert LinkedInEnricher._is_authwall(authwall_html) is True


def test_is_authwall_passes_real_content(people_page_html_with_links):
    assert LinkedInEnricher._is_authwall(people_page_html_with_links) is False


# ── Company slug extraction tests ────────────────────────────────

def test_extract_company_slug():
    assert LinkedInEnricher._extract_company_slug("https://www.linkedin.com/company/flaman-fitness") == "flaman-fitness"
    assert LinkedInEnricher._extract_company_slug("https://linkedin.com/company/lululemon/") == "lululemon"
    assert LinkedInEnricher._extract_company_slug("https://example.com/not-linkedin") is None


# ── Title filtering tests ────────────────────────────────────────

def test_filter_by_target_titles():
    enricher = LinkedInEnricher()
    contacts = [
        Contact(name="Alice", title="CEO", linkedin_url="https://linkedin.com/in/alice"),
        Contact(name="Bob", title="Software Engineer", linkedin_url="https://linkedin.com/in/bob"),
        Contact(name="Carol", title="Founder & COO", linkedin_url="https://linkedin.com/in/carol"),
        Contact(name="Dave", title="Marketing Intern", linkedin_url="https://linkedin.com/in/dave"),
        Contact(name="Eve", title="Store Manager", linkedin_url="https://linkedin.com/in/eve"),
    ]
    filtered = enricher._filter_by_target_titles(contacts)

    names = [c.name for c in filtered]
    assert "Alice" in names
    assert "Carol" in names
    assert "Eve" in names
    assert "Bob" not in names
    assert "Dave" not in names


def test_filter_by_target_titles_empty():
    enricher = LinkedInEnricher()
    contacts = [
        Contact(name="Bob", title="Software Engineer", linkedin_url="https://linkedin.com/in/bob"),
    ]
    assert enricher._filter_by_target_titles(contacts) == []


# ── scrape_people_page tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_scrape_people_page_uses_flaresolverr(people_page_html_with_links):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = people_page_html_with_links

        contacts = await enricher.scrape_people_page("https://www.linkedin.com/company/flaman-fitness")

    # Verify it called _fetch_html with the /people/ URL and flaresolverr flag
    mock_fetch.assert_called_once_with(
        "https://www.linkedin.com/company/flaman-fitness/people/",
        use_flaresolverr=True,
    )
    assert len(contacts) >= 3


@pytest.mark.asyncio
async def test_scrape_people_page_handles_authwall(authwall_html):
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = authwall_html

        contacts = await enricher.scrape_people_page("https://www.linkedin.com/company/test-co")

    assert contacts == []


@pytest.mark.asyncio
async def test_scrape_people_page_handles_bad_url():
    enricher = LinkedInEnricher()

    contacts = await enricher.scrape_people_page("https://example.com/not-a-linkedin-url")

    assert contacts == []


@pytest.mark.asyncio
async def test_scrape_people_page_handles_fetch_failure():
    enricher = LinkedInEnricher()

    with patch.object(enricher, '_fetch_html', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        contacts = await enricher.scrape_people_page("https://www.linkedin.com/company/test-co")

    assert contacts == []


# ── find_contacts preference/fallback tests ──────────────────────

@pytest.mark.asyncio
async def test_find_contacts_prefers_people_page():
    """When people page returns contacts, DDG search should NOT be called."""
    enricher = LinkedInEnricher()

    people_contacts = [
        Contact(name="Alice CEO", title="CEO", linkedin_url="https://linkedin.com/in/alice-ceo"),
        Contact(name="Bob COO", title="COO", linkedin_url="https://linkedin.com/in/bob-coo"),
    ]

    with patch.object(enricher, 'scrape_people_page', new_callable=AsyncMock) as mock_scrape, \
         patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_ddg:
        mock_scrape.return_value = people_contacts

        contacts = await enricher.find_contacts(
            "Test Co", linkedin_url="https://linkedin.com/company/test-co"
        )

    assert len(contacts) == 2
    assert contacts[0].name == "Alice CEO"
    mock_ddg.assert_not_called()


@pytest.mark.asyncio
async def test_find_contacts_falls_back_to_ddg():
    """When people page returns empty, DDG search should be used as fallback."""
    enricher = LinkedInEnricher()

    ddg_contacts = [
        Contact(name="DDG Found", title="Owner", linkedin_url="https://linkedin.com/in/ddg-found"),
    ]

    with patch.object(enricher, 'scrape_people_page', new_callable=AsyncMock) as mock_scrape, \
         patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_ddg:
        mock_scrape.return_value = []
        mock_ddg.return_value = ddg_contacts

        contacts = await enricher.find_contacts(
            "Test Co", linkedin_url="https://linkedin.com/company/test-co"
        )

    assert len(contacts) == 1
    assert contacts[0].name == "DDG Found"
    mock_ddg.assert_called_once()


@pytest.mark.asyncio
async def test_find_contacts_ddg_only_when_no_linkedin_url():
    """When no linkedin_url is provided, only DDG search is used."""
    enricher = LinkedInEnricher()

    with patch.object(enricher, 'scrape_people_page', new_callable=AsyncMock) as mock_scrape, \
         patch.object(enricher, '_search_people', new_callable=AsyncMock) as mock_ddg:
        mock_ddg.return_value = [
            Contact(name="Found", title="CEO", linkedin_url="https://linkedin.com/in/found"),
        ]

        contacts = await enricher.find_contacts("Test Co")

    mock_scrape.assert_not_called()
    assert len(contacts) == 1


@pytest.mark.asyncio
async def test_find_contacts_filters_by_title():
    """When people page returns mixed titles, decision-makers are preferred."""
    enricher = LinkedInEnricher()

    all_contacts = [
        Contact(name="Alice", title="CEO", linkedin_url="https://linkedin.com/in/alice"),
        Contact(name="Bob", title="Software Engineer", linkedin_url="https://linkedin.com/in/bob"),
        Contact(name="Carol", title="Founder", linkedin_url="https://linkedin.com/in/carol"),
        Contact(name="Dave", title="Intern", linkedin_url="https://linkedin.com/in/dave"),
    ]

    with patch.object(enricher, 'scrape_people_page', new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = all_contacts

        contacts = await enricher.find_contacts(
            "Test Co", linkedin_url="https://linkedin.com/company/test-co"
        )

    names = [c.name for c in contacts]
    assert "Alice" in names
    assert "Carol" in names
    # Non-decision-makers should be filtered out when decision-makers exist
    assert "Bob" not in names
    assert "Dave" not in names


# ── Playwright integration tests ────────────────────────────────

def test_load_cookies_valid_file():
    """Valid cookie file should be loaded."""
    cookies = [
        {"name": "li_at", "value": "test123", "domain": ".linkedin.com", "path": "/"},
        {"name": "JSESSIONID", "value": "ajax:456", "domain": ".linkedin.com", "path": "/"},
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(cookies, f)
        f.flush()
        result = LinkedInEnricher._load_cookies(f.name)
    assert len(result) == 2
    assert result[0]["name"] == "li_at"


def test_load_cookies_missing_file():
    """Missing cookie file should return empty list."""
    result = LinkedInEnricher._load_cookies("/nonexistent/cookies.json")
    assert result == []


def test_load_cookies_invalid_json():
    """Invalid JSON should return empty list."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("not valid json{{{")
        f.flush()
        result = LinkedInEnricher._load_cookies(f.name)
    assert result == []


def test_load_cookies_filters_invalid_entries():
    """Entries missing required fields should be filtered out."""
    cookies = [
        {"name": "li_at", "value": "ok", "domain": ".linkedin.com"},  # valid
        {"name": "bad"},  # missing value and domain
        "not a dict",  # not a dict
    ]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(cookies, f)
        f.flush()
        result = LinkedInEnricher._load_cookies(f.name)
    assert len(result) == 1
    assert result[0]["name"] == "li_at"


@pytest.mark.asyncio
async def test_fetch_html_tries_playwright_first():
    """When browser context exists, Playwright should be tried before FlareSolverr."""
    enricher = LinkedInEnricher()
    enricher._browser_context = MagicMock()  # Simulate started browser

    with patch.object(enricher, '_fetch_via_playwright', new_callable=AsyncMock) as mock_pw, \
         patch.object(enricher, '_check_flaresolverr', new_callable=AsyncMock) as mock_fs_check, \
         patch.object(enricher, '_fetch_via_flaresolverr', new_callable=AsyncMock) as mock_fs:
        mock_pw.return_value = "<html>playwright content</html>"

        result = await enricher._fetch_html("https://linkedin.com/company/test", use_flaresolverr=True)

    assert result == "<html>playwright content</html>"
    mock_pw.assert_called_once()
    mock_fs_check.assert_not_called()  # Should not even check FlareSolverr
    mock_fs.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_html_falls_to_flaresolverr_when_playwright_fails():
    """When Playwright returns None, FlareSolverr should be tried."""
    enricher = LinkedInEnricher()
    enricher._browser_context = MagicMock()

    with patch.object(enricher, '_fetch_via_playwright', new_callable=AsyncMock) as mock_pw, \
         patch.object(enricher, '_check_flaresolverr', new_callable=AsyncMock) as mock_fs_check, \
         patch.object(enricher, '_fetch_via_flaresolverr', new_callable=AsyncMock) as mock_fs:
        mock_pw.return_value = None
        mock_fs_check.return_value = True
        mock_fs.return_value = "<html>flaresolverr content</html>"

        result = await enricher._fetch_html("https://linkedin.com/company/test", use_flaresolverr=True)

    assert result == "<html>flaresolverr content</html>"
    mock_pw.assert_called_once()
    mock_fs.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_html_skips_playwright_without_browser():
    """When no browser context, Playwright should be skipped entirely."""
    enricher = LinkedInEnricher()
    # _browser_context is None by default

    with patch.object(enricher, '_fetch_via_playwright', new_callable=AsyncMock) as mock_pw, \
         patch.object(enricher, '_check_flaresolverr', new_callable=AsyncMock) as mock_fs_check, \
         patch.object(enricher, '_fetch_via_flaresolverr', new_callable=AsyncMock) as mock_fs:
        mock_fs_check.return_value = True
        mock_fs.return_value = "<html>flaresolverr only</html>"

        result = await enricher._fetch_html("https://linkedin.com/company/test", use_flaresolverr=True)

    assert result == "<html>flaresolverr only</html>"
    mock_pw.assert_not_called()  # Playwright was never tried


@pytest.mark.asyncio
async def test_close_browser_safe_when_never_started():
    """close_browser should not raise when browser was never started."""
    enricher = LinkedInEnricher()
    await enricher.close_browser()  # Should not raise


@pytest.mark.asyncio
async def test_init_accepts_cookie_file():
    """Constructor should accept cookie_file parameter."""
    enricher = LinkedInEnricher(cookie_file="/tmp/test_cookies.json")
    assert enricher._cookie_file == "/tmp/test_cookies.json"
    assert enricher._browser is None
    assert enricher._browser_context is None
