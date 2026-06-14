"""Claude provider — Anthropic SDK, structured output via forced tool-use.

The shared system prompt and input formatter live in `ai_processor`; this
module owns the Claude-specific tool schema and the actual ``messages.create``
call. SDK import is lazy so importing this module is free.
"""

from __future__ import annotations

from typing import Any

from ..ai_processor import CATEGORIES, SYSTEM_PROMPT, _items_to_prompt_json
from ..sources.base import RawItem
from .base import LLMProvider

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_DIGEST_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title":      {"type": "string"},
        "url":        {"type": "string"},
        "source":     {"type": "string"},
        "importance": {"type": "integer", "minimum": 0, "maximum": 10},
        "summary_kr": {"type": "string"},
    },
    "required": ["title", "url", "source", "importance", "summary_kr"],
}

EMIT_DIGEST_TOOL: dict[str, Any] = {
    "name": "emit_digest",
    "description": (
        "Emit the final categorized digest. Call this exactly once. "
        "Group similar items into the most authoritative primary source, "
        "classify by category, score importance 0–10, and write a single "
        "concise Korean summary line per item. Return at most 3 items per category, "
        "ordered by descending importance."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "categories": {
                "type": "object",
                "properties": {cat: {"type": "array", "items": _DIGEST_ITEM_SCHEMA} for cat in CATEGORIES},
                "required": list(CATEGORIES),
            },
        },
        "required": ["categories"],
    },
}


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, *, model: str | None = None, client: Any = None) -> None:
        self.model = model or DEFAULT_MODEL
        self._client = client  # injected for tests; built lazily otherwise

    def _ensure_client(self) -> Any:
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic()
        return self._client

    def emit_digest(self, items: list[RawItem]) -> dict:
        user_msg = (
            "아래는 정규화된 AI 뉴스 항목 목록(JSON)이다. emit_digest 도구를 호출해 "
            "다이제스트를 반환하라.\n\n" + _items_to_prompt_json(items)
        )
        resp = self._ensure_client().messages.create(
            model=self.model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[EMIT_DIGEST_TOOL],
            tool_choice={"type": "tool", "name": "emit_digest"},
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_digest":
                return block.input
        raise ValueError("model did not emit an emit_digest tool_use block")
