"""Unit tests for the AI processing stage. All Claude calls go through the
`caller` seam; no network or SDK interaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ai_news_digest.ai_processor import (
    CATEGORIES,
    DEFAULT_MODEL,
    EMIT_DIGEST_TOOL,
    MAX_RAW_TEXT_CHARS,
    SPLIT_THRESHOLD,
    SYSTEM_PROMPT,
    TOP_PER_CATEGORY,
    Digest,
    DigestItem,
    _call_emit_digest,
    _fallback_digest,
    _items_to_prompt_json,
    _merge_digests,
    _parse_item,
    _truncate,
    _validate_payload,
    process,
)
from ai_news_digest.sources.base import RawItem


NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


def _raw(title="T", url="https://example.com/a", source="Src", text="body") -> RawItem:
    return RawItem(title=title, url=url, source=source, published_at=NOW, raw_text=text)


def _payload_item(
    title="T",
    url="https://example.com/a",
    source="Src",
    importance=5,
    summary=("ko1", "ko2", "ko3"),
) -> dict:
    return {
        "title": title,
        "url": url,
        "source": source,
        "importance": importance,
        "summary_kr": list(summary),
    }


def _payload(**cats) -> dict:
    base = {c: [] for c in CATEGORIES}
    base.update(cats)
    return {"categories": base}


# --- helpers ------------------------------------------------------------

def test_truncate_passes_through_short_text():
    assert _truncate("hello", 10) == "hello"


def test_truncate_appends_ellipsis_when_over_limit():
    out = _truncate("x" * 50, 10)
    assert out.endswith("…")
    assert len(out) == 11  # 10 chars + ellipsis


def test_items_to_prompt_json_serializes_published_at_iso():
    body = _items_to_prompt_json([_raw()])
    data = json.loads(body)
    assert data[0]["published_at"] == NOW.isoformat()


def test_items_to_prompt_json_truncates_raw_text():
    long = "x" * (MAX_RAW_TEXT_CHARS + 500)
    body = _items_to_prompt_json([_raw(text=long)])
    data = json.loads(body)
    assert data[0]["raw_text"].endswith("…")
    assert len(data[0]["raw_text"]) <= MAX_RAW_TEXT_CHARS + 1


def test_items_to_prompt_json_handles_none_date():
    item = RawItem(title="t", url="u", source="s", published_at=None, raw_text="r")
    data = json.loads(_items_to_prompt_json([item]))
    assert data[0]["published_at"] is None


# --- validation --------------------------------------------------------

def test_validate_payload_builds_digest():
    payload = _payload(모델출시=[_payload_item()])
    d = _validate_payload(payload)
    assert isinstance(d, Digest)
    assert len(d.categories["모델출시"]) == 1
    assert d.categories["모델출시"][0].summary_kr == ("ko1", "ko2", "ko3")


def test_validate_payload_trims_to_top_per_category_by_importance():
    items = [
        _payload_item(title=f"#{i}", url=f"https://e/{i}", importance=i)
        for i in range(10)
    ]
    d = _validate_payload(_payload(모델출시=items))
    kept = d.categories["모델출시"]
    assert len(kept) == TOP_PER_CATEGORY
    assert [it.importance for it in kept] == [9, 8, 7, 6, 5]


def test_validate_payload_raises_without_categories_key():
    with pytest.raises(ValueError, match="categories"):
        _validate_payload({"notes": "x"})


def test_validate_payload_raises_when_category_not_list():
    bad = {"categories": {**{c: [] for c in CATEGORIES}, "모델출시": "oops"}}
    with pytest.raises(ValueError, match="must be a list"):
        _validate_payload(bad)


def test_parse_item_raises_on_missing_field():
    item = _payload_item()
    item.pop("url")
    with pytest.raises(ValueError, match="url"):
        _parse_item(item)


def test_parse_item_raises_when_summary_not_three_lines():
    item = _payload_item(summary=("only", "two"))
    with pytest.raises(ValueError, match="3"):
        _parse_item(item)


def test_parse_item_clamps_importance_to_zero_ten():
    high = _parse_item(_payload_item(importance=99))
    low = _parse_item(_payload_item(importance=-5))
    assert high.importance == 10
    assert low.importance == 0


# --- process happy path ------------------------------------------------

def test_process_returns_empty_digest_on_empty_input():
    d = process([])
    assert isinstance(d, Digest)
    assert d.total_items() == 0
    assert all(d.categories[c] == () for c in CATEGORIES)


def test_process_uses_caller_and_returns_digest():
    items = [_raw()]
    caller = MagicMock(
        return_value=_payload(모델출시=[_payload_item(title="MyTitle")])
    )
    d = process(items, caller=caller)
    caller.assert_called_once()
    (passed_items,) = caller.call_args.args
    assert passed_items == items
    assert d.categories["모델출시"][0].title == "MyTitle"
    assert d.fallback is False


# --- retry + fallback --------------------------------------------------

def test_process_retries_once_on_first_failure():
    items = [_raw()]
    caller = MagicMock(
        side_effect=[ValueError("nope"), _payload(논문=[_payload_item()])]
    )
    d = process(items, caller=caller)
    assert caller.call_count == 2
    assert d.categories["논문"][0].title == "T"
    assert d.fallback is False


def test_process_falls_back_after_two_failures():
    items = [
        _raw(title="link-one", url="https://e/1"),
        _raw(title="link-two", url="https://e/2"),
    ]
    caller = MagicMock(side_effect=[ValueError("a"), ValueError("b")])
    d = process(items, caller=caller)
    assert caller.call_count == 2
    assert d.fallback is True
    assert d.notes == "원본 링크 덤프(폴백)"
    # All items dumped into 기타 with importance 0 and empty summary
    assert len(d.categories["기타"]) == 2
    assert {it.url for it in d.categories["기타"]} == {"https://e/1", "https://e/2"}
    assert all(it.importance == 0 for it in d.categories["기타"])
    assert all(it.summary_kr == ("", "", "") for it in d.categories["기타"])


def test_fallback_digest_uses_url_when_title_missing():
    item = RawItem(title="", url="https://e/x", source="s", published_at=NOW, raw_text="")
    d = _fallback_digest([item])
    assert d.fallback is True
    assert d.categories["기타"][0].title == "https://e/x"


# --- split + merge ----------------------------------------------------

def test_process_splits_when_input_exceeds_threshold():
    items = [_raw(title=f"t{i}", url=f"https://e/{i}") for i in range(SPLIT_THRESHOLD + 2)]
    caller = MagicMock(return_value=_payload(논문=[_payload_item()]))
    process(items, caller=caller)
    assert caller.call_count == 2
    first_chunk, second_chunk = (c.args[0] for c in caller.call_args_list)
    assert len(first_chunk) + len(second_chunk) == len(items)
    assert first_chunk and second_chunk  # both non-empty
    # disjoint slices
    assert {i.url for i in first_chunk}.isdisjoint({i.url for i in second_chunk})


def test_merge_digests_dedups_by_url_and_keeps_higher_importance():
    a = _validate_payload(_payload(모델출시=[
        _payload_item(url="https://e/dup", importance=4),
        _payload_item(url="https://e/a", importance=7),
    ]))
    b = _validate_payload(_payload(모델출시=[
        _payload_item(url="https://e/dup", importance=9),  # higher → should win
        _payload_item(url="https://e/b", importance=6),
    ]))
    merged = _merge_digests([a, b])
    urls = [it.url for it in merged.categories["모델출시"]]
    assert urls == ["https://e/dup", "https://e/a", "https://e/b"]
    assert merged.categories["모델출시"][0].importance == 9


def test_merge_digests_caps_each_category_to_top_per_category():
    half = _validate_payload(_payload(논문=[
        _payload_item(url=f"https://e/{i}", importance=10 - i) for i in range(5)
    ]))
    other = _validate_payload(_payload(논문=[
        _payload_item(url=f"https://e/o{i}", importance=10 - i) for i in range(5)
    ]))
    merged = _merge_digests([half, other])
    assert len(merged.categories["논문"]) == TOP_PER_CATEGORY


def test_merge_propagates_fallback_flag():
    fb = _fallback_digest([_raw()])
    ok = _validate_payload(_payload(모델출시=[_payload_item()]))
    assert _merge_digests([ok, fb]).fallback is True


# --- tool schema sanity -----------------------------------------------

def test_tool_schema_lists_all_four_categories():
    cats = EMIT_DIGEST_TOOL["input_schema"]["properties"]["categories"]
    assert set(cats["properties"]) == set(CATEGORIES)
    assert set(cats["required"]) == set(CATEGORIES)


def test_tool_schema_requires_three_line_summary():
    item_schema = EMIT_DIGEST_TOOL["input_schema"]["properties"]["categories"][
        "properties"
    ]["모델출시"]["items"]
    s = item_schema["properties"]["summary_kr"]
    assert s["minItems"] == 3 and s["maxItems"] == 3


def test_system_prompt_mentions_pii_guard():
    # Privacy rule (#8) must be present; the model is the last guard before send.
    assert "개인" in SYSTEM_PROMPT


# --- _call_emit_digest with a fake SDK client -------------------------

def _fake_tool_use(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name="emit_digest", input=payload)


def test_call_emit_digest_invokes_client_with_forced_tool_use():
    payload = _payload(모델출시=[_payload_item()])
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(content=[_fake_tool_use(payload)])

    out = _call_emit_digest(client, DEFAULT_MODEL, [_raw()])

    assert out == payload
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_digest"}
    assert kwargs["tools"] == [EMIT_DIGEST_TOOL]
    # System prompt sent with prompt-cache control.
    (sys_block,) = kwargs["system"]
    assert sys_block["cache_control"] == {"type": "ephemeral"}
    assert "AI 뉴스 다이제스트" in sys_block["text"]
    # User message embeds the JSON payload.
    user_msg = kwargs["messages"][0]
    assert user_msg["role"] == "user"
    assert "emit_digest" in user_msg["content"]


def test_call_emit_digest_raises_when_no_tool_use_block():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hi")]
    )
    with pytest.raises(ValueError, match="emit_digest"):
        _call_emit_digest(client, DEFAULT_MODEL, [_raw()])
