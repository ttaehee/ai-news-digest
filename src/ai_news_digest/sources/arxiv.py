"""arXiv per-category source. Caps to the most-recent N items to bound input tokens."""

from __future__ import annotations

from .base import RawItem
from .rss import RSSSource

_BASE_URL = "https://export.arxiv.org/rss/{category}"
_DEFAULT_LIMIT = 30


class ArxivSource(RSSSource):
    """One arXiv category (e.g. ``cs.AI``). Slices to ``limit`` most-recent items.

    arXiv RSS lists submissions newest-first, so a simple slice gives us the
    top-N most recent. The cap exists to keep Claude input tokens bounded
    (PLAN §5).
    """

    def __init__(
        self,
        category: str,
        limit: int = _DEFAULT_LIMIT,
        timeout: float = 15.0,
    ) -> None:
        super().__init__(
            name=f"arXiv {category}",
            url=_BASE_URL.format(category=category),
            timeout=timeout,
        )
        self.category = category
        self.limit = limit

    def fetch(self) -> list[RawItem]:
        return super().fetch()[: self.limit]
