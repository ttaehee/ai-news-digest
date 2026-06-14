"""Plain-text renderer for a `Digest`. Shared by ConsoleSender and SlackSender.

Output format:

* Header: ``AI 뉴스 다이제스트 — YYYY-MM-DD (KST)``
* Per non-empty category: section heading, then for each item one line:
  ``- 제목 — 요약 (출처) · URL`` (when summary present)
  ``- 제목 (출처) · URL`` (when summary empty, e.g. fallback dump)
* Optional notes line.
* Optional footer ``(일부 소스 실패: …)``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from .ai_processor import CATEGORIES, Digest
from .eval import DigestScore
from .eval.constants import QUALITY_PASS_THRESHOLD

KST = timezone(timedelta(hours=9))


def render_text(
    digest: Digest,
    *,
    run_at: datetime | None = None,
    failed_sources: Iterable[str] | None = None,
    score: DigestScore | None = None,
) -> str:
    if run_at is None:
        run_at = datetime.now(timezone.utc)
    elif run_at.tzinfo is None:
        raise ValueError("render_text requires tz-aware `run_at`")

    date_kst = run_at.astimezone(KST).strftime("%Y-%m-%d")
    lines: list[str] = [f"AI 뉴스 다이제스트 — {date_kst} (KST)", ""]

    if digest.fallback:
        lines.append("⚠ 모델 처리 실패: 원본 링크 덤프(폴백) 모드")
        lines.append("")

    any_items = False
    for cat in CATEGORIES:
        items = digest.categories.get(cat, ())
        if not items:
            continue
        any_items = True
        lines.append(f"# {cat}")
        for it in items:
            if it.summary_kr:
                lines.append(f"- {it.title} — {it.summary_kr} ({it.source}) · {it.url}")
            else:
                lines.append(f"- {it.title} ({it.source}) · {it.url}")
        lines.append("")

    if not any_items:
        lines.append("(다이제스트에 포함할 항목 없음)")
        lines.append("")

    if digest.notes:
        lines.append(f"메모: {digest.notes}")
        lines.append("")

    if score is not None and score.total > 0:
        pct = round(score.pass_rate * 100)
        below = score.pass_rate < QUALITY_PASS_THRESHOLD
        emoji = "⚠️" if below else "📊"
        body = f"{score.passed_count}/{score.total} 통과 ({pct}%)"
        suffix = (
            f" — 기준 {round(QUALITY_PASS_THRESHOLD * 100)}% 미달" if below else ""
        )
        lines.append(f"{emoji} 요약 품질: {body}{suffix}")

    failed = list(failed_sources or [])
    if failed:
        lines.append(f"(일부 소스 실패: {', '.join(failed)})")

    return "\n".join(lines).rstrip() + "\n"
