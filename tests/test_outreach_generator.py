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
    user_prompt = call_args.kwargs.get("user_prompt") or call_args[0][1]
    assert "Test Campaign" in user_prompt


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
    system = call_args.kwargs.get("system_prompt") or call_args[0][0]
    assert "consulting company" in system.lower() or "outreach" in system.lower()
