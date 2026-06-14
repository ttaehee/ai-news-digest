"""Unit tests for ClaudeProvider. The Anthropic SDK client is mocked."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ai_news_digest.ai_processor import CATEGORIES
from ai_news_digest.providers.claude import (
    DEFAULT_MODEL,
    EMIT_DIGEST_TOOL,
    ClaudeProvider,
)
from ai_news_digest.sources.base import RawItem


NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def _raw(title="T", url="https://example.com/a", source="Src", text="body") -> RawItem:
    return RawItem(title=title, url=url, source=source, published_at=NOW, raw_text=text)


def _payload_item(url="https://e/a", importance=5) -> dict:
    return {
        "title": "T",
        "url": url,
        "source": "Src",
        "importance": importance,
        "summary_kr": "summary line",
    }


def _payload(**cats) -> dict:
    base = {c: [] for c in CATEGORIES}
    base.update(cats)
    return {"categories": base}


def _fake_tool_use(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name="emit_digest", input=payload)


# --- tool schema sanity ----------------------------------------------------


def test_tool_schema_lists_all_four_categories():
    cats = EMIT_DIGEST_TOOL["input_schema"]["properties"]["categories"]
    assert set(cats["properties"]) == set(CATEGORIES)
    assert set(cats["required"]) == set(CATEGORIES)


def test_tool_schema_requires_string_summary():
    item_schema = EMIT_DIGEST_TOOL["input_schema"]["properties"]["categories"][
        "properties"
    ]["모델출시"]["items"]
    assert item_schema["properties"]["summary_kr"] == {"type": "string"}


# --- emit_digest --------------------------------------------------------


def test_provider_defaults_to_canonical_model():
    assert ClaudeProvider().model == DEFAULT_MODEL


def test_model_override_respected():
    assert ClaudeProvider(model="claude-sonnet-4-6").model == "claude-sonnet-4-6"


def test_emit_digest_invokes_client_with_forced_tool_use():
    payload = _payload(모델출시=[_payload_item()])
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(content=[_fake_tool_use(payload)])

    provider = ClaudeProvider(model="claude-test", client=client)
    out = provider.emit_digest([_raw()])

    assert out == payload
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-test"
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_digest"}
    assert kwargs["tools"] == [EMIT_DIGEST_TOOL]
    (sys_block,) = kwargs["system"]
    assert sys_block["cache_control"] == {"type": "ephemeral"}
    assert "AI 뉴스 다이제스트" in sys_block["text"]
    user_msg = kwargs["messages"][0]
    assert user_msg["role"] == "user"
    assert "emit_digest" in user_msg["content"]


def test_emit_digest_raises_when_no_tool_use_block():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hi")]
    )
    with pytest.raises(ValueError, match="emit_digest"):
        ClaudeProvider(client=client).emit_digest([_raw()])
