"""Unit tests for ArxivSource. No network — HTTP mocked with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_news_digest.sources.arxiv import ArxivSource


def _make_feed(n: int, category: str = "cs.AI") -> bytes:
    """Build an arXiv-shaped RSS body with ``n`` items, newest first."""
    items = []
    for i in range(n):
        day = max(1, 28 - (i % 28))  # spread across days, all in May 2026
        items.append(
            f"""    <item>
      <title>Paper {i}: A study of foo</title>
      <link>https://arxiv.org/abs/2606.{i:05d}</link>
      <description>Abstract for paper {i}.</description>
      <pubDate>Mon, {day:02d} May 2026 12:00:00 GMT</pubDate>
    </item>"""
        )
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>arXiv {category}</title>
    <link>https://arxiv.org/list/{category}/recent</link>
    <description>Recent submissions to {category}</description>
{chr(10).join(items)}
  </channel>
</rss>"""
    return body.encode("utf-8")


def _url(category: str) -> str:
    return f"https://export.arxiv.org/rss/{category}"


def test_url_uses_export_arxiv_https():
    src = ArxivSource("cs.AI")
    assert src.url == "https://export.arxiv.org/rss/cs.AI"


def test_default_limit_is_30():
    assert ArxivSource("cs.AI").limit == 30


def test_source_name_includes_category():
    assert ArxivSource("cs.LG").name == "arXiv cs.LG"


def test_caps_items_at_default_limit():
    with respx.mock() as router:
        router.get(_url("cs.AI")).mock(
            return_value=httpx.Response(200, content=_make_feed(35))
        )
        items = ArxivSource("cs.AI").fetch()
    assert len(items) == 30


def test_respects_custom_limit():
    with respx.mock() as router:
        router.get(_url("cs.LG")).mock(
            return_value=httpx.Response(200, content=_make_feed(20, "cs.LG"))
        )
        items = ArxivSource("cs.LG", limit=10).fetch()
    assert len(items) == 10


def test_returns_all_when_feed_smaller_than_limit():
    with respx.mock() as router:
        router.get(_url("cs.CL")).mock(
            return_value=httpx.Response(200, content=_make_feed(5, "cs.CL"))
        )
        items = ArxivSource("cs.CL").fetch()
    assert len(items) == 5


def test_preserves_newest_first_order():
    with respx.mock() as router:
        router.get(_url("cs.AI")).mock(
            return_value=httpx.Response(200, content=_make_feed(35))
        )
        items = ArxivSource("cs.AI").fetch()
    # _make_feed numbers items 0..34 in order, and our slice takes the first 30.
    assert items[0].title.startswith("Paper 0:")
    assert items[29].title.startswith("Paper 29:")


def test_items_carry_category_in_source_name():
    with respx.mock() as router:
        router.get(_url("cs.AI")).mock(
            return_value=httpx.Response(200, content=_make_feed(3))
        )
        items = ArxivSource("cs.AI").fetch()
    assert all(i.source == "arXiv cs.AI" for i in items)


def test_item_url_points_to_arxiv_abs():
    with respx.mock() as router:
        router.get(_url("cs.AI")).mock(
            return_value=httpx.Response(200, content=_make_feed(3))
        )
        items = ArxivSource("cs.AI").fetch()
    assert items[0].url.startswith("https://arxiv.org/abs/")


def test_http_error_propagates():
    with respx.mock() as router:
        router.get(_url("cs.AI")).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            ArxivSource("cs.AI").fetch()
