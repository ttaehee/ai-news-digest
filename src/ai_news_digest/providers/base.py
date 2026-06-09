"""LLM provider interface — one method, one responsibility."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..sources.base import RawItem


class LLMProvider(ABC):
    """Translate a list of RawItems into the raw structured-digest dict.

    Implementations own the SDK call and structured-output mechanism
    (Claude → forced tool-use, Gemini → response_schema). Validation,
    retry, fallback, split-merge stay in `ai_processor.process`.
    """

    name: str
    model: str

    @abstractmethod
    def emit_digest(self, items: list[RawItem]) -> dict: ...
