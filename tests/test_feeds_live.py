"""Live network checks for every registered source.

Marked `network`; deselected by default. Run explicitly with:

    pytest -m network

Mirrors what scripts/check_feeds.py does, parameterized per source so failures
identify the specific source. Polymorphic over Source.fetch() so RSS, arXiv,
HN, and any future source type are all covered without per-backend branching.
"""

from __future__ import annotations

import time

import pytest

from ai_news_digest.sources.base import Source
from ai_news_digest.sources.registry import DEFAULT_SOURCES

_RETRY_BACKOFFS_S = (2.0, 4.0)  # waits between attempts; total attempts = len + 1


def _fetch_with_retry(src: Source):
    last_exc: Exception | None = None
    for wait in (*_RETRY_BACKOFFS_S, None):
        try:
            return src.fetch()
        except Exception as e:
            last_exc = e
        if wait is not None:
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


@pytest.mark.network
@pytest.mark.parametrize("src", DEFAULT_SOURCES, ids=lambda s: s.name)
def test_source_alive(src: Source) -> None:
    items = _fetch_with_retry(src)
    assert len(items) > 0, f"{src.name}: returned 0 items"
