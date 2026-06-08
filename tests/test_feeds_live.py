"""Live network checks for every registered RSS feed.

Marked `network`; deselected by default. Run explicitly with:

    pytest -m network

Mirrors what scripts/check_feeds.py does, parameterized per source so failures
identify the specific feed.
"""

from __future__ import annotations

import time

import feedparser
import httpx
import pytest

from ai_news_digest.sources.registry import DEFAULT_SOURCES
from ai_news_digest.sources.rss import RSSSource

_RSS_SOURCES = [s for s in DEFAULT_SOURCES if isinstance(s, RSSSource)]
_TIMEOUT = 20.0
_RETRY_BACKOFFS_S = (2.0, 4.0)  # waits between attempts; total attempts = len + 1


def _get_with_retries(url: str) -> httpx.Response:
    last: httpx.Response | None = None
    last_exc: Exception | None = None
    backoffs = (*_RETRY_BACKOFFS_S, None)
    for wait in backoffs:
        try:
            resp = httpx.get(
                url,
                timeout=_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "ai-news-digest-test/0.1"},
            )
            if resp.status_code == 200:
                return resp
            last = resp
        except httpx.HTTPError as e:
            last_exc = e
        if wait is not None:
            time.sleep(wait)
    if last is not None:
        return last
    assert last_exc is not None
    raise last_exc


@pytest.mark.network
@pytest.mark.parametrize("src", _RSS_SOURCES, ids=lambda s: s.name)
def test_feed_alive(src: RSSSource) -> None:
    resp = _get_with_retries(src.url)
    assert resp.status_code == 200, f"{src.name}: HTTP {resp.status_code}"

    parsed = feedparser.parse(resp.content)
    assert len(parsed.entries) > 0, f"{src.name}: feed parsed to 0 entries"
