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
