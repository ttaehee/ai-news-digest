"""Cross-source normalization: time-window filter and lightweight text cleanup.

The collection stage already returns a unified `RawItem` shape; this stage
trims that input to what the AI processor should see:

* Drops items without a usable `published_at` (sources that omit dates are
  excluded conservatively — they are also a frequent vector for noise).
* Drops items older than `now - window_hours` (default 26h, sized to absorb
  GitHub Actions cron jitter; see PLAN §4).
* Strips HTML tags and collapses whitespace in `title` and `raw_text` so the
  downstream prompt sees clean text.

Items are returned in input order. Naive datetimes are treated as UTC for
robustness; sources are expected to emit tz-aware UTC per the `RawItem`
contract.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from .sources.base import RawItem

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

DEFAULT_WINDOW_HOURS = 26


def normalize(
    items: list[RawItem],
    window_hours: int = DEFAULT_WINDOW_HOURS,
    now: datetime | None = None,
) -> list[RawItem]:
    """Apply time-window filter + text cleanup to a flat list of raw items.

    `now` is injectable for deterministic tests; in production the pipeline
    passes ``datetime.now(timezone.utc)``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("normalize() requires a timezone-aware `now`")

    cutoff = now - timedelta(hours=window_hours)

    out: list[RawItem] = []
    for item in items:
        if item.published_at is None:
            continue
        published = _ensure_utc(item.published_at)
        if published < cutoff:
            continue
        out.append(
            RawItem(
                title=_clean_text(item.title),
                url=item.url,
                source=item.source,
                published_at=published,
                raw_text=_clean_text(item.raw_text),
            )
        )
    return out


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    no_tags = _HTML_TAG.sub(" ", text)
    unescaped = html.unescape(no_tags)
    return _WHITESPACE.sub(" ", unescaped).strip()
