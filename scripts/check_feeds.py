#!/usr/bin/env python3
"""Live health-check for every registered feed.

Hits each source in ai_news_digest.sources.registry.DEFAULT_SOURCES with a real
HTTP request, parses the body with feedparser, and prints a table:

    source | HTTP | kind | items | latest     | status

Exits 1 if any source returns non-200, fails to parse, or yields zero entries.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

import feedparser
import httpx

from ai_news_digest.sources.registry import DEFAULT_SOURCES
from ai_news_digest.sources.rss import RSSSource

_USER_AGENT = "ai-news-digest-feedcheck/0.1"
_TIMEOUT = 20.0
_RETRY_BACKOFFS_S = (2.0, 4.0)  # waits between attempts; total attempts = len + 1


def _detect_kind(body: bytes) -> str:
    head = body[:2000].lower()
    if b"<rss" in head:
        return "RSS"
    if b"<feed" in head:
        return "Atom"
    return "?"


def _latest_date(parsed) -> str:
    latest: datetime | None = None
    for entry in parsed.entries:
        for key in ("published_parsed", "updated_parsed"):
            t = entry.get(key)
            if t:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                if latest is None or dt > latest:
                    latest = dt
                break
    return latest.strftime("%Y-%m-%d") if latest else "no-date"


def _get_with_retries(url: str) -> httpx.Response:
    """GET with backoff retries — absorbs transient WAF/rate-limit/slow-host blips."""
    last_exc: Exception | None = None
    backoffs = (*_RETRY_BACKOFFS_S, None)  # None marks "no sleep after last attempt"
    for wait in backoffs:
        try:
            resp = httpx.get(
                url,
                timeout=_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            if resp.status_code == 200:
                return resp
            last_exc = httpx.HTTPStatusError(
                f"status {resp.status_code}", request=resp.request, response=resp
            )
        except httpx.HTTPError as e:
            last_exc = e
        if wait is not None:
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def check_one(name: str, url: str) -> tuple[str, str, str, str, str, str]:
    try:
        resp = _get_with_retries(url)
    except httpx.HTTPStatusError as e:
        return (name, str(e.response.status_code), "?", "?", "?", "FAIL: non-200")
    except httpx.HTTPError as e:
        return (name, "ERR", "?", "?", "?", f"FAIL: {type(e).__name__}")

    status = str(resp.status_code)

    kind = _detect_kind(resp.content)
    parsed = feedparser.parse(resp.content)
    n = len(parsed.entries)
    if n == 0:
        return (name, status, kind, "0", "no-date", "FAIL: 0 entries")

    return (name, status, kind, str(n), _latest_date(parsed), "OK")


def main() -> int:
    rows: list[tuple[str, str, str, str, str, str]] = []
    failed = 0
    for src in DEFAULT_SOURCES:
        if not isinstance(src, RSSSource):
            continue
        row = check_one(src.name, src.url)
        if not row[5].startswith("OK"):
            failed += 1
        rows.append(row)

    if not rows:
        print("no RSS sources registered", file=sys.stderr)
        return 1

    name_w = max(len(r[0]) for r in rows)
    fmt = f"{{:<{name_w}}} | {{:>4}} | {{:<4}} | {{:>5}} | {{:<10}} | {{}}"
    header = fmt.format("source", "HTTP", "kind", "items", "latest", "status")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(fmt.format(*r))

    if failed:
        print(f"\n{failed} feed(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nAll {len(rows)} feeds OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
