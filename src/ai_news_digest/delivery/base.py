"""Sender plugin interface — one channel per implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..ai_processor import Digest


class Sender(ABC):
    """Ship a `Digest` to one delivery channel.

    `run_at` and `failed_sources` are runtime context the pipeline collects;
    they are passed at send time (not construction time) so the same sender
    instance can be reused across runs in principle.
    """

    @abstractmethod
    def send(
        self,
        digest: Digest,
        *,
        run_at: datetime | None = None,
        failed_sources: list[str] | None = None,
    ) -> None: ...
