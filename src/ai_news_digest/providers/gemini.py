"""Gemini provider — google-genai SDK, structured output via response_schema.

Korean property keys ("모델출시", etc.) are used directly; the schema mirrors
the Claude tool's input shape so the validator downstream is provider-agnostic.
If a future Gemini revision rejects non-ASCII keys, swap to English keys and
map at the provider boundary (PLAN §11).
"""

from __future__ import annotations

import json
from typing import Any

from ..ai_processor import CATEGORIES, SYSTEM_PROMPT, _items_to_prompt_json
from ..sources.base import RawItem
from .base import LLMProvider

DEFAULT_MODEL = "gemini-2.5-flash"

_DIGEST_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title":      {"type": "string"},
        "url":        {"type": "string"},
        "source":     {"type": "string"},
        "importance": {"type": "integer"},
        "summary_kr": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "url", "source", "importance", "summary_kr"],
}

GEMINI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "object",
            "properties": {cat: {"type": "array", "items": _DIGEST_ITEM_SCHEMA} for cat in CATEGORIES},
            "required": list(CATEGORIES),
        },
        "notes": {"type": "string"},
    },
    "required": ["categories"],
}


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, model: str | None = None, client: Any = None) -> None:
        self.model = model or DEFAULT_MODEL
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            from google import genai
            # SDK reads GEMINI_API_KEY (and falls back to GOOGLE_API_KEY).
            self._client = genai.Client()
        return self._client

    def emit_digest(self, items: list[RawItem]) -> dict:
        from google.genai import types

        user_msg = (
            "아래는 정규화된 AI 뉴스 항목 목록(JSON)이다. 응답은 정확히 "
            "주어진 스키마에 맞는 단일 JSON 객체로만 반환하라.\n\n"
            + _items_to_prompt_json(items)
        )
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GEMINI_SCHEMA,
        )
        resp = self._ensure_client().models.generate_content(
            model=self.model,
            contents=user_msg,
            config=config,
        )
        text = getattr(resp, "text", None)
        if not text:
            raise ValueError("Gemini returned empty response.text")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini returned non-JSON text: {e}") from e
