"""MCP server exposing the collect+filter stage of ai-news-digest.

This server intentionally does NOT call any LLM. It reuses the batch
pipeline's source collection and time-window normalization, applies a
deterministic per-category source filter (Community = Hacker News,
Paper = arXiv, Model/Tool/Misc = primary blogs), and bundles the items
with the existing ``SYSTEM_PROMPT`` into a single text payload. The host
Claude (Desktop or CLI) does the summarization, classification, and
importance scoring.

That split is why no API key is needed here and why ``providers/`` is not
imported. The batch path (``pipeline.run``) is untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from .ai_processor import SYSTEM_PROMPT
from .normalize import normalize
from .pipeline import DEFAULT_FETCH_WORKERS, _collect
from .sources.base import RawItem
from .sources.registry import COMMUNITY_SOURCES, DEFAULT_SOURCES

# Canonical category names match ai_processor.CATEGORIES exactly.
_CANONICAL_CATEGORIES: frozenset[str] = frozenset(
    {"Model", "Paper", "Tool", "Misc", "Community"}
)
# Lower-cased alias → canonical English. English canonicals also work directly.
_CATEGORY_ALIASES: dict[str, str] = {
    "모델": "Model",
    "논문": "Paper",
    "툴": "Tool",
    "기타": "Misc",
    "커뮤니티": "Community",
}
# Inputs that mean "no category filter".
_ALL_ALIASES: frozenset[str] = frozenset({"", "전체", "all"})

TOP_K_MIN, TOP_K_MAX = 1, 25
HOURS_MIN, HOURS_MAX = 1, 336


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _resolve_category(category: str | None) -> str | None:
    """Normalize a user-supplied category to the canonical English name.

    Returns None when the input means "all categories" (None, empty string,
    '전체', 'all'). Raises ValueError on any other unrecognized value so
    the host can surface the mistake to the user.
    """
    if category is None:
        return None
    key = category.strip().lower()
    if key in _ALL_ALIASES:
        return None
    for canon in _CANONICAL_CATEGORIES:
        if key == canon.lower():
            return canon
    for alias, canon in _CATEGORY_ALIASES.items():
        if key == alias.lower():
            return canon
    raise ValueError(
        f"unknown category: {category!r} "
        f"(use Model/Paper/Tool/Misc/Community, the Korean aliases "
        f"모델/논문/툴/기타/커뮤니티, or '전체' / omit)"
    )


def _filter_by_category(items: list[RawItem], category: str | None) -> list[RawItem]:
    """Server-side coarse filter by ``source``. Host Claude does precise
    classification for Model/Tool/Misc because that needs body comprehension.

    * Community → any source in ``COMMUNITY_SOURCES`` (HN, GeekNews, …)
    * Paper → arXiv only (any cs.* category)
    * Model / Tool / Misc → primary blogs only (drops community + arXiv);
      the host picks the right bucket per item based on body content
    * None → pass everything through
    """
    if category is None:
        return items
    if category == "Community":
        return [i for i in items if i.source in COMMUNITY_SOURCES]
    if category == "Paper":
        return [i for i in items if i.source.startswith("arXiv")]
    # Model / Tool / Misc share the primary-blog pool.
    return [
        i
        for i in items
        if i.source not in COMMUNITY_SOURCES and not i.source.startswith("arXiv")
    ]


def _render_payload(
    items: list[RawItem],
    *,
    category: str | None,
    top_k: int,
    hours: int,
    failed_sources: list[str],
    refine: bool = False,
) -> str:
    """Compose the instruction + SYSTEM_PROMPT + items into one string."""
    cat_label = category or "전체"
    failed_label = ", ".join(failed_sources) if failed_sources else "없음"

    instruction = (
        "아래 원문 항목들을 다음 기준에 따라 요약·분류하고 카테고리별 중요도 점수를 매겨라.\n"
        f"카테고리당 최대 {top_k}개, 한국어 한 줄 요약, 0–10 importance 점수와 함께 제시한다."
    )

    conditions = (
        "# 조건\n"
        f"- 사용자 요청 카테고리: {cat_label}\n"
        f"- 시간창: 최근 {hours}시간\n"
        f"- 카테고리당 상한: top_k = {top_k}\n"
        f"- 소스 실패: {failed_label}"
    )

    parts: list[str] = [
        instruction,
        "",
        "# 기준 (SYSTEM_PROMPT)",
        SYSTEM_PROMPT,
        "",
        conditions,
        "",
        f"# 데이터 ({len(items)}개 항목)",
    ]

    for n, item in enumerate(items, 1):
        ts = item.published_at.isoformat() if item.published_at else "no-date"
        parts.append("")
        parts.append(f"## [{n}] {item.source} · {ts}")
        parts.append(f"title: {item.title}")
        parts.append(f"url: {item.url}")
        if item.raw_text:
            parts.append(f"raw_text: {item.raw_text}")

    if refine:
        parts.append("")
        parts.append("# 자가 개선 (refine)")
        parts.append(
            "요약을 작성한 뒤, 위 SYSTEM_PROMPT의 summary_kr 규칙과 같은 기준"
            "(금지어·전문용어·제목 번역·길이)으로 스스로 채점하라. 미달 항목은"
            " 재작성하고, 최종 결과만 반환한다."
        )

    return "\n".join(parts)


mcp = FastMCP("ai-news-digest")


@mcp.tool()
def get_ai_digest(
    category: str | None = None,
    top_k: int = 3,
    hours: int = 24,
    refine: bool = False,
) -> str:
    """Collect AI news items, filter by time window and category, and return
    a single text payload the host LLM can summarize.

    The server does no LLM work — it gathers items and bundles them with
    the project's existing SYSTEM_PROMPT so the host applies the same
    rules the batch pipeline does.

    Args:
        category: 'Model' / 'Paper' / 'Tool' / 'Misc' / 'Community', or the
            Korean aliases '모델' / '논문' / '툴' / '기타' / '커뮤니티'.
            Omit or pass '전체' / 'all' / '' for all categories.
        top_k: Items per category the host should keep (clamped to 1–25,
            default 3). The host enforces this against SYSTEM_PROMPT.
        hours: Time window in hours (clamped to 1–336, default 24).
        refine: When True, append a self-improvement instruction telling the
            host to re-score its summaries against the SYSTEM_PROMPT rules
            (banned words, jargon, title translation, length) and rewrite
            anything that fails. Default False to keep the host's output
            tokens single-pass.

    Returns:
        A single string containing the host instruction, the embedded
        SYSTEM_PROMPT, the run conditions, and the raw items.
    """
    canon = _resolve_category(category)
    top_k = _clamp(top_k, TOP_K_MIN, TOP_K_MAX)
    hours = _clamp(hours, HOURS_MIN, HOURS_MAX)

    raw, failed = _collect(DEFAULT_SOURCES, DEFAULT_FETCH_WORKERS)
    items = normalize(raw, window_hours=hours, now=datetime.now(timezone.utc))
    items = _filter_by_category(items, canon)

    if not items:
        cat_label = canon or "전체"
        return (
            f"해당 조건의 뉴스가 없습니다 "
            f"(카테고리: {cat_label}, 최근 {hours}시간)."
        )

    return _render_payload(
        items,
        category=canon,
        top_k=top_k,
        hours=hours,
        failed_sources=failed,
        refine=refine,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
