"""Unit tests for HnSource. httpx is mocked via respx — no network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from ai_news_digest.sources.hn import HnSource

_API = "https://hn.algolia.com/api/v1/search_by_date"
_EPOCH = 1750000000  # arbitrary fixed timestamp for deterministic tests
_EXPECTED_DT = datetime.fromtimestamp(_EPOCH, tz=timezone.utc)


def _hit(
    *,
    title: str = "Claude 4.7 released",
    url: str | None = "https://anthropic.com/news/c47",
    object_id: str = "12345",
    points: int = 200,
    num_comments: int = 80,
    created_at_i: int = _EPOCH,
    story_text: str | None = None,
) -> dict:
    return {
        "title": title,
        "url": url,
        "objectID": object_id,
        "points": points,
        "num_comments": num_comments,
        "created_at_i": created_at_i,
        "story_text": story_text,
    }


def _body(hits: list[dict]) -> bytes:
    return json.dumps({"hits": hits}).encode("utf-8")


# --- request shape -------------------------------------------------------


def test_request_carries_default_keywords_tags_filters_limit():
    with respx.mock() as router:
        route = router.get(_API).mock(return_value=httpx.Response(200, content=_body([])))
        HnSource().fetch()
    sent = route.calls.last.request
    assert sent.url.params["tags"] == "story"
    # Keywords appear in both `query` (Algolia's default-AND search) and
    # `optionalWords` (makes each one optional → OR-like recall in one call).
    assert sent.url.params["query"] == "AI LLM GPT Claude Gemini Anthropic OpenAI"
    assert sent.url.params["optionalWords"] == "AI,LLM,GPT,Claude,Gemini,Anthropic,OpenAI"
    assert sent.url.params["numericFilters"] == "points>=50"
    assert sent.url.params["hitsPerPage"] == "30"


def test_constructor_overrides_propagate_to_params():
    with respx.mock() as router:
        route = router.get(_API).mock(return_value=httpx.Response(200, content=_body([])))
        HnSource(keywords=("RAG", "agents"), min_points=99, limit=10).fetch()
    sent = route.calls.last.request
    assert sent.url.params["query"] == "RAG agents"
    assert sent.url.params["optionalWords"] == "RAG,agents"
    assert sent.url.params["numericFilters"] == "points>=99"
    assert sent.url.params["hitsPerPage"] == "10"


def test_sends_user_agent_header():
    with respx.mock() as router:
        route = router.get(_API).mock(return_value=httpx.Response(200, content=_body([])))
        HnSource().fetch()
    assert "ai-news-digest" in route.calls.last.request.headers.get("user-agent", "")


# --- response parsing ---------------------------------------------------


def test_parses_hit_to_raw_item():
    with respx.mock() as router:
        router.get(_API).mock(return_value=httpx.Response(200, content=_body([_hit()])))
        items = HnSource().fetch()

    assert len(items) == 1
    item = items[0]
    assert item.title == "Claude 4.7 released"
    assert item.url == "https://anthropic.com/news/c47"
    assert item.source == "Hacker News"
    assert item.published_at == _EXPECTED_DT
    assert item.published_at.tzinfo is timezone.utc
    assert "200 points" in item.raw_text
    assert "80 comments" in item.raw_text


def test_custom_source_name_overrides_default():
    with respx.mock() as router:
        router.get(_API).mock(return_value=httpx.Response(200, content=_body([_hit()])))
        items = HnSource(name="HN").fetch()
    assert items[0].source == "HN"


def test_ask_hn_falls_back_to_yc_item_url_when_external_url_missing():
    with respx.mock() as router:
        router.get(_API).mock(
            return_value=httpx.Response(200, content=_body([_hit(url=None, object_id="987654")]))
        )
        items = HnSource().fetch()
    assert items[0].url == "https://news.ycombinator.com/item?id=987654"


def test_story_text_appended_to_raw_text_when_present():
    with respx.mock() as router:
        router.get(_API).mock(
            return_value=httpx.Response(
                200,
                content=_body(
                    [_hit(url=None, story_text="What do you think about Claude 4.7?")]
                ),
            )
        )
        items = HnSource().fetch()
    text = items[0].raw_text
    assert "200 points, 80 comments" in text
    assert "What do you think about Claude 4.7?" in text


def test_missing_points_and_comments_default_to_zero():
    raw_hit = _hit()
    raw_hit["points"] = None
    raw_hit["num_comments"] = None
    with respx.mock() as router:
        router.get(_API).mock(return_value=httpx.Response(200, content=_body([raw_hit])))
        items = HnSource().fetch()
    assert "0 points, 0 comments" in items[0].raw_text


def test_empty_hits_returns_empty_list():
    with respx.mock() as router:
        router.get(_API).mock(return_value=httpx.Response(200, content=_body([])))
        assert HnSource().fetch() == []


def test_preserves_hit_order():
    hits = [
        _hit(title="first", url="https://e/1", object_id="1"),
        _hit(title="second", url="https://e/2", object_id="2"),
        _hit(title="third", url="https://e/3", object_id="3"),
    ]
    with respx.mock() as router:
        router.get(_API).mock(return_value=httpx.Response(200, content=_body(hits)))
        items = HnSource().fetch()
    assert [i.title for i in items] == ["first", "second", "third"]


# --- error handling ------------------------------------------------------


def test_http_error_propagates():
    with respx.mock() as router:
        router.get(_API).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            HnSource().fetch()


def test_network_error_propagates():
    with respx.mock() as router:
        router.get(_API).mock(side_effect=httpx.ConnectError("net down"))
        with pytest.raises(httpx.ConnectError):
            HnSource().fetch()
