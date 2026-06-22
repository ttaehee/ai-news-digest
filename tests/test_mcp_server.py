"""Unit tests for the MCP server's pure functions.

No network, no LLM — covers _resolve_category, _clamp, _filter_by_category,
and _render_payload. The get_ai_digest tool itself hits the live network
via _collect; that path is exercised by check_feeds and the daily run.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_news_digest.ai_processor import SYSTEM_PROMPT
from ai_news_digest.mcp_server import (
    HOURS_MAX,
    HOURS_MIN,
    TOP_K_MAX,
    TOP_K_MIN,
    _clamp,
    _filter_by_category,
    _render_payload,
    _resolve_category,
)
from ai_news_digest.sources.base import RawItem

NOW = datetime(2026, 6, 22, 0, 0, 0, tzinfo=timezone.utc)


def _item(
    source: str = "OpenAI Blog",
    title: str = "t",
    url: str = "https://e/x",
    raw_text: str = "some body",
) -> RawItem:
    return RawItem(
        title=title,
        url=url,
        source=source,
        published_at=NOW,
        raw_text=raw_text,
    )


# --- _resolve_category -------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Model", "Model"),
        ("Paper", "Paper"),
        ("Tool", "Tool"),
        ("Misc", "Misc"),
        ("Community", "Community"),
    ],
)
def test_resolve_category_english_canonical(value, expected):
    assert _resolve_category(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("모델", "Model"),
        ("논문", "Paper"),
        ("툴", "Tool"),
        ("기타", "Misc"),
        ("커뮤니티", "Community"),
    ],
)
def test_resolve_category_korean_aliases(value, expected):
    assert _resolve_category(value) == expected


@pytest.mark.parametrize("value", ["model", "MODEL", "MoDeL", "  Model  "])
def test_resolve_category_case_insensitive_and_strips_whitespace(value):
    assert _resolve_category(value) == "Model"


@pytest.mark.parametrize("value", [None, "", "전체", "all", "ALL"])
def test_resolve_category_all_returns_none(value):
    assert _resolve_category(value) is None


def test_resolve_category_unknown_raises():
    with pytest.raises(ValueError, match="unknown category"):
        _resolve_category("이상한값")


# --- _clamp -----------------------------------------------------------


def test_clamp_top_k_below_min():
    assert _clamp(0, TOP_K_MIN, TOP_K_MAX) == TOP_K_MIN


def test_clamp_top_k_above_max():
    assert _clamp(100, TOP_K_MIN, TOP_K_MAX) == TOP_K_MAX


def test_clamp_top_k_in_range():
    assert _clamp(5, TOP_K_MIN, TOP_K_MAX) == 5


def test_clamp_hours_below_min():
    assert _clamp(0, HOURS_MIN, HOURS_MAX) == HOURS_MIN


def test_clamp_hours_above_max():
    assert _clamp(1000, HOURS_MIN, HOURS_MAX) == HOURS_MAX


def test_clamp_hours_in_range():
    assert _clamp(24, HOURS_MIN, HOURS_MAX) == 24


# --- _filter_by_category ----------------------------------------------


def test_filter_community_keeps_only_hn():
    items = [
        _item(source="OpenAI Blog"),
        _item(source="Hacker News"),
        _item(source="arXiv cs.AI"),
    ]
    out = _filter_by_category(items, "Community")
    assert [i.source for i in out] == ["Hacker News"]


def test_filter_paper_keeps_only_arxiv():
    items = [
        _item(source="OpenAI Blog"),
        _item(source="Hacker News"),
        _item(source="arXiv cs.AI"),
        _item(source="arXiv cs.CL"),
    ]
    out = _filter_by_category(items, "Paper")
    assert sorted(i.source for i in out) == ["arXiv cs.AI", "arXiv cs.CL"]


@pytest.mark.parametrize("category", ["Model", "Tool", "Misc"])
def test_filter_model_tool_misc_drops_hn_and_arxiv(category):
    items = [
        _item(source="OpenAI Blog"),
        _item(source="Google DeepMind Blog"),
        _item(source="Hacker News"),
        _item(source="arXiv cs.AI"),
    ]
    out = _filter_by_category(items, category)
    assert {i.source for i in out} == {"OpenAI Blog", "Google DeepMind Blog"}


def test_filter_none_keeps_everything():
    items = [_item(source="OpenAI Blog"), _item(source="Hacker News")]
    assert _filter_by_category(items, None) == items


# --- _render_payload --------------------------------------------------


def test_render_payload_embeds_system_prompt_verbatim():
    text = _render_payload(
        [_item()], category=None, top_k=3, hours=24, failed_sources=[]
    )
    assert SYSTEM_PROMPT in text


def test_render_payload_lists_every_item():
    items = [
        _item(source="OpenAI Blog", title="first", url="https://e/1"),
        _item(source="arXiv cs.AI", title="second", url="https://e/2"),
    ]
    text = _render_payload(
        items, category=None, top_k=3, hours=24, failed_sources=[]
    )
    for needle in ("first", "second", "https://e/1", "https://e/2", "OpenAI Blog", "arXiv cs.AI"):
        assert needle in text


def test_render_payload_surfaces_conditions():
    text = _render_payload(
        [_item()],
        category="Community",
        top_k=5,
        hours=72,
        failed_sources=["BAIR"],
    )
    assert "Community" in text
    assert "top_k = 5" in text
    assert "최근 72시간" in text
    assert "BAIR" in text


def test_render_payload_failed_sources_empty_shows_none_label():
    text = _render_payload(
        [_item()], category=None, top_k=3, hours=24, failed_sources=[]
    )
    assert "소스 실패: 없음" in text


def test_render_payload_count_matches_items():
    items = [_item(url=f"https://e/{i}") for i in range(7)]
    text = _render_payload(
        items, category=None, top_k=3, hours=24, failed_sources=[]
    )
    assert "데이터 (7개 항목)" in text


def test_render_payload_uses_iso_timestamp():
    text = _render_payload(
        [_item()], category=None, top_k=3, hours=24, failed_sources=[]
    )
    assert NOW.isoformat() in text


def test_render_payload_includes_refine_block_when_true():
    text = _render_payload(
        [_item()],
        category=None,
        top_k=3,
        hours=24,
        failed_sources=[],
        refine=True,
    )
    assert "# 자가 개선 (refine)" in text
    # references the SYSTEM_PROMPT rules by topic instead of copy-pasting
    for keyword in ("금지어", "전문용어", "제목 번역", "길이"):
        assert keyword in text


def test_render_payload_omits_refine_block_when_false():
    text = _render_payload(
        [_item()],
        category=None,
        top_k=3,
        hours=24,
        failed_sources=[],
        refine=False,
    )
    assert "자가 개선" not in text


def test_render_payload_refine_defaults_to_false():
    text = _render_payload(
        [_item()], category=None, top_k=3, hours=24, failed_sources=[]
    )
    assert "자가 개선" not in text
