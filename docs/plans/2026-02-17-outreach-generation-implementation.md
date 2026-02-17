# Outreach Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LLM-powered personalized outreach message generation to the lead detail CLI view, with caching, multi-provider support, and guided regeneration.

**Architecture:** New `llm_client.py` provides a unified LLM abstraction for OpenAI + Anthropic. New `outreach_generator.py` handles template parsing, message generation, and file caching in `data/outreach/`. The CLI integration adds a "Generate Outreach" option to the existing `_display_lead_details` function in `__main__.py`.

**Tech Stack:** Python 3.11+, openai SDK, anthropic SDK, Rich (panels/spinners), InquirerPy (menus)

---

### Task 1: Add Dependencies and Config

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `src/config.py`
- Create: `tests/test_outreach_config.py`

**Step 1: Update requirements.txt**

Add to `requirements.txt` after the `openai>=1.0.0` line:

```
anthropic>=0.40.0
```

**Step 2: Update .env.example**

Add after the Apollo section:

```
# Anthropic API (optional - for outreach generation with Claude)
ANTHROPIC_API_KEY=your_anthropic_api_key
```

**Step 3: Write failing test for OutreachSettings**

Create `tests/test_outreach_config.py`:

```python
# tests/test_outreach_config.py
import pytest
from unittest.mock import patch
from src.config import OutreachSettings


def test_outreach_settings_defaults():
    s = OutreachSettings()
    assert s.llm_provider == "openai"
    assert s.llm_model == "gpt-4o"
    assert s.default_template == ""


def test_outreach_settings_custom():
    s = OutreachSettings(llm_provider="anthropic", llm_model="claude-sonnet-4-5-20250929")
    assert s.llm_provider == "anthropic"
    assert s.llm_model == "claude-sonnet-4-5-20250929"
```

**Step 4: Run test to verify it fails**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_config.py -v`

Expected: FAIL with `ImportError: cannot import name 'OutreachSettings'`

**Step 5: Add OutreachSettings to config.py**

In `src/config.py`, add after the `EmailVerificationSettings` class (after line 32):

```python
@dataclass
class OutreachSettings:
    """Settings for outreach message generation."""
    llm_provider: str = "openai"       # "openai" or "anthropic"
    llm_model: str = "gpt-4o"          # model name
    default_template: str = ""         # default template filename
```

Add `anthropic_api_key` field to the `Settings` class (after `apollo_api_key` on line 40):

```python
    anthropic_api_key: str = ""
```

Add `outreach` field to the `Settings` class (after `email_verification` on line 50):

```python
    outreach: OutreachSettings = field(default_factory=OutreachSettings)
```

In `Settings.__post_init__`, add after `self.apollo_api_key` line (after line 56):

```python
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
```

And after the email verification settings loading (after line 95):

```python
        # Load outreach settings
        outreach_config = config.get("outreach", {})
        self.outreach = OutreachSettings(
            llm_provider=outreach_config.get("llm_provider", "openai"),
            llm_model=outreach_config.get("llm_model", "gpt-4o"),
            default_template=outreach_config.get("default_template", ""),
        )
```

**Step 6: Run test to verify it passes**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_config.py -v`

Expected: PASS (2 tests)

**Step 7: Install anthropic**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && pip install anthropic>=0.40.0`

**Step 8: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add requirements.txt .env.example src/config.py tests/test_outreach_config.py
git commit -m "feat: add OutreachSettings config and Anthropic API key support"
```

---

### Task 2: LLM Client Module

**Files:**
- Create: `src/llm_client.py`
- Create: `tests/test_llm_client.py`

**Step 1: Write failing tests for LLMClient**

Create `tests/test_llm_client.py`:

```python
# tests/test_llm_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.llm_client import LLMClient


def test_init_openai_provider():
    client = LLMClient(provider="openai", model="gpt-4o", api_key="test-key")
    assert client.provider == "openai"
    assert client.model == "gpt-4o"


def test_init_anthropic_provider():
    client = LLMClient(provider="anthropic", model="claude-sonnet-4-5-20250929", api_key="test-key")
    assert client.provider == "anthropic"
    assert client.model == "claude-sonnet-4-5-20250929"


def test_init_invalid_provider():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMClient(provider="gemini", model="gemini-pro", api_key="test-key")


def test_init_missing_api_key():
    with pytest.raises(ValueError, match="API key required"):
        LLMClient(provider="openai", model="gpt-4o", api_key="")


@patch("src.llm_client.OpenAI")
def test_generate_openai(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Generated text"))]
    )

    client = LLMClient(provider="openai", model="gpt-4o", api_key="test-key")
    result = client.generate(system_prompt="You are helpful", user_prompt="Write something")

    assert result == "Generated text"
    mock_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Write something"},
        ],
    )


@patch("src.llm_client.Anthropic")
def test_generate_anthropic(mock_anthropic_class):
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Generated text")]
    )

    client = LLMClient(provider="anthropic", model="claude-sonnet-4-5-20250929", api_key="test-key")
    result = client.generate(system_prompt="You are helpful", user_prompt="Write something")

    assert result == "Generated text"
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system="You are helpful",
        messages=[{"role": "user", "content": "Write something"}],
    )


@patch("src.llm_client.OpenAI")
def test_generate_from_settings(mock_openai_class):
    """Test the from_settings factory method."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Hello"))]
    )

    with patch("src.llm_client.settings") as mock_settings:
        mock_settings.outreach.llm_provider = "openai"
        mock_settings.outreach.llm_model = "gpt-4o"
        mock_settings.openai_api_key = "test-key"
        mock_settings.anthropic_api_key = ""

        client = LLMClient.from_settings()
        assert client.provider == "openai"
        assert client.model == "gpt-4o"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_llm_client.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm_client'`

