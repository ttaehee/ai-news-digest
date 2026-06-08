"""Generic RSS / Atom source backed by httpx + feedparser."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import struct_time

import feedparser
import httpx
from dateutil import parser as date_parser

from .base import RawItem, Source

log = logging.getLogger(__name__)

_USER_AGENT = "ai-news-digest/0.1 (+https://github.com/ttaehee/ai-news-digest)"


class RSSSource(Source):
    def __init__(self, name: str, url: str, timeout: float = 10.0) -> None:
        self.name = name
        self.url = url
        self.timeout = timeout

    def fetch(self) -> list[RawItem]:
        resp = httpx.get(
            self.url,
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()

        parsed = feedparser.parse(resp.content)
        items: list[RawItem] = []
        for entry in parsed.entries:
            items.append(self._entry_to_item(entry))
        return items

    def _entry_to_item(self, entry: dict) -> RawItem:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        published_at = self._extract_date(entry)
        raw_text = (entry.get("summary") or entry.get("description") or "").strip()
        return RawItem(
            title=title,
            url=url,
            source=self.name,
            published_at=published_at,
            raw_text=raw_text,
        )

    @staticmethod
    def _extract_date(entry: dict) -> datetime | None:
        for key in ("published_parsed", "updated_parsed"):
            t: struct_time | None = entry.get(key)
            if t:
                return datetime(*t[:6], tzinfo=timezone.utc)
        for key in ("published", "updated"):
            raw = entry.get(key)
            if raw:
                try:
                    dt = date_parser.parse(raw)
                except (ValueError, TypeError):
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
        return None
