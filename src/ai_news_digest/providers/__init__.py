"""LLM provider plugins. Pick one via `get_provider(LLM_PROVIDER)`."""

from __future__ import annotations

from .base import LLMProvider
from .claude import ClaudeProvider
from .gemini import GeminiProvider

__all__ = ["LLMProvider", "ClaudeProvider", "GeminiProvider", "get_provider"]

DEFAULT_PROVIDER = "gemini"


def get_provider(
    name: str | None = None,
    *,
    model: str | None = None,
    client=None,
) -> LLMProvider:
    """Instantiate the LLM provider named in ``LLM_PROVIDER``.

    ``client`` is for tests/dependency injection; production paths leave it
    None so each provider builds its own SDK client lazily.
    """
    selected = (name or DEFAULT_PROVIDER).strip().lower()
    if selected == "gemini":
        return GeminiProvider(model=model, client=client)
    if selected == "claude":
        return ClaudeProvider(model=model, client=client)
    raise ValueError(
        f"unknown LLM_PROVIDER: {name!r} (expected 'gemini' or 'claude')"
    )
