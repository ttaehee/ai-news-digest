"""AI processing stage (PLAN §5): dedupe, categorize, score, summarize.

Provider-agnostic orchestration. Validation, retry, fallback, and split-merge
live here; the actual LLM call is delegated to an `LLMProvider` (see
``providers/``). The ``caller`` seam stays for tests so no SDK is touched.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable

from .sources.base import RawItem

if TYPE_CHECKING:
    from .providers.base import LLMProvider

log = logging.getLogger(__name__)

SPLIT_THRESHOLD = 80         # > this many items triggers a halved-call
TOP_PER_CATEGORY = 5         # cap per category in the final digest
MAX_RAW_TEXT_CHARS = 1000    # raw_text truncation before sending to the LLM
MAX_ATTEMPTS = 2             # 1 initial + 1 retry; then fallback
RETRY_BACKOFF_S = 10.0       # wait before retrying — absorbs transient LLM 503s

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
    provider: "LLMProvider | None" = None,
    split_threshold: int = SPLIT_THRESHOLD,
    caller: Caller | None = None,
) -> Digest:
    """Run AI processing. Returns a `Digest`.

    `caller` is the seam for tests: callable(items) -> raw tool/JSON dict.
    In production, `provider.emit_digest` is used; if no provider is passed,
    `providers.get_provider()` selects the default (gemini).
    """
    if not items:
        return Digest(categories={c: () for c in CATEGORIES})

    if caller is None:
        if provider is None:
            from .providers import get_provider
            provider = get_provider()
        caller = provider.emit_digest

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
        if attempt < MAX_ATTEMPTS:
            log.info("ai_processor sleeping %.1fs before retry", RETRY_BACKOFF_S)
            time.sleep(RETRY_BACKOFF_S)
    log.error("ai_processor exhausted attempts (last error: %s); falling back", last_exc)
    return _fallback_digest(items)


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
    """Combine split-call results: union per category, dedup by URL, top-5.

    ``fallback`` is recomputed from the *output*. It stays True only when a
    raw-dump item actually survives the top-5 sort; if real items out-rank
    every importance-0 fallback entry the merged digest is fully real and
    the warning banner is suppressed. Fallback-half notes are likewise
    dropped when their items don't surface, so a successful half doesn't
    inherit the other half's "폴백" message.
    """
    combined: dict[str, list[DigestItem]] = {c: [] for c in CATEGORIES}
    fallback_items: set[DigestItem] = set()
    for d in digests:
        for c in CATEGORIES:
            items_in_cat = d.categories.get(c, ())
            combined[c].extend(items_in_cat)
            if d.fallback:
                fallback_items.update(items_in_cat)

    final: dict[str, tuple[DigestItem, ...]] = {}
    output_has_fallback = False
    for c in CATEGORIES:
        seen: set[str] = set()
        unique: list[DigestItem] = []
        for item in sorted(combined[c], key=lambda i: i.importance, reverse=True):
            if item.url in seen:
                continue
            seen.add(item.url)
            unique.append(item)
            if item in fallback_items:
                output_has_fallback = True
            if len(unique) >= TOP_PER_CATEGORY:
                break
        final[c] = tuple(unique)

    notes_parts: list[str] = []
    for d in digests:
        if not d.notes:
            continue
        if d.fallback and not output_has_fallback:
            continue
        notes_parts.append(d.notes)

    return Digest(
        categories=final,
        notes=" ".join(notes_parts).strip(),
        fallback=output_has_fallback,
    )
