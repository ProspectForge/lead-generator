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
