"""Source plugin interface and the unified raw-item shape."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawItem:
    """One item as fetched from a source, before any cross-source normalization.

    `published_at` is timezone-aware UTC, or None when the source omits a date.
    Items with None `published_at` will be dropped at the time-window stage.
    """

    title: str
    url: str
    source: str
    published_at: datetime | None
    raw_text: str


class Source(ABC):
    """Plugin contract. A Source knows its name and how to fetch its current items."""

    name: str

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        """Fetch all currently available items from this source.

        Implementations must use a timeout on every network call and let
        exceptions propagate; the pipeline isolates failures per source.
        """