**Step 3: Implement LLMClient**

Create `src/llm_client.py`:

```python
# src/llm_client.py
"""Unified LLM client supporting OpenAI and Anthropic."""
from __future__ import annotations

from openai import OpenAI
from anthropic import Anthropic

from src.config import settings


class LLMClient:
    """Unified interface for LLM text generation."""

    SUPPORTED_PROVIDERS = ("openai", "anthropic")

    def __init__(self, provider: str, model: str, api_key: str):
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported LLM provider: {provider}. Use one of {self.SUPPORTED_PROVIDERS}")
        if not api_key:
            raise ValueError("API key required for LLM provider")

        self.provider = provider
        self.model = model
        self._api_key = api_key

    @classmethod
    def from_settings(cls) -> "LLMClient":
        """Create an LLMClient from application settings."""
        provider = settings.outreach.llm_provider
        model = settings.outreach.llm_model

        if provider == "openai":
            api_key = settings.openai_api_key
        elif provider == "anthropic":
            api_key = settings.anthropic_api_key
        else:
            api_key = ""

        return cls(provider=provider, model=model, api_key=api_key)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text using the configured LLM provider."""
        if self.provider == "openai":
            return self._generate_openai(system_prompt, user_prompt)
        elif self.provider == "anthropic":
            return self._generate_anthropic(system_prompt, user_prompt)

    def _generate_openai(self, system_prompt: str, user_prompt: str) -> str:
        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    def _generate_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        client = Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_llm_client.py -v`

Expected: PASS (7 tests)

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/llm_client.py tests/test_llm_client.py
git commit -m "feat: add LLMClient with OpenAI and Anthropic support"
```

---

### Task 3: Outreach Generator — Template Parsing & Lead Data Formatting

**Files:**
- Create: `src/outreach_generator.py`
- Create: `tests/test_outreach_generator.py`

**Step 1: Write failing tests for template discovery and lead formatting**

Create `tests/test_outreach_generator.py`:

```python
# tests/test_outreach_generator.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.outreach_generator import OutreachGenerator


@pytest.fixture
def sample_template(tmp_path):
    """Create a sample template file."""
    template = tmp_path / "test-template.md"
    template.write_text("""# Outreach Templates — Test Campaign

Campaign for testing.

**Positioning:** Test positioning
**Tone:** Professional
**CTA:** Book a call

## CSV Field Mapping

| Placeholder | CSV Field |
|-------------|-----------|
| `{brand_name}` | `brand_name` |
| `{contact_name}` | `contact_1_name` |

---

## Cold Email

**Subject:** Testing {brand_name}

Hey {contact_name}, this is a test email for {brand_name}.

---

## LinkedIn Connection Request

Hi {contact_name} — test connection request for {brand_name}.

---

## LinkedIn Follow-Up

Thanks for connecting, {contact_name}. Test follow-up for {brand_name}.

---

## Follow-Up Email

**Subject:** Re: Testing {brand_name}

Hey {contact_name}, just following up about {brand_name}.
""")
    return template


@pytest.fixture
def sample_lead_row():
    """Simulates a pandas DataFrame row as a dict-like object."""
    import pandas as pd
    data = {
        "brand_name": "Portland Running Company",
        "website": "https://portlandrunning.com",
        "location_count": 5,
        "cities": "Portland, Seattle, Denver",
        "contact_1_name": "John Smith",
        "contact_1_title": "CEO",
        "contact_1_email": "john@portlandrunning.com",
        "contact_1_linkedin": "https://linkedin.com/in/johnsmith",
        "contact_2_name": "Jane Doe",
        "contact_2_title": "COO",
        "contact_2_email": "jane@portlandrunning.com",
        "ecommerce_platform": "shopify",
        "has_ecommerce": True,
        "detected_marketplaces": "amazon",
        "industry": "Retail",
        "employee_count": 50,
        "linkedin_company": "https://linkedin.com/company/portland-running",
    }
    return pd.Series(data)


def test_discover_templates(tmp_path):
    """Templates are auto-discovered from a directory."""
    (tmp_path / "campaign-a.md").write_text("# Template A\n## Cold Email\nTest")
    (tmp_path / "campaign-b.md").write_text("# Template B\n## Cold Email\nTest")
    (tmp_path / "not-a-template.txt").write_text("ignore me")

    gen = OutreachGenerator(templates_dir=tmp_path)
    templates = gen.list_templates()

    assert len(templates) == 2
    names = [t["name"] for t in templates]
    assert "campaign-a" in names
    assert "campaign-b" in names


def test_discover_templates_empty_dir(tmp_path):
    gen = OutreachGenerator(templates_dir=tmp_path)
    assert gen.list_templates() == []


def test_format_lead_data(sample_lead_row):
    gen = OutreachGenerator()
    formatted = gen._format_lead_data(sample_lead_row, contact_index=1)

    assert "Portland Running Company" in formatted
    assert "portlandrunning.com" in formatted
    assert "5" in formatted
    assert "John Smith" in formatted
    assert "CEO" in formatted
    assert "shopify" in formatted
    assert "amazon" in formatted


def test_format_lead_data_second_contact(sample_lead_row):
    gen = OutreachGenerator()
    formatted = gen._format_lead_data(sample_lead_row, contact_index=2)

    assert "Jane Doe" in formatted
    assert "COO" in formatted


def test_read_template(sample_template):
    gen = OutreachGenerator(templates_dir=sample_template.parent)
    content = gen._read_template("test-template")

    assert "Test Campaign" in content
    assert "Cold Email" in content
    assert "{brand_name}" in content


