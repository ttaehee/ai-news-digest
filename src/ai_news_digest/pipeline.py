"""Pipeline orchestration: collect → normalize → AI process → deliver.

Per-source isolation runs fetches in a thread pool so one slow / broken
feed cannot stall the others. Single-source failures are caught, logged,
and surfaced to the renderer as ``(일부 소스 실패: …)``.

The self-check (PLAN §3 "검증 루프"):
* zero normalized items → skip AI call and skip delivery, return cleanly
* fallback Digest (AI exhausted retries) → still delivered so the renderer
  can show the warning footer + raw-link dump

Dependencies are injected so tests don't touch network, SDK, or stdout.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .ai_processor import Digest, process
from .delivery.base import Sender
from .normalize import normalize
from .providers.base import LLMProvider
from .sources.base import RawItem, Source

log = logging.getLogger(__name__)

DEFAULT_FETCH_WORKERS = 8


@dataclass
class RunResult:
    raw_count: int
    normalized_count: int
    failed_sources: list[str] = field(default_factory=list)
    digest: Digest | None = None
    sent: bool = False
    elapsed_total_s: float = 0.0


def run(
    sources: list[Source],
    provider: LLMProvider,
    sender: Sender,
    *,
    window_hours: int = 26,
    now: datetime | None = None,
    fetch_workers: int = DEFAULT_FETCH_WORKERS,
) -> RunResult:
    """Run one full digest pass."""
    started = time.monotonic()
    now = now or datetime.now(timezone.utc)

    raw, failed = _collect(sources, fetch_workers)
    log.info("collect: %d raw items from %d sources (%d failed)", len(raw), len(sources), len(failed))

    items = normalize(raw, window_hours=window_hours, now=now)
    log.info("normalize: %d items kept after %dh window", len(items), window_hours)

    if not items:
        log.warning("self-check: 0 items after normalize — skipping AI and delivery")
        return RunResult(
            raw_count=len(raw),
            normalized_count=0,
            failed_sources=failed,
            elapsed_total_s=time.monotonic() - started,
        )

    ai_started = time.monotonic()
    digest = process(items, provider=provider)
    log.info(
        "ai_processor: %d items in digest (fallback=%s, %.2fs, provider=%s, model=%s)",
        digest.total_items(),
        digest.fallback,
        time.monotonic() - ai_started,
        provider.name,
        provider.model,
    )

    sender.send(digest, run_at=now, failed_sources=failed)
    log.info("deliver: %s sent (sources failed: %s)", type(sender).__name__, failed or "none")

    return RunResult(
        raw_count=len(raw),
        normalized_count=len(items),
        failed_sources=failed,
        digest=digest,
        sent=True,
        elapsed_total_s=time.monotonic() - started,
    )


def _collect(sources: list[Source], workers: int) -> tuple[list[RawItem], list[str]]:
    """Fetch every source in parallel; isolate per-source failures."""
    raw: list[RawItem] = []
    failed: list[str] = []
    if not sources:
        return raw, failed

    with ThreadPoolExecutor(max_workers=min(workers, len(sources))) as executor:
        futures = {executor.submit(_fetch_one, src): src for src in sources}
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                items, elapsed_ms = fut.result()
            except Exception as e:
                log.warning("collect: %s FAILED — %s: %s", src.name, type(e).__name__, e)
                failed.append(src.name)
                continue
            log.info("collect: %s — %d items in %dms", src.name, len(items), elapsed_ms)
            raw.extend(items)
    return raw, failed


def _fetch_one(src: Source) -> tuple[list[RawItem], int]:
    start = time.monotonic()
    items = src.fetch()
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return items, elapsed_ms
