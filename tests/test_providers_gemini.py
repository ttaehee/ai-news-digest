"""Unit tests for GeminiProvider. The google-genai client is mocked."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ai_news_digest.ai_processor import CATEGORIES
from ai_news_digest.providers.gemini import (
    DEFAULT_MODEL,
    GEMINI_SCHEMA,
    GeminiProvider,
)
from ai_news_digest.sources.base import RawItem


NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def _raw() -> RawItem:
    return RawItem(
        title="T",
        url="https://e/a",
        source="Src",
        published_at=NOW,
        raw_text="body",
    )


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


# --- schema sanity --------------------------------------------------------


def test_schema_lists_all_categories():
    cats = GEMINI_SCHEMA["properties"]["categories"]
    assert set(cats["properties"]) == set(CATEGORIES)
    assert set(cats["required"]) == set(CATEGORIES)


def test_schema_item_requires_title_url_source_importance_summary():
    item = GEMINI_SCHEMA["properties"]["categories"]["properties"]["Model"]["items"]
    assert set(item["required"]) == {
        "title",
        "url",
        "source",
        "importance",
        "summary_kr",
    }


# --- emit_digest ----------------------------------------------------------


def test_provider_defaults_to_canonical_model():
    assert GeminiProvider().model == DEFAULT_MODEL


def test_model_override_respected():
    assert GeminiProvider(model="gemini-2.5-flash-lite").model == "gemini-2.5-flash-lite"


def test_emit_digest_returns_parsed_json_dict():
    payload = _payload(Paper=[_payload_item()])
    text = json.dumps(payload, ensure_ascii=False)

    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)

    out = GeminiProvider(model="gemini-test", client=client).emit_digest([_raw()])
    assert out == payload


def test_emit_digest_passes_model_and_schema_config():
    payload = _payload(Model=[_payload_item()])
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps(payload, ensure_ascii=False)
    )

    GeminiProvider(model="gemini-test", client=client).emit_digest([_raw()])

    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-test"
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema == GEMINI_SCHEMA
    assert "AI 뉴스 다이제스트" in config.system_instruction
    # user msg embeds the items JSON
    assert "정규화된 AI 뉴스" in kwargs["contents"]


def test_emit_digest_raises_on_empty_text():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text="")
    with pytest.raises(ValueError, match="empty"):
        GeminiProvider(client=client).emit_digest([_raw()])


def test_emit_digest_raises_on_non_json_text():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text="not json {")
    with pytest.raises(ValueError, match="non-JSON"):
        GeminiProvider(client=client).emit_digest([_raw()])
