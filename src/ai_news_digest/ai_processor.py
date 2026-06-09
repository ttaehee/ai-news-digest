"""AI processing stage (PLAN §5): dedupe, categorize, score, summarize.

Calls Claude with a forced ``emit_digest`` tool — Anthropic has no
``response_format``, so tool-use is the structured-output mechanism
(AGENTS §4). On hard failure, falls back to a raw-link dump so the
pipeline can still ship.

The Claude call is reached through a single ``caller`` seam so tests
never touch the SDK.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .sources.base import RawItem

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SPLIT_THRESHOLD = 80         # > this many items triggers a halved-call
TOP_PER_CATEGORY = 5         # cap per category in the final digest
MAX_RAW_TEXT_CHARS = 1000    # raw_text truncation before sending to Claude
MAX_ATTEMPTS = 2             # 1 initial + 1 retry; then fallback

CATEGORIES: tuple[str, ...] = ("모델출시", "논문", "툴", "기타")


@dataclass(frozen=True)
class DigestItem:
    title: str
    url: str
    source: str
    importance: int                # 0–10
    summary_kr: tuple[str, str, str]  # exactly 3 lines


@dataclass(frozen=True)
class Digest:
    categories: dict[str, tuple[DigestItem, ...]]
    notes: str = ""
    fallback: bool = False        # True when raw-link dump path was used

    def total_items(self) -> int:
        return sum(len(v) for v in self.categories.values())


# --- emit_digest tool schema (forced) ------------------------------------

_DIGEST_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title":      {"type": "string"},
        "url":        {"type": "string"},
        "source":     {"type": "string"},
        "importance": {"type": "integer", "minimum": 0, "maximum": 10},
        "summary_kr": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
    },
    "required": ["title", "url", "source", "importance", "summary_kr"],
}

EMIT_DIGEST_TOOL: dict[str, Any] = {
    "name": "emit_digest",
    "description": (
        "Emit the final categorized digest. Call this exactly once. "
        "Group similar items into the most authoritative primary source, "
        "classify by category, score importance 0–10, and write a 3-line "
        "Korean summary per item. Return at most 5 items per category, "
        "ordered by descending importance."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "categories": {
                "type": "object",
                "properties": {cat: {"type": "array", "items": _DIGEST_ITEM_SCHEMA} for cat in CATEGORIES},
                "required": list(CATEGORIES),
            },
            "notes": {"type": "string"},
        },
        "required": ["categories"],
    },
}


SYSTEM_PROMPT = """\
당신은 한국어 AI 뉴스 다이제스트 큐레이터다.

규칙:
1. 사용자 입력에 정규화된 AI 뉴스 항목 목록이 JSON으로 들어온다.
2. emit_digest 도구를 정확히 한 번 호출해 다이제스트를 반환한다. 자연어 응답은 하지 않는다.
3. 같은 발표/논문/기사는 가장 권위 있는 1차 소스 1건으로 묶는다(중복 제거).
4. 카테고리:
   - 모델출시: 새로운 모델·주요 모델 업데이트·API 변경
   - 논문: 연구·논문·기술 보고서
   - 툴: 라이브러리·서비스·SDK·통합·플랫폼 발표
   - 기타: 위 셋에 명확히 안 맞는 의미 있는 AI 뉴스
5. importance는 0–10 정수. 우선순위:
   ① 업계 파급력(새 모델·주요 API 변경 등)
   ② 출처 신뢰도(1차 소스 우선)
   ③ AI 전반 관련성
   화제성/신규성은 동점일 때만 보조 지표로 사용.
