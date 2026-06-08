"""Unit tests for RSSSource. No network — all HTTP mocked with respx."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import httpx
import pytest
import respx

from ai_news_digest.sources.rss import RSSSource

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://example.com/feed.xml"


def _mock_feed_body(monkeypatch_url: str = FEED_URL) -> respx.Router:
    router = respx.mock(assert_all_called=True)
    return router


def test_parses_items_and_assigns_source_name():
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    with respx.mock() as router:
        router.get(FEED_URL).mock(return_value=httpx.Response(200, content=body))
        items = RSSSource("Example", FEED_URL).fetch()

    assert len(items) == 3
    titles = [i.title for i in items]
    assert "New foundation model released" in titles
    assert all(i.source == "Example" for i in items)
    assert all(i.url.startswith("https://example.com/posts/") for i in items)


def test_published_at_is_tz_aware_utc():
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    with respx.mock() as router:
        router.get(FEED_URL).mock(return_value=httpx.Response(200, content=body))
        items = RSSSource("Example", FEED_URL).fetch()

    for item in items:
        assert item.published_at is not None
        assert item.published_at.tzinfo is not None
        # all converted to UTC by feedparser (it normalizes to UTC)
        assert item.published_at.utcoffset().total_seconds() == 0


def test_missing_date_yields_none():
    body = (FIXTURES / "sample_rss_no_date.xml").read_bytes()
    with respx.mock() as router:
        router.get(FEED_URL).mock(return_value=httpx.Response(200, content=body))
        items = RSSSource("Example", FEED_URL).fetch()

    assert len(items) == 1
    assert items[0].published_at is None


def test_http_error_raises():
    with respx.mock() as router:
        router.get(FEED_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            RSSSource("Example", FEED_URL).fetch()


def test_request_uses_user_agent_and_follows_redirects():
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    with respx.mock() as router:
        route = router.get(FEED_URL).mock(
            return_value=httpx.Response(200, content=body)
        )
        RSSSource("Example", FEED_URL, timeout=5.0).fetch()

    sent = route.calls.last.request
    assert "ai-news-digest" in sent.headers.get("user-agent", "")


def test_raw_text_comes_from_summary_or_description():
    body = (FIXTURES / "sample_rss.xml").read_bytes()
    with respx.mock() as router:
        router.get(FEED_URL).mock(return_value=httpx.Response(200, content=body))
        items = RSSSource("Example", FEED_URL).fetch()

    assert items[0].raw_text  # non-empty
    assert "foundation model launch" in items[0].raw_text
