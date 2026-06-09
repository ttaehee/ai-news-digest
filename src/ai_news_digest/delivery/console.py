"""Console sender — renders to text and writes to a stream (stdout by default).

This is the default DRY_RUN path (PLAN §6): no external I/O, fully functional.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import IO

from ..ai_processor import Digest
from ..render import render_text
from .base import Sender


class ConsoleSender(Sender):
    """Write the rendered digest to ``stream`` (defaults to ``sys.stdout``)."""

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream = stream  # resolved lazily so sys.stdout patches still work

    def send(
        self,
        digest: Digest,
        *,
        run_at: datetime | None = None,
        failed_sources: list[str] | None = None,
    ) -> None:
        text = render_text(digest, run_at=run_at, failed_sources=failed_sources)
        out = self._stream if self._stream is not None else sys.stdout
        out.write(text)
        out.flush()
