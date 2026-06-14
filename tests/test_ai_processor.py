"""Unit tests for the AI processing stage. All LLM calls go through the
`caller` seam; no network or SDK interaction. Provider-specific tests
live in tests/test_providers_*.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ai_news_digest.ai_processor import (
    CATEGORIES,
    MAX_RAW_TEXT_CHARS,
    RETRY_BACKOFF_S,
    SPLIT_THRESHOLD,
    SYSTEM_PROMPT,
    TOP_PER_CATEGORY,
    Digest,
    DigestItem,
    _fallback_digest,
    _items_to_prompt_json,
    _merge_digests,
    _parse_item,
    _truncate,
    _validate_payload,
    process,
)
from ai_news_digest.sources.base import RawItem


@pytest.fixture(autouse=True)
def _mock_retry_sleep(monkeypatch):
    """Tests should never actually wait for the AI-call retry backoff."""
    monkeypatch.setattr("ai_news_digest.ai_processor.time.sleep", lambda _: None)


NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


def _raw(title="T", url="https://example.com/a", source="Src", text="body") -> RawItem:
    return RawItem(title=title, url=url, source=source, published_at=NOW, raw_text=text)


def _payload_item(
    title="T",
    url="https://example.com/a",
    source="Src",
    importance=5,
    summary="ko summary",
) -> dict:
    return {
        "title": title,
        "url": url,
        "source": source,
        "importance": importance,
        "summary_kr": summary,
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
    assert d.categories["모델출시"][0].summary_kr == "ko summary"


def test_validate_payload_trims_to_top_per_category_by_importance():
    items = [
        _payload_item(title=f"#{i}", url=f"https://e/{i}", importance=i)
        for i in range(10)
    ]
    d = _validate_payload(_payload(모델출시=items))
    kept = d.categories["모델출시"]
    assert len(kept) == TOP_PER_CATEGORY
    assert [it.importance for it in kept] == list(range(9, 9 - TOP_PER_CATEGORY, -1))


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


def test_parse_item_raises_when_summary_not_string():
    item = _payload_item(summary=["was", "a", "list"])
    with pytest.raises(ValueError, match="string"):
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
    assert all(it.summary_kr == "" for it in d.categories["기타"])


def test_fallback_digest_uses_url_when_title_missing():
    item = RawItem(title="", url="https://e/x", source="s", published_at=NOW, raw_text="")
    d = _fallback_digest([item])
    assert d.fallback is True
    assert d.categories["기타"][0].title == "https://e/x"


def test_attempt_sleeps_with_backoff_between_failed_and_next_attempt(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(
        "ai_news_digest.ai_processor.time.sleep",
        lambda s: sleeps.append(s),
    )
    caller = MagicMock(
        side_effect=[ValueError("first"), _payload(모델출시=[_payload_item()])]
    )
    process([_raw()], caller=caller)
    # Exactly one sleep, between attempt 1 (failed) and attempt 2 (success).
    assert sleeps == [RETRY_BACKOFF_S]


def test_no_sleep_when_first_attempt_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(
        "ai_news_digest.ai_processor.time.sleep",
        lambda s: sleeps.append(s),
    )
    caller = MagicMock(return_value=_payload(모델출시=[_payload_item()]))
    process([_raw()], caller=caller)
    assert sleeps == []


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


def test_merge_clears_fallback_flag_when_real_items_outsort_dump():
    # Real items in 기타 push the fallback's importance-0 entries out of the
    # top-N; merged digest is fully real.
    real = _validate_payload(_payload(
        기타=[
            _payload_item(url=f"https://e/r{i}", importance=10 - i)
            for i in range(TOP_PER_CATEGORY)
        ],
    ))
    fb = _fallback_digest([_raw(url="https://e/fb1"), _raw(url="https://e/fb2")])
    merged = _merge_digests([real, fb])
    assert merged.fallback is False
    # fallback's "원본 링크 덤프(폴백)" note dropped because its items didn't surface
    assert merged.notes == ""
    urls = {it.url for it in merged.categories["기타"]}
    assert urls == {f"https://e/r{i}" for i in range(TOP_PER_CATEGORY)}


def test_merge_keeps_fallback_flag_when_dump_items_survive():
    # Real digest has nothing in 기타, so fallback dump items occupy it
    # and the warning + note must be preserved.
    real = _validate_payload(_payload(모델출시=[_payload_item()]))
    fb = _fallback_digest([_raw(url="https://e/fb")])
    merged = _merge_digests([real, fb])
    assert merged.fallback is True
    assert len(merged.categories["기타"]) == 1
    assert merged.notes == "원본 링크 덤프(폴백)"


def test_merge_two_fallback_digests_keeps_flag():
    a = _fallback_digest([_raw(url="https://e/a")])
    b = _fallback_digest([_raw(url="https://e/b")])
    assert _merge_digests([a, b]).fallback is True


def test_merge_keeps_real_notes_when_fallback_note_dropped():
    real = Digest(
        categories={
            "모델출시": (),
            "논문": (),
            "툴": (),
            "기타": tuple(
                DigestItem(
                    title=f"r{i}",
                    url=f"https://e/r{i}",
                    source="S",
                    importance=10 - i,
                    summary_kr="real summary",
                )
                for i in range(5)
            ),
        },
        notes="real model note",
        fallback=False,
    )
    fb = _fallback_digest([_raw(url="https://e/fb")])
    merged = _merge_digests([real, fb])
    assert merged.fallback is False
    assert merged.notes == "real model note"


# --- system prompt ----------------------------------------------------

def test_system_prompt_mentions_pii_guard():
    # Privacy rule (#8) must be present; the model is the last guard before send.
    assert "개인" in SYSTEM_PROMPT
