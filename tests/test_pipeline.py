"""Unit tests for pipeline.run — sources, provider, and sender are stubbed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from ai_news_digest.ai_processor import CATEGORIES, Digest, DigestItem
from ai_news_digest.pipeline import run
from ai_news_digest.providers.base import LLMProvider
from ai_news_digest.sources.base import RawItem, Source


NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _item(title="t", url="https://e/x", source="Src", offset_hours=1) -> RawItem:
    return RawItem(
        title=title,
        url=url,
        source=source,
        published_at=NOW - timedelta(hours=offset_hours),
        raw_text="body",
    )


class FakeSource(Source):
    def __init__(self, name: str, items=None, raises=None):
        self.name = name
        self._items = items or []
        self._raises = raises

    def fetch(self):
        if self._raises:
            raise self._raises
        return list(self._items)


class FakeProvider(LLMProvider):
    name = "fake"
    model = "fake-1"

    def __init__(self, payload: dict | None = None):
        self._payload = payload or {
            "categories": {c: [] for c in CATEGORIES},
        }

    def emit_digest(self, items):
        return self._payload


def _make_sender():
    sender = MagicMock()
    return sender


# ---------------------------------------------------------------------------


def test_collects_from_all_sources_and_passes_to_ai():
    a = FakeSource("A", items=[_item(title="a1", url="https://e/a1")])
    b = FakeSource("B", items=[_item(title="b1", url="https://e/b1")])
    provider = FakeProvider(
        payload={
            "categories": {
                "모델출시": [
                    {
                        "title": "merged",
                        "url": "https://e/a1",
                        "source": "Src",
                        "importance": 8,
                        "summary_kr": "간결 한 줄",
                    }
                ],
                "논문": [], "툴": [], "기타": [],
            }
        }
    )
    sender = _make_sender()

    result = run([a, b], provider, sender, now=NOW)

    assert result.raw_count == 2
    assert result.normalized_count == 2
    assert result.failed_sources == []
    assert result.sent is True
    sender.send.assert_called_once()
    sent_digest = sender.send.call_args.args[0]
    assert isinstance(sent_digest, Digest)
    assert len(sent_digest.categories["모델출시"]) == 1


def test_isolates_per_source_failures():
    healthy = FakeSource("healthy", items=[_item()])
    broken = FakeSource("broken", raises=RuntimeError("boom"))

    result = run([healthy, broken], FakeProvider(), _make_sender(), now=NOW)

    assert result.failed_sources == ["broken"]
    assert result.raw_count == 1
    assert result.sent is True


def test_zero_items_after_normalize_skips_ai_and_sender():
    # both sources return only items outside the 26h window
    stale = FakeSource("stale", items=[_item(offset_hours=200)])
    sender = _make_sender()
    provider = MagicMock(spec=LLMProvider)
    provider.name = "fake"
    provider.model = "fake-1"

    result = run([stale], provider, sender, now=NOW)

    assert result.normalized_count == 0
    assert result.sent is False
    assert result.digest is None
    provider.emit_digest.assert_not_called()
    sender.send.assert_not_called()


def test_zero_sources_also_short_circuits():
    sender = _make_sender()
    provider = MagicMock(spec=LLMProvider)
    provider.name = "fake"; provider.model = "fake-1"

    result = run([], provider, sender, now=NOW)
    assert result.raw_count == 0
    assert result.normalized_count == 0
    assert result.sent is False
    sender.send.assert_not_called()


def test_failed_sources_forwarded_to_sender():
    healthy = FakeSource("ok", items=[_item()])
    broken = FakeSource("broken", raises=RuntimeError("x"))

    sender = _make_sender()
    run([healthy, broken], FakeProvider(), sender, now=NOW)

    kwargs = sender.send.call_args.kwargs
    assert kwargs["failed_sources"] == ["broken"]


def test_now_propagated_to_sender():
    src = FakeSource("ok", items=[_item()])
    sender = _make_sender()
    run([src], FakeProvider(), sender, now=NOW)
    assert sender.send.call_args.kwargs["run_at"] == NOW


def test_window_hours_param_filters_items():
    src = FakeSource("ok", items=[_item(offset_hours=15)])
    sender = _make_sender()

    # window 10h → 15h-old item is dropped → no send
    r1 = run([src], FakeProvider(), sender, window_hours=10, now=NOW)
    assert r1.normalized_count == 0
    sender.send.assert_not_called()

    # window 30h → 15h-old item kept → send happens
    sender2 = _make_sender()
    r2 = run([src], FakeProvider(), sender2, window_hours=30, now=NOW)
    assert r2.normalized_count == 1
    sender2.send.assert_called_once()


def test_fallback_digest_still_delivered():
    src = FakeSource("ok", items=[_item()])

    class BadProvider(LLMProvider):
        name = "bad"; model = "bad-1"
        def emit_digest(self, items):
            raise RuntimeError("nope")

    sender = _make_sender()
    result = run([src], BadProvider(), sender, now=NOW)

    assert result.digest is not None
    assert result.digest.fallback is True
    sender.send.assert_called_once()


def test_returns_elapsed_total_seconds():
    src = FakeSource("ok", items=[_item()])
    result = run([src], FakeProvider(), _make_sender(), now=NOW)
    assert result.elapsed_total_s >= 0
