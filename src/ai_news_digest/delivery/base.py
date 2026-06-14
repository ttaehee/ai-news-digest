"""Sender plugin interface — one channel per implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..ai_processor import Digest
from ..eval import DigestScore


class Sender(ABC):
    """Ship a `Digest` to one delivery channel.

    `run_at`, `failed_sources`, and `score` are runtime context the pipeline
    collects; they're passed at send time (not construction time) so the same
    sender instance can be reused across runs in principle.
    """

    @abstractmethod
    def send(
        self,
        digest: Digest,
        *,
        run_at: datetime | None = None,
        failed_sources: list[str] | None = None,
        score: DigestScore | None = None,
    ) -> None: ...
