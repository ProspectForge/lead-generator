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
