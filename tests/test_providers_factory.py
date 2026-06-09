"""Tests for the `get_provider` factory."""

from __future__ import annotations

import pytest

from ai_news_digest.providers import (
    ClaudeProvider,
    GeminiProvider,
    get_provider,
)
from ai_news_digest.providers.claude import DEFAULT_MODEL as CLAUDE_DEFAULT
from ai_news_digest.providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT


def test_default_provider_is_gemini():
    p = get_provider()
    assert isinstance(p, GeminiProvider)
    assert p.name == "gemini"
    assert p.model == GEMINI_DEFAULT


def test_explicit_gemini():
    assert isinstance(get_provider("gemini"), GeminiProvider)


def test_explicit_claude():
    p = get_provider("claude")
    assert isinstance(p, ClaudeProvider)
    assert p.name == "claude"
    assert p.model == CLAUDE_DEFAULT


def test_provider_name_is_case_insensitive_and_strips_whitespace():
    assert isinstance(get_provider(" CLAUDE "), ClaudeProvider)
    assert isinstance(get_provider("Gemini"), GeminiProvider)


def test_model_override_propagates():
    g = get_provider("gemini", model="gemini-2.5-flash-lite")
    assert g.model == "gemini-2.5-flash-lite"
    c = get_provider("claude", model="claude-sonnet-4-6")
    assert c.model == "claude-sonnet-4-6"


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="unknown LLM_PROVIDER"):
        get_provider("openai")


def test_none_falls_back_to_default():
    assert isinstance(get_provider(None), GeminiProvider)