def test_read_template_not_found(tmp_path):
    gen = OutreachGenerator(templates_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        gen._read_template("nonexistent")
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.outreach_generator'`

**Step 3: Implement template parsing and lead formatting**

Create `src/outreach_generator.py`:

```python
# src/outreach_generator.py
"""LLM-powered outreach message generation with caching."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import settings
from src.llm_client import LLMClient


# Message types and their file suffixes
MESSAGE_TYPES = {
    "cold_email": "Cold Email",
    "linkedin_request": "LinkedIn Connection Request",
    "linkedin_followup": "LinkedIn Follow-Up",
    "follow_up_email": "Follow-Up Email",
}

OUTREACH_DIR = Path("data/outreach")

SYSTEM_PROMPT_TEMPLATE = (
    "You are an expert B2B outreach copywriter. You write personalized sales messages "
    "that feel like they were written by someone who genuinely researched the recipient's "
    "business. You follow the provided template's structure, tone, and positioning but "
    "deeply personalize using the lead's specific data. Keep messages concise and natural "
    "— never use filler or generic phrases."
)

SYSTEM_PROMPT_FREEFORM = (
    "You are an expert B2B outreach copywriter. You write personalized sales messages "
    "for a consulting company that helps multi-location retailers automate their operations. "
    "Write concise, natural messages that feel researched and personal. "
    "Never use filler or generic phrases. Be direct and value-focused."
)


def _slugify(name: str) -> str:
    """Convert brand name to a filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


class OutreachGenerator:
    """Generates personalized outreach messages using LLMs."""

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        outreach_dir: Optional[Path] = None,
    ):
        self.templates_dir = templates_dir or Path("templates")
        self.outreach_dir = outreach_dir or OUTREACH_DIR

    def list_templates(self) -> list[dict]:
        """Discover available templates from the templates directory."""
        if not self.templates_dir.exists():
            return []

        templates = []
        for f in sorted(self.templates_dir.glob("*.md")):
            # Read first line to get title
            first_line = f.read_text().split("\n")[0].strip("# ").strip()
            templates.append({
                "name": f.stem,
                "title": first_line,
                "path": f,
            })
        return templates

    def _read_template(self, template_name: str) -> str:
        """Read a template file by name (without extension)."""
        path = self.templates_dir / f"{template_name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")
        return path.read_text()

    def _format_lead_data(self, lead_row: pd.Series, contact_index: int = 1) -> str:
        """Format lead data into a structured string for the LLM prompt."""
        lines = []
        lines.append(f"- Brand: {lead_row.get('brand_name', 'Unknown')}")
        lines.append(f"- Website: {lead_row.get('website', 'N/A')}")
        lines.append(f"- Locations: {lead_row.get('location_count', 'N/A')}")

        cities = lead_row.get("cities")
        if pd.notna(cities):
            lines.append(f"- Cities: {cities}")

        # Contact info
        name = lead_row.get(f"contact_{contact_index}_name")
        if pd.notna(name):
            lines.append(f"- Contact name: {name}")

        title = lead_row.get(f"contact_{contact_index}_title")
        if pd.notna(title):
            lines.append(f"- Contact title: {title}")

        email = lead_row.get(f"contact_{contact_index}_email")
        if pd.notna(email):
            lines.append(f"- Contact email: {email}")

        linkedin = lead_row.get(f"contact_{contact_index}_linkedin")
        if pd.notna(linkedin):
            lines.append(f"- Contact LinkedIn: {linkedin}")

        # Company details
        platform = lead_row.get("ecommerce_platform")
        if pd.notna(platform):
            lines.append(f"- E-commerce platform: {platform}")

        marketplaces = lead_row.get("detected_marketplaces")
        if pd.notna(marketplaces):
            lines.append(f"- Marketplaces: {marketplaces}")

        industry = lead_row.get("industry")
        if pd.notna(industry):
            lines.append(f"- Industry: {industry}")

        employees = lead_row.get("employee_count")
        if pd.notna(employees):
            lines.append(f"- Employee count: {employees}")

        company_linkedin = lead_row.get("linkedin_company")
        if pd.notna(company_linkedin):
            lines.append(f"- Company LinkedIn: {company_linkedin}")

        return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py -v`

Expected: PASS (6 tests)

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/outreach_generator.py tests/test_outreach_generator.py
git commit -m "feat: add OutreachGenerator with template discovery and lead formatting"
```

---

### Task 4: Outreach Generator — Message Generation

**Files:**
- Modify: `src/outreach_generator.py`
- Modify: `tests/test_outreach_generator.py`

**Step 1: Write failing tests for message generation**

Add to `tests/test_outreach_generator.py`:

```python
def test_parse_generated_response():
    """Parser extracts individual messages from LLM's combined response."""
    gen = OutreachGenerator()
    response = """## Cold Email

**Subject:** Test subject

Hey John, this is the cold email body.

## LinkedIn Connection Request

Hi John — this is the connection request.

## LinkedIn Follow-Up

Thanks for connecting, John. This is the follow-up.

## Follow-Up Email

**Subject:** Re: Test subject

Hey John, just following up.
"""
    messages = gen._parse_response(response)

    assert "cold_email" in messages
    assert "linkedin_request" in messages
    assert "linkedin_followup" in messages
    assert "follow_up_email" in messages
    assert "cold email body" in messages["cold_email"]
    assert "connection request" in messages["linkedin_request"]


@patch("src.outreach_generator.LLMClient")
def test_generate_template_mode(mock_llm_class, sample_lead_row, sample_template):
    """Template-guided generation sends template + lead data to LLM."""
    mock_client = MagicMock()
    mock_llm_class.from_settings.return_value = mock_client
    mock_client.generate.return_value = """## Cold Email

**Subject:** Test

Generated cold email.

## LinkedIn Connection Request

Generated connection request.

## LinkedIn Follow-Up

Generated follow-up.

## Follow-Up Email

**Subject:** Re: Test

Generated follow-up email.
"""

    gen = OutreachGenerator(templates_dir=sample_template.parent)
    messages = gen.generate(sample_lead_row, template_name="test-template")

    assert len(messages) == 4
    assert "Generated cold email" in messages["cold_email"]

    # Verify LLM was called with template content in the prompt
    call_args = mock_client.generate.call_args
    assert "Test Campaign" in call_args.kwargs.get("user_prompt", call_args[1] if len(call_args) > 1 else call_args[0][1])


@patch("src.outreach_generator.LLMClient")
def test_generate_freeform_mode(mock_llm_class, sample_lead_row):
    """Free-form generation sends only lead data with freeform system prompt."""
    mock_client = MagicMock()
    mock_llm_class.from_settings.return_value = mock_client
    mock_client.generate.return_value = """## Cold Email

**Subject:** Test

Free-form cold email.

## LinkedIn Connection Request

Free-form request.

## LinkedIn Follow-Up

Free-form follow-up.

## Follow-Up Email

**Subject:** Re: Test

Free-form follow-up email.
"""

    gen = OutreachGenerator()
    messages = gen.generate(sample_lead_row, template_name=None)

    assert len(messages) == 4
    assert "Free-form cold email" in messages["cold_email"]

    # Verify freeform system prompt was used
    call_args = mock_client.generate.call_args
    system = call_args.kwargs.get("system_prompt", call_args[0][0])
    assert "consulting company" in system.lower() or "outreach" in system.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py::test_parse_generated_response tests/test_outreach_generator.py::test_generate_template_mode tests/test_outreach_generator.py::test_generate_freeform_mode -v`

Expected: FAIL with `AttributeError: 'OutreachGenerator' object has no attribute '_parse_response'`

**Step 3: Implement generation methods**

Add to `src/outreach_generator.py` inside the `OutreachGenerator` class:

```python
    def _parse_response(self, response: str) -> dict[str, str]:
        """Parse LLM response into individual messages by heading."""
        messages = {}

        # Map heading text to message type keys
        heading_map = {
            "cold email": "cold_email",
            "linkedin connection request": "linkedin_request",
            "linkedin follow-up": "linkedin_followup",
            "linkedin follow up": "linkedin_followup",
            "follow-up email": "follow_up_email",
            "follow up email": "follow_up_email",
        }

        # Split by ## headings
        sections = re.split(r"^## ", response, flags=re.MULTILINE)

        for section in sections:
            if not section.strip():
                continue

            # First line is the heading
            lines = section.split("\n", 1)
            heading = lines[0].strip().lower()
            body = lines[1].strip() if len(lines) > 1 else ""

            for pattern, key in heading_map.items():
                if pattern in heading:
                    messages[key] = body
                    break

        return messages

    def _build_user_prompt(
        self,
        lead_row: pd.Series,
        contact_index: int,
        template_content: Optional[str] = None,
    ) -> str:
        """Build the user prompt for the LLM."""
        lead_data = self._format_lead_data(lead_row, contact_index)

        parts = []
        if template_content:
            parts.append("Here is the template to follow as a style guide:")
            parts.append(template_content)
            parts.append("")

        parts.append("Here is the lead data:")
        parts.append(lead_data)
        parts.append("")
        parts.append(
            "Generate personalized versions of all 4 message types. "
            "Output each under a markdown heading: "
            "## Cold Email, ## LinkedIn Connection Request, "
            "## LinkedIn Follow-Up, ## Follow-Up Email."
        )

        return "\n".join(parts)

    def generate(
        self,
        lead_row: pd.Series,
        template_name: Optional[str] = None,
        contact_index: int = 1,
    ) -> dict[str, str]:
        """Generate all 4 outreach messages for a lead.

        Args:
            lead_row: A pandas Series with lead data.
            template_name: Template name (without .md) for guided mode, or None for free-form.
            contact_index: Which contact to personalize for (1-4).

        Returns:
            Dict mapping message type keys to generated text.
        """
        template_content = None
        if template_name:
            template_content = self._read_template(template_name)

        system_prompt = SYSTEM_PROMPT_TEMPLATE if template_content else SYSTEM_PROMPT_FREEFORM
        user_prompt = self._build_user_prompt(lead_row, contact_index, template_content)

        client = LLMClient.from_settings()
        response = client.generate(system_prompt=system_prompt, user_prompt=user_prompt)

        return self._parse_response(response)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py -v`

Expected: PASS (9 tests)

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/outreach_generator.py tests/test_outreach_generator.py
git commit -m "feat: add outreach message generation with template and free-form modes"
```

---

### Task 5: Outreach Generator — File Caching

**Files:**
- Modify: `src/outreach_generator.py`
- Modify: `tests/test_outreach_generator.py`

**Step 1: Write failing tests for caching**

Add to `tests/test_outreach_generator.py`:

```python
def test_slugify():
    from src.outreach_generator import _slugify
    assert _slugify("Portland Running Company") == "portland-running-company"
    assert _slugify("Nike's Store #5") == "nike-s-store-5"
    assert _slugify("  Spaces  ") == "spaces"


def test_save_and_load_cached(tmp_path, sample_lead_row):
    """Generated messages are saved to files and can be loaded back."""
    gen = OutreachGenerator(outreach_dir=tmp_path)

    messages = {
        "cold_email": "Test cold email body",
        "linkedin_request": "Test connection request",
        "linkedin_followup": "Test follow-up message",
        "follow_up_email": "Test follow-up email",
    }

    gen.save_outreach(
        brand_name="Portland Running Company",
        messages=messages,
        template_name="test-template",
        contact_name="John Smith",
        model="gpt-4o",
    )

    # Verify files exist
    slug = "portland-running-company"
    assert (tmp_path / f"{slug}_cold_email.md").exists()
    assert (tmp_path / f"{slug}_linkedin_request.md").exists()
    assert (tmp_path / f"{slug}_linkedin_followup.md").exists()
    assert (tmp_path / f"{slug}_follow_up_email.md").exists()

    # Load them back
    loaded = gen.load_cached_outreach("Portland Running Company")
    assert loaded is not None
    assert len(loaded) == 4
    assert "Test cold email body" in loaded["cold_email"]


def test_load_cached_nonexistent(tmp_path):
    """Loading non-existent outreach returns None."""
    gen = OutreachGenerator(outreach_dir=tmp_path)
    result = gen.load_cached_outreach("Nonexistent Brand")
    assert result is None


def test_save_creates_directory(tmp_path):
    """Save creates the outreach directory if it doesn't exist."""
    outreach_dir = tmp_path / "nested" / "outreach"
    gen = OutreachGenerator(outreach_dir=outreach_dir)

    messages = {
        "cold_email": "Test",
        "linkedin_request": "Test",
        "linkedin_followup": "Test",
        "follow_up_email": "Test",
    }

    gen.save_outreach("Test Brand", messages, "template", "Contact", "gpt-4o")
    assert outreach_dir.exists()


def test_saved_file_has_metadata_header(tmp_path):
    """Saved files include YAML-like metadata header."""
    gen = OutreachGenerator(outreach_dir=tmp_path)

    messages = {"cold_email": "Email body here"}
    gen.save_outreach("Test Brand", messages, "my-template", "John", "gpt-4o")

    content = (tmp_path / "test-brand_cold_email.md").read_text()
    assert "brand: Test Brand" in content
    assert "template: my-template" in content
    assert "contact: John" in content
    assert "model: gpt-4o" in content
    assert "Email body here" in content
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py::test_slugify tests/test_outreach_generator.py::test_save_and_load_cached tests/test_outreach_generator.py::test_load_cached_nonexistent tests/test_outreach_generator.py::test_save_creates_directory tests/test_outreach_generator.py::test_saved_file_has_metadata_header -v`

Expected: FAIL with `AttributeError: 'OutreachGenerator' object has no attribute 'save_outreach'`

**Step 3: Implement caching methods**

Add to `src/outreach_generator.py` inside the `OutreachGenerator` class:

```python
    def save_outreach(
        self,
        brand_name: str,
        messages: dict[str, str],
        template_name: str,
        contact_name: str,
        model: str,
        instructions: Optional[str] = None,
    ) -> None:
        """Save generated messages to individual files with metadata."""
        self.outreach_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(brand_name)
        now = datetime.now().isoformat(timespec="seconds")

        for msg_type, content in messages.items():
            header = (
                f"---\n"
                f"brand: {brand_name}\n"
                f"template: {template_name}\n"
                f"contact: {contact_name}\n"
                f"generated_at: {now}\n"
                f"model: {model}\n"
                f"instructions: {instructions or 'null'}\n"
                f"---\n\n"
            )
            file_path = self.outreach_dir / f"{slug}_{msg_type}.md"
            file_path.write_text(header + content)

    def load_cached_outreach(self, brand_name: str) -> Optional[dict[str, str]]:
        """Load previously generated outreach messages for a brand.

        Returns None if no cached messages exist.
        """
        slug = _slugify(brand_name)
        messages = {}

        for msg_type in MESSAGE_TYPES:
            file_path = self.outreach_dir / f"{slug}_{msg_type}.md"
            if not file_path.exists():
                continue

            raw = file_path.read_text()

            # Strip metadata header
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
                else:
                    content = raw
            else:
                content = raw

            messages[msg_type] = content

        return messages if messages else None

    def has_cached_outreach(self, brand_name: str) -> bool:
        """Check if cached outreach exists for a brand."""
        slug = _slugify(brand_name)
        return any(
            (self.outreach_dir / f"{slug}_{msg_type}.md").exists()
            for msg_type in MESSAGE_TYPES
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py -v`

Expected: PASS (14 tests)

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/outreach_generator.py tests/test_outreach_generator.py
git commit -m "feat: add outreach message caching to data/outreach/"
```

---

### Task 6: Outreach Generator — Regeneration

**Files:**
- Modify: `src/outreach_generator.py`
- Modify: `tests/test_outreach_generator.py`

**Step 1: Write failing tests for regeneration**

Add to `tests/test_outreach_generator.py`:

```python
@patch("src.outreach_generator.LLMClient")
def test_regenerate_all(mock_llm_class, sample_lead_row, tmp_path):
    """Regenerate all messages overwrites cached files."""
    mock_client = MagicMock()
    mock_llm_class.from_settings.return_value = mock_client
    mock_client.generate.return_value = """## Cold Email

Regenerated cold email.

## LinkedIn Connection Request

Regenerated request.

## LinkedIn Follow-Up

Regenerated follow-up.

## Follow-Up Email

Regenerated follow-up email.
"""

    gen = OutreachGenerator(outreach_dir=tmp_path)

    # Save initial messages
    initial = {
        "cold_email": "Old email",
        "linkedin_request": "Old request",
        "linkedin_followup": "Old follow-up",
        "follow_up_email": "Old follow-up email",
    }
    gen.save_outreach("Portland Running Company", initial, "test", "John", "gpt-4o")

    # Regenerate
    messages = gen.regenerate(sample_lead_row, template_name="test")
    assert "Regenerated cold email" in messages["cold_email"]


@patch("src.outreach_generator.LLMClient")
def test_regenerate_single_message(mock_llm_class, sample_lead_row, tmp_path):
    """Regenerate a single message type."""
    mock_client = MagicMock()
    mock_llm_class.from_settings.return_value = mock_client
    mock_client.generate.return_value = "New version of cold email."

    gen = OutreachGenerator(outreach_dir=tmp_path)

    # Save initial
    initial = {
        "cold_email": "Old email",
        "linkedin_request": "Keep this",
        "linkedin_followup": "Keep this too",
        "follow_up_email": "And this",
    }
    gen.save_outreach("Portland Running Company", initial, "test", "John", "gpt-4o")

    # Regenerate only cold_email
    messages = gen.regenerate_single(
        sample_lead_row,
        message_type="cold_email",
        instructions="Make it shorter",
    )

    assert "New version" in messages["cold_email"]
    # Other messages should be unchanged
    assert "Keep this" in messages["linkedin_request"]


@patch("src.outreach_generator.LLMClient")
def test_regenerate_with_instructions(mock_llm_class, sample_lead_row, tmp_path):
    """Regeneration passes user instructions to the LLM."""
    mock_client = MagicMock()
    mock_llm_class.from_settings.return_value = mock_client
    mock_client.generate.return_value = """## Cold Email

Shorter email.

## LinkedIn Connection Request

Shorter request.

## LinkedIn Follow-Up

Shorter follow-up.

## Follow-Up Email

Shorter follow-up email.
"""

    gen = OutreachGenerator(outreach_dir=tmp_path)
    messages = gen.regenerate(
        sample_lead_row,
        template_name=None,
        instructions="Make everything shorter and more casual",
    )

    # Verify instructions were passed to LLM
    call_args = mock_client.generate.call_args
    user_prompt = call_args.kwargs.get("user_prompt", call_args[0][1])
    assert "shorter" in user_prompt.lower()
    assert "casual" in user_prompt.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py::test_regenerate_all tests/test_outreach_generator.py::test_regenerate_single_message tests/test_outreach_generator.py::test_regenerate_with_instructions -v`

Expected: FAIL with `AttributeError: 'OutreachGenerator' object has no attribute 'regenerate'`

**Step 3: Implement regeneration methods**

Add to `src/outreach_generator.py` inside the `OutreachGenerator` class:

```python
    def regenerate(
        self,
        lead_row: pd.Series,
        template_name: Optional[str] = None,
        contact_index: int = 1,
        instructions: Optional[str] = None,
    ) -> dict[str, str]:
        """Regenerate all outreach messages, optionally with user instructions.

        Args:
            lead_row: Lead data.
            template_name: Template name for guided mode, None for free-form.
            contact_index: Which contact to use.
            instructions: Optional user instructions (e.g. "make it shorter").

        Returns:
            Dict of regenerated messages.
        """
        template_content = None
        if template_name:
            try:
                template_content = self._read_template(template_name)
            except FileNotFoundError:
                pass

        system_prompt = SYSTEM_PROMPT_TEMPLATE if template_content else SYSTEM_PROMPT_FREEFORM
        user_prompt = self._build_user_prompt(lead_row, contact_index, template_content)

        if instructions:
            user_prompt += f"\n\nAdditional instructions: {instructions}"

        client = LLMClient.from_settings()
        response = client.generate(system_prompt=system_prompt, user_prompt=user_prompt)

        messages = self._parse_response(response)

        # Save regenerated messages
        brand_name = str(lead_row.get("brand_name", "unknown"))
        contact_name = str(lead_row.get(f"contact_{contact_index}_name", "Unknown"))
        model = settings.outreach.llm_model
        self.save_outreach(brand_name, messages, template_name or "free-form", contact_name, model, instructions)

        return messages

    def regenerate_single(
        self,
        lead_row: pd.Series,
        message_type: str,
        instructions: Optional[str] = None,
        contact_index: int = 1,
    ) -> dict[str, str]:
        """Regenerate a single message type.

        Args:
            lead_row: Lead data.
            message_type: One of the MESSAGE_TYPES keys.
            instructions: Optional user instructions.
            contact_index: Which contact to use.

        Returns:
            Dict of all messages (with the specified one regenerated).
        """
        brand_name = str(lead_row.get("brand_name", "unknown"))

        # Load existing messages
        existing = self.load_cached_outreach(brand_name) or {}

        # Build prompt for single message
        lead_data = self._format_lead_data(lead_row, contact_index)
        heading = MESSAGE_TYPES.get(message_type, message_type)

        system_prompt = SYSTEM_PROMPT_FREEFORM
        user_prompt = f"Here is the lead data:\n{lead_data}\n\n"

        if message_type in existing:
            user_prompt += f"Here is the previous {heading}:\n{existing[message_type]}\n\n"

        if instructions:
            user_prompt += f"User feedback: {instructions}\n\n"

        user_prompt += f"Regenerate the {heading}. Output only the message text, no heading."

        client = LLMClient.from_settings()
        response = client.generate(system_prompt=system_prompt, user_prompt=user_prompt)

        # Update the single message
        existing[message_type] = response.strip()

        # Save all messages
        contact_name = str(lead_row.get(f"contact_{contact_index}_name", "Unknown"))
        model = settings.outreach.llm_model
        self.save_outreach(brand_name, existing, "regenerated", contact_name, model, instructions)

        return existing
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/test_outreach_generator.py -v`

Expected: PASS (17 tests)

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/outreach_generator.py tests/test_outreach_generator.py
git commit -m "feat: add outreach regeneration with custom instructions"
```

---

### Task 7: CLI Integration — Generate Outreach from Lead Detail

**Files:**
- Modify: `src/__main__.py`

**Step 1: Add the outreach option to `_display_lead_details`**

In `src/__main__.py`, add this import at the top (after the existing imports around line 16):

```python
from src.outreach_generator import OutreachGenerator, MESSAGE_TYPES
```

**Step 2: Add "Generate Outreach" to the navigation choices in `_display_lead_details`**

In the `_display_lead_details` function, find the navigation choices section (around line 911-919). Replace the nav_choices building with:

```python
        # Navigation options
        nav_choices = []

        # Outreach generation option
        brand_name = str(row.get("brand_name", "Unknown"))
        outreach_gen = OutreachGenerator()
        has_outreach = outreach_gen.has_cached_outreach(brand_name)

        if has_outreach:
            nav_choices.append({"name": "✉️  View outreach messages", "value": "outreach"})
        else:
            nav_choices.append({"name": "✉️  Generate outreach", "value": "outreach"})

        if current_idx > 0:
            nav_choices.append({"name": "⬅️  Previous lead", "value": "prev"})

        if current_idx < total_leads - 1:
            nav_choices.append({"name": "➡️  Next lead", "value": "next"})

        nav_choices.append({"name": "🔢 Jump to lead #", "value": "jump"})
        nav_choices.append({"name": "← Back to list", "value": "back"})
```

**Step 3: Add the outreach action handler**

In the same function, in the action handling block (after the "back" handler around line 928), add the outreach handler before the existing elif chain:

```python
        if action == "back":
            return current_idx
        elif action == "outreach":
            _outreach_flow(row)
```

**Step 4: Implement the `_outreach_flow` function**

Add this new function to `src/__main__.py` (before `_interactive_stats`):

```python
def _outreach_flow(lead_row):
    """Outreach generation and viewing flow for a single lead."""
    import pandas as pd

    brand_name = str(lead_row.get("brand_name", "Unknown"))
    gen = OutreachGenerator()

    # Check for cached messages
    cached = gen.load_cached_outreach(brand_name)

    if cached:
        # Show existing messages
        _display_outreach_messages(cached, brand_name)

        action = inquirer.select(
            message="What would you like to do?",
            choices=[
                {"name": "🔄 Regenerate all messages", "value": "regen_all"},
                {"name": "✏️  Regenerate with instructions", "value": "regen_guided"},
                {"name": "🎯 Regenerate specific message", "value": "regen_single"},
                Separator(),
                {"name": "← Back to lead", "value": "back"},
            ],
        ).execute()

        if action == "back":
            return

        if action == "regen_all":
            _do_generate(gen, lead_row, brand_name)

        elif action == "regen_guided":
            instructions = inquirer.text(
                message="Enter instructions (e.g. 'make it shorter', 'more casual tone'):",
            ).execute()
            if instructions.strip():
                _do_generate(gen, lead_row, brand_name, instructions=instructions)

        elif action == "regen_single":
            msg_type = inquirer.select(
                message="Which message to regenerate?",
                choices=[
                    {"name": heading, "value": key}
                    for key, heading in MESSAGE_TYPES.items()
                ],
            ).execute()

            instructions = inquirer.text(
                message="Instructions (optional, press Enter to skip):",
                default="",
            ).execute()

            with console.status(f"[bold cyan]Regenerating {MESSAGE_TYPES[msg_type]}..."):
                try:
                    messages = gen.regenerate_single(
                        lead_row,
                        message_type=msg_type,
                        instructions=instructions if instructions.strip() else None,
                    )
                    console.print(f"[green]✓ Regenerated {MESSAGE_TYPES[msg_type]}[/green]\n")
                    _display_outreach_messages(messages, brand_name)
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
    else:
        # No cached messages — generate new ones
        _do_generate(gen, lead_row, brand_name)


def _do_generate(gen: OutreachGenerator, lead_row, brand_name: str, instructions: str = None):
    """Run the generation flow: pick mode, template, contact, generate."""
    import pandas as pd

    # Pick mode
    mode = inquirer.select(
        message="Generation mode:",
        choices=[
            {"name": "📝 Template-guided (follows your template's style)", "value": "template"},
            {"name": "✨ Free-form (original copy from lead data)", "value": "freeform"},
        ],
    ).execute()

    template_name = None
    if mode == "template":
        templates = gen.list_templates()
        if not templates:
            console.print("[yellow]No templates found in templates/ directory. Using free-form mode.[/yellow]")
        else:
            template_choices = [
                {"name": f"{t['name']} — {t['title']}", "value": t["name"]}
                for t in templates
            ]
            template_name = inquirer.select(
                message="Select template:",
                choices=template_choices,
            ).execute()

    # Pick contact if multiple
    contact_index = 1
    contacts = []
    for i in range(1, 5):
        name = lead_row.get(f"contact_{i}_name")
        if pd.notna(name) and str(name).strip():
            title = lead_row.get(f"contact_{i}_title", "")
            title_str = f" ({title})" if pd.notna(title) and str(title).strip() else ""
            contacts.append({"name": f"{name}{title_str}", "value": i})

    if len(contacts) > 1:
        contact_index = inquirer.select(
            message="Generate for which contact?",
            choices=contacts,
        ).execute()
    elif len(contacts) == 0:
        console.print("[yellow]No contacts found for this lead. Using placeholder.[/yellow]")

    # Generate
    with console.status("[bold cyan]Generating outreach messages..."):
        try:
            if instructions:
                messages = gen.regenerate(
                    lead_row,
                    template_name=template_name,
                    contact_index=contact_index,
                    instructions=instructions,
                )
            else:
                messages = gen.generate(
                    lead_row,
                    template_name=template_name,
                    contact_index=contact_index,
                )

                # Save to cache
                contact_name = str(lead_row.get(f"contact_{contact_index}_name", "Unknown"))
                from src.config import settings
                gen.save_outreach(
                    brand_name,
                    messages,
                    template_name or "free-form",
                    contact_name,
                    settings.outreach.llm_model,
                )

            console.print("[green]✓ Messages generated and saved[/green]\n")
            _display_outreach_messages(messages, brand_name)

        except Exception as e:
            console.print(f"[red]Error generating outreach: {e}[/red]")
            console.print("[dim]Check your API key and LLM provider settings.[/dim]")


def _display_outreach_messages(messages: dict[str, str], brand_name: str):
    """Display outreach messages in Rich panels."""
    console.print()
    for msg_type, heading in MESSAGE_TYPES.items():
        content = messages.get(msg_type)
        if content:
            console.print(Panel(
                content,
                title=f"[bold]{heading}[/bold]",
                subtitle=brand_name,
                border_style="cyan",
                padding=(1, 2),
            ))
            console.print()
```

**Step 5: Run the app to verify the CLI integration works**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src --help`

Expected: No import errors, help output displays

**Step 6: Run all existing tests to verify nothing is broken**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 7: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/__main__.py
git commit -m "feat: add outreach generation CLI flow to lead detail view"
```

---

### Task 8: Settings Menu — Outreach Provider Configuration

**Files:**
- Modify: `src/__main__.py`

**Step 1: Add outreach settings to the settings menu**

In `_show_settings_overview`, add outreach info to the settings table (after the concurrency rows, around line 199):

```python
        # Outreach
        table.add_row("12", "Outreach LLM Provider", settings.outreach.llm_provider.capitalize())
        table.add_row("13", "Outreach LLM Model", settings.outreach.llm_model)
```

Add outreach config option to the settings menu choices (before the Separator, around line 209):

```python
                {"name": "✉️  Outreach LLM settings", "value": "outreach"},
```

Add the handler in the settings menu loop (after the `api_help` handler, around line 233):

```python
        elif action == "outreach":
            _configure_outreach()
```

**Step 2: Implement `_configure_outreach`**

Add this function to `__main__.py` (after `_configure_concurrency`):

```python
def _configure_outreach():
    """Configure outreach LLM settings."""
    console.print()

    provider = inquirer.select(
        message="Select LLM provider for outreach generation:",
        choices=[
            {"name": "OpenAI (GPT-4o, GPT-4o-mini)", "value": "openai"},
            {"name": "Anthropic (Claude Sonnet, Claude Haiku)", "value": "anthropic"},
        ],
        default=settings.outreach.llm_provider,
    ).execute()
    settings.outreach.llm_provider = provider

    if provider == "openai":
        model_choices = [
            {"name": "gpt-4o (recommended)", "value": "gpt-4o"},
            {"name": "gpt-4o-mini (faster, cheaper)", "value": "gpt-4o-mini"},
        ]
    else:
        model_choices = [
            {"name": "claude-sonnet-4-5-20250929 (recommended)", "value": "claude-sonnet-4-5-20250929"},
            {"name": "claude-haiku-4-5-20251001 (faster, cheaper)", "value": "claude-haiku-4-5-20251001"},
        ]

    model = inquirer.select(
        message="Select model:",
        choices=model_choices,
        default=settings.outreach.llm_model,
    ).execute()
    settings.outreach.llm_model = model

    # Verify API key
    if provider == "openai" and not settings.openai_api_key:
        console.print("[yellow]Warning: OPENAI_API_KEY not set in .env[/yellow]")
    elif provider == "anthropic" and not settings.anthropic_api_key:
        console.print("[yellow]Warning: ANTHROPIC_API_KEY not set in .env[/yellow]")

    console.print(f"[green]✓ Outreach settings updated: {provider} / {model}[/green]")
```

**Step 3: Update API help to mention Anthropic**

In `_show_api_help`, add Anthropic to the optional keys section (around line 334):

```python
        "ANTHROPIC_API_KEY=your_key   [dim]# For outreach generation with Claude[/dim]\n"
```

And add to the "Get API keys" section:

```python
        "• Anthropic: [link]https://console.anthropic.com/[/link]\n"
```

**Step 4: Run all tests**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 5: Commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add src/__main__.py
git commit -m "feat: add outreach LLM provider settings to CLI"
```

---

### Task 9: Final Integration Test

**Files:**
- All existing files

**Step 1: Run the full test suite**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m pytest tests/ -v --tb=short`

Expected: All tests pass (existing + new)

**Step 2: Verify imports work**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -c "from src.llm_client import LLMClient; from src.outreach_generator import OutreachGenerator, MESSAGE_TYPES; print('All imports OK')"`

Expected: `All imports OK`

**Step 3: Verify the CLI starts without errors**

Run: `cd /home/farzin/PROSPECTFORGE/lead-generator && python -m src --help`

Expected: Help output with no import errors

**Step 4: Create data/outreach directory**

Run: `mkdir -p /home/farzin/PROSPECTFORGE/lead-generator/data/outreach`

**Step 5: Add data/outreach to .gitignore if not already present**

Check if `.gitignore` excludes data/ directory. If not, add `data/outreach/` to it.

**Step 6: Final commit**

```bash
cd /home/farzin/PROSPECTFORGE/lead-generator
git add -A
git commit -m "feat: complete outreach generation feature"
```
