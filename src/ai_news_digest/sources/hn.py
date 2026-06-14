"""Hacker News source — Algolia HN Search API, AI-tagged stories.

Uses the public ``search_by_date`` endpoint (no API key, free) so we can
filter on a topic query plus a minimum points threshold in one request.
The engagement counts ride along in ``raw_text`` so the AI processor
can use them when scoring importance — HN isn't a 1차 소스 by itself,
but a story with 200 points and 100 comments is its own signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from .base import RawItem, Source

log = logging.getLogger(__name__)

_API_URL = "https://hn.algolia.com/api/v1/search_by_date"
_DEFAULT_KEYWORDS: tuple[str, ...] = (
    "AI", "LLM", "GPT", "Claude", "Gemini", "Anthropic", "OpenAI",
)
_DEFAULT_MIN_POINTS = 50
_DEFAULT_LIMIT = 30
_USER_AGENT = "ai-news-digest/0.1 (+https://github.com/ttaehee/ai-news-digest)"


class HnSource(Source):
    def __init__(
        self,
        name: str = "Hacker News",
        keywords: tuple[str, ...] = _DEFAULT_KEYWORDS,
        min_points: int = _DEFAULT_MIN_POINTS,
        limit: int = _DEFAULT_LIMIT,
        timeout: float = 10.0,
    ) -> None:
        self.name = name
        self.keywords = tuple(keywords)
        self.min_points = min_points
        self.limit = limit
        self.timeout = timeout

    def fetch(self) -> list[RawItem]:
        # Algolia treats query words as AND by default and doesn't honor a
        # boolean "OR". Pairing the keyword list as both `query` and
        # `optionalWords` makes every keyword optional → matches any document
        # containing at least one of them, ranked by how many match.
        resp = httpx.get(
            _API_URL,
            params={
                "tags": "story",
                "query": " ".join(self.keywords),
                "optionalWords": ",".join(self.keywords),
                "numericFilters": f"points>={self.min_points}",
                "hitsPerPage": self.limit,
            },
            timeout=self.timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        return [self._hit_to_item(h) for h in hits]

    def _hit_to_item(self, hit: dict) -> RawItem:
        title = (hit.get("title") or "").strip()
        url = (hit.get("url") or "").strip()
        if not url:
            object_id = hit.get("objectID") or ""
            url = f"https://news.ycombinator.com/item?id={object_id}"

        published_at: datetime | None = None
        ts = hit.get("created_at_i")
        if ts is not None:
            published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)

        points = hit.get("points") or 0
        num_comments = hit.get("num_comments") or 0
        raw_text = f"Hacker News story: {points} points, {num_comments} comments"
        story_text = (hit.get("story_text") or "").strip()
        if story_text:
            raw_text = f"{raw_text}\n\n{story_text}"

        return RawItem(
            title=title,
            url=url,
            source=self.name,
            published_at=published_at,
            raw_text=raw_text,
        )
