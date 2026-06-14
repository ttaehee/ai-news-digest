#!/usr/bin/env python3
"""Live health-check for every registered source.

Calls each Source's own ``fetch()`` polymorphically so RSS, arXiv, HN, and
any future source type all go through the same check without needing
special-cases per backend. Prints:

    source | items | latest     | status

Exits 1 if any source fails to fetch or returns zero items.
"""

from __future__ import annotations

import sys
import time

from ai_news_digest.sources.base import RawItem, Source
from ai_news_digest.sources.registry import DEFAULT_SOURCES

_RETRY_BACKOFFS_S = (2.0, 4.0)  # waits between attempts; total attempts = len + 1


def _fetch_with_retry(src: Source) -> list[RawItem]:
    """Call ``src.fetch()`` with backoff retries — absorbs transient blips."""
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


def _latest_date(items: list[RawItem]) -> str:
    dates = [i.published_at for i in items if i.published_at is not None]
    return max(dates).strftime("%Y-%m-%d") if dates else "no-date"


def check_one(src: Source) -> tuple[str, str, str, str]:
    try:
        items = _fetch_with_retry(src)
    except Exception as e:
        return (src.name, "ERR", "-", f"FAIL: {type(e).__name__}")
    if not items:
        return (src.name, "0", "no-date", "FAIL: 0 items")
    return (src.name, str(len(items)), _latest_date(items), "OK")


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []
    failed = 0
    for src in DEFAULT_SOURCES:
        row = check_one(src)
        if not row[3].startswith("OK"):
            failed += 1
        rows.append(row)

    if not rows:
        print("no sources registered", file=sys.stderr)
        return 1

    name_w = max(len(r[0]) for r in rows)
    fmt = f"{{:<{name_w}}} | {{:>5}} | {{:<10}} | {{}}"
    header = fmt.format("source", "items", "latest", "status")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(fmt.format(*r))

    if failed:
        print(f"\n{failed} source(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nAll {len(rows)} sources OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