6. summary_kr은 정확히 3줄. 1줄=요점, 2줄=배경 또는 메커니즘, 3줄=의의 또는 영향.
7. 각 카테고리에서 importance 내림차순으로 정렬해 상위 5개만 남긴다.
8. 본문에 개인 이메일/전화번호/주소 등 개인정보가 보이면 요약에 절대 포함하지 않는다.
9. 한국어로 작성하되 모델명·제품명·고유명사는 원어 그대로 둔다(예: GPT-5, Gemini 2.5, vLLM).
"""

Caller = Callable[[list[RawItem]], dict]


# --- public entry --------------------------------------------------------

def process(
    items: list[RawItem],
    *,
    client: Any = None,
    model: str = DEFAULT_MODEL,
    split_threshold: int = SPLIT_THRESHOLD,
    caller: Caller | None = None,
) -> Digest:
    """Run AI processing. Returns a `Digest`.

    `caller` is the seam for tests: callable(items) -> raw tool input dict.
    Production wraps a Claude call via `client` (defaults to fresh
    `anthropic.Anthropic()`).
    """
    if not items:
        return Digest(categories={c: () for c in CATEGORIES})

    if caller is None:
        client = client or _default_client()
        caller = lambda its: _call_emit_digest(client, model, its)

    if len(items) <= split_threshold:
        return _attempt_with_retry(items, caller)

    mid = len(items) // 2
    log.info("ai_processor: splitting %d items into %d + %d", len(items), mid, len(items) - mid)
    halves = [items[:mid], items[mid:]]
    digests = [_attempt_with_retry(h, caller) for h in halves]
    return _merge_digests(digests)


# --- attempt loop --------------------------------------------------------

def _attempt_with_retry(items: list[RawItem], caller: Caller) -> Digest:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            payload = caller(items)
            return _validate_payload(payload)
        except Exception as e:
            log.warning("ai_processor attempt %d failed: %s", attempt, e)
            last_exc = e
    log.error("ai_processor exhausted attempts (last error: %s); falling back", last_exc)
    return _fallback_digest(items)


# --- Claude call (production path) ---------------------------------------

def _default_client() -> Any:
    from anthropic import Anthropic
    return Anthropic()


def _call_emit_digest(client: Any, model: str, items: list[RawItem]) -> dict:
    """One Claude call with forced emit_digest. Returns the raw tool input dict.

    Raises ValueError if the model failed to emit a tool_use block we recognise.
    """
    user_msg = (
        "아래는 정규화된 AI 뉴스 항목 목록(JSON)이다. emit_digest 도구를 호출해 "
        "다이제스트를 반환하라.\n\n" + _items_to_prompt_json(items)
    )
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[EMIT_DIGEST_TOOL],
        tool_choice={"type": "tool", "name": "emit_digest"},
        messages=[{"role": "user", "content": user_msg}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_digest":
            return block.input  # SDK returns a dict
    raise ValueError("model did not emit an emit_digest tool_use block")


# --- input preparation ---------------------------------------------------

def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[:n].rstrip() + "…"


def _items_to_prompt_json(items: Iterable[RawItem]) -> str:
    rendered = []
    for it in items:
        rendered.append(
            {
                "title": it.title,
                "url": it.url,
                "source": it.source,
                "published_at": it.published_at.isoformat() if it.published_at else None,
                "raw_text": _truncate(it.raw_text, MAX_RAW_TEXT_CHARS),
            }
        )
    return json.dumps(rendered, ensure_ascii=False)


# --- output validation ---------------------------------------------------

def _validate_payload(payload: dict) -> Digest:
    if not isinstance(payload, dict) or "categories" not in payload:
        raise ValueError("payload missing `categories`")
    cats_in = payload["categories"]
    if not isinstance(cats_in, dict):
        raise ValueError("`categories` must be an object")

    result: dict[str, tuple[DigestItem, ...]] = {}
    for cat in CATEGORIES:
        items_raw = cats_in.get(cat, [])
        if not isinstance(items_raw, list):
            raise ValueError(f"category `{cat}` must be a list")
        parsed = [_parse_item(d) for d in items_raw]
        parsed.sort(key=lambda i: i.importance, reverse=True)
        result[cat] = tuple(parsed[:TOP_PER_CATEGORY])

    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        notes = ""
    return Digest(categories=result, notes=notes)


def _parse_item(d: dict) -> DigestItem:
    for k in ("title", "url", "source", "importance", "summary_kr"):
        if k not in d:
            raise ValueError(f"item missing required field `{k}`")
    summary = d["summary_kr"]
    if not isinstance(summary, list) or len(summary) != 3:
        raise ValueError("summary_kr must be a list of exactly 3 strings")
    importance = int(d["importance"])
    return DigestItem(
        title=str(d["title"]).strip(),
        url=str(d["url"]).strip(),
        source=str(d["source"]).strip(),
        importance=max(0, min(10, importance)),
        summary_kr=tuple(str(s).strip() for s in summary),
    )


# --- fallback + merge ----------------------------------------------------

def _fallback_digest(items: list[RawItem]) -> Digest:
    """Last resort when the model fails twice: dump every item as 기타."""
    dump = tuple(
        DigestItem(
            title=it.title or it.url,
            url=it.url,
            source=it.source,
            importance=0,
            summary_kr=("", "", ""),
        )
        for it in items
    )
    cats: dict[str, tuple[DigestItem, ...]] = {c: () for c in CATEGORIES}
    cats["기타"] = dump
    return Digest(categories=cats, notes="원본 링크 덤프(폴백)", fallback=True)


def _merge_digests(digests: list[Digest]) -> Digest:
    """Combine split-call results: union per category, dedup by URL, top-5."""
    combined: dict[str, list[DigestItem]] = {c: [] for c in CATEGORIES}
    notes_parts: list[str] = []
    fallback_any = False
    for d in digests:
        for c in CATEGORIES:
            combined[c].extend(d.categories.get(c, ()))
        if d.notes:
            notes_parts.append(d.notes)
        fallback_any = fallback_any or d.fallback

    final: dict[str, tuple[DigestItem, ...]] = {}
    for c in CATEGORIES:
        seen: set[str] = set()
        unique: list[DigestItem] = []
        for item in sorted(combined[c], key=lambda i: i.importance, reverse=True):
            if item.url in seen:
                continue
            seen.add(item.url)
            unique.append(item)
            if len(unique) >= TOP_PER_CATEGORY:
                break
        final[c] = tuple(unique)
    return Digest(
        categories=final,
        notes=" ".join(notes_parts).strip(),
        fallback=fallback_any,
    )
