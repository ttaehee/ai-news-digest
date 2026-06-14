"""Slack sender — POSTs the rendered digest to an Incoming Webhook.

Uses Slack mrkdwn (``*bold*`` for category headers, ``<url|text>`` for
clickable title links). The plain-text console renderer in render.py is
left untouched so the two channels can drift independently.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

import httpx

from ..ai_processor import CATEGORIES, Digest
from ..eval import DigestScore
from ..eval.constants import QUALITY_PASS_THRESHOLD
from .base import Sender

log = logging.getLogger(__name__)

_TIMEOUT_S = 10.0
_KST = timezone(timedelta(hours=9))
_BULLET = "•"
_CATEGORY_EMOJI: dict[str, str] = {
    "Model":     "🌵",
    "Paper":     "📖",
    "Tool":      "🍄‍🟫",
    "Misc":      "🌿",
    "Community": "🍊",
}


def _render_slack(
    digest: Digest,
    *,
    run_at: datetime | None = None,
    failed_sources: Iterable[str] | None = None,
    score: DigestScore | None = None,
) -> str:
    """Render the digest as Slack mrkdwn — one item per line, ``*bold*``
    category headers, clickable ``<url|title>`` links, blank line between
    categories.
    """
    if run_at is None:
        run_at = datetime.now(timezone.utc)
    elif run_at.tzinfo is None:
        raise ValueError("_render_slack requires tz-aware `run_at`")

    date_kst = run_at.astimezone(_KST).strftime("%Y-%m-%d")
    parts: list[str] = [f"AI 뉴스 다이제스트 — {date_kst} (KST)", ""]

    if digest.fallback:
        parts.append("⚠ 모델 처리 실패: 원본 링크 덤프(폴백) 모드")
        parts.append("")

    any_items = False
    for cat in CATEGORIES:
        items = digest.categories.get(cat, ())
        if not items:
            continue
        any_items = True
        emoji = _CATEGORY_EMOJI.get(cat, "")
        parts.append(f"{emoji} *{cat}*" if emoji else f"*{cat}*")
        for it in items:
            link = f"<{it.url}|{it.title}>" if it.url else it.title
            if it.summary_kr:
                parts.append(f"{_BULLET} {link} — {it.summary_kr} ({it.source})")
            else:
                parts.append(f"{_BULLET} {link} ({it.source})")
        parts.append("")

    if not any_items:
        parts.append("(다이제스트에 포함할 항목 없음)")
        parts.append("")

    if digest.notes:
        parts.append(f"메모: {digest.notes}")
        parts.append("")

    if score is not None and score.total > 0:
        pct = round(score.pass_rate * 100)
        below = score.pass_rate < QUALITY_PASS_THRESHOLD
        emoji = "⚠️" if below else "📊"
        body = f"{score.passed_count}/{score.total} 통과 ({pct}%)"
        suffix = (
            f" — 기준 {round(QUALITY_PASS_THRESHOLD * 100)}% 미달" if below else ""
        )
        parts.append(f"{emoji} *요약 품질*: {body}{suffix}")

    failed = list(failed_sources or [])
    if failed:
        parts.append(f"(일부 소스 실패: {', '.join(failed)})")

    return "\n".join(parts).rstrip() + "\n"


class SlackSender(Sender):
    def __init__(self, webhook_url: str) -> None:
        if not webhook_url:
            raise ValueError("SlackSender requires a non-empty webhook URL")
        self.webhook_url = webhook_url

    def send(
        self,
        digest: Digest,
        *,
        run_at: datetime | None = None,
        failed_sources: list[str] | None = None,
        score: DigestScore | None = None,
    ) -> None:
        body = _render_slack(
            digest, run_at=run_at, failed_sources=failed_sources, score=score
        )
        try:
            resp = httpx.post(
                self.webhook_url,
                json={"text": body},
                timeout=_TIMEOUT_S,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.error("Slack POST failed: %s: %s", type(e).__name__, e)
            raise
