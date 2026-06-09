"""Unit tests for the normalization stage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_news_digest.normalize import DEFAULT_WINDOW_HOURS, normalize
from ai_news_digest.sources.base import RawItem


NOW = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)


def _item(
    *,
    title: str = "T",
    url: str = "https://example.com/a",
    source: str = "Example",
    published_at: datetime | None = NOW,
    raw_text: str = "body",
) -> RawItem:
    return RawItem(
        title=title,
        url=url,
        source=source,
        published_at=published_at,
        raw_text=raw_text,
    )


def test_keeps_items_inside_window():
    items = [
        _item(published_at=NOW - timedelta(hours=1)),
        _item(published_at=NOW - timedelta(hours=25)),
    ]
    out = normalize(items, window_hours=26, now=NOW)
    assert len(out) == 2


def test_drops_items_outside_window():
    items = [
        _item(published_at=NOW - timedelta(hours=27)),
        _item(published_at=NOW - timedelta(days=30)),
    ]
    assert normalize(items, window_hours=26, now=NOW) == []


def test_boundary_at_cutoff_is_inclusive():
    cutoff_item = _item(published_at=NOW - timedelta(hours=26))
    just_before_cutoff = _item(
        published_at=NOW - timedelta(hours=26, seconds=1)
    )
    out = normalize([cutoff_item, just_before_cutoff], window_hours=26, now=NOW)
    assert len(out) == 1
    assert out[0] is not just_before_cutoff  # they get rebuilt; identity differs


def test_drops_dateless_items():
    items = [
        _item(published_at=None, title="dateless"),
        _item(published_at=NOW),
    ]
    out = normalize(items, now=NOW)
    assert len(out) == 1
    assert out[0].title == "T"


def test_strips_html_from_title_and_raw_text():
    item = _item(
        title="<b>Big</b> news",
        raw_text='<p>Hello <a href="x">world</a></p>',
    )
    out = normalize([item], now=NOW)
    assert out[0].title == "Big news"
    assert out[0].raw_text == "Hello world"


def test_unescapes_html_entities():
    item = _item(raw_text="Tom &amp; Jerry &lt;3")
    out = normalize([item], now=NOW)
    assert out[0].raw_text == "Tom & Jerry <3"


def test_collapses_whitespace():
    item = _item(
        title="lots   of\n\twhitespace",
        raw_text="line1\n\n\nline2   line3",
    )
    out = normalize([item], now=NOW)
    assert out[0].title == "lots of whitespace"
    assert out[0].raw_text == "line1 line2 line3"


def test_preserves_url_unchanged():
    item = _item(url="https://example.com/path?a=1&b=2")
    out = normalize([item], now=NOW)
    assert out[0].url == "https://example.com/path?a=1&b=2"


def test_input_order_preserved():
    items = [
        _item(title="first", published_at=NOW - timedelta(hours=2)),
        _item(title="second", published_at=NOW - timedelta(hours=20)),
        _item(title="third", published_at=NOW - timedelta(hours=10)),
    ]
    out = normalize(items, now=NOW)
    assert [i.title for i in out] == ["first", "second", "third"]


def test_naive_published_at_treated_as_utc():
    naive = datetime(2026, 6, 9, 11, 0, 0)  # 1h before NOW, no tzinfo
    item = _item(published_at=naive)
    out = normalize([item], now=NOW)
    assert len(out) == 1
    assert out[0].published_at.tzinfo is timezone.utc


def test_non_utc_published_at_converted_to_utc():
    other_tz = timezone(timedelta(hours=9))
    # 21:00 KST = 12:00 UTC = NOW; inside the 26h window
    item = _item(published_at=datetime(2026, 6, 9, 21, 0, 0, tzinfo=other_tz))
    out = normalize([item], now=NOW)
    assert len(out) == 1
    assert out[0].published_at == NOW


def test_default_window_is_26_hours():
    assert DEFAULT_WINDOW_HOURS == 26
    item_25h = _item(published_at=NOW - timedelta(hours=25))
    item_27h = _item(published_at=NOW - timedelta(hours=27))
    out = normalize([item_25h, item_27h], now=NOW)
    assert len(out) == 1


def test_empty_input_returns_empty():
    assert normalize([], now=NOW) == []


def test_raises_when_now_is_naive():
    with pytest.raises(ValueError):
        normalize([_item()], now=datetime(2026, 6, 9, 12, 0, 0))


def test_empty_text_fields_pass_through_clean():
    item = _item(title="", raw_text="")
    out = normalize([item], now=NOW)
    assert out[0].title == ""
    assert out[0].raw_text == ""
