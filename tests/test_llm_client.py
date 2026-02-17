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
