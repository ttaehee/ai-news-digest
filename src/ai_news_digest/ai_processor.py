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
TOP_PER_CATEGORY = 3         # cap per category in the final digest
MAX_RAW_TEXT_CHARS = 1000    # raw_text truncation before sending to the LLM
MAX_ATTEMPTS = 2             # 1 initial + 1 retry; then fallback
RETRY_BACKOFF_S = 10.0       # wait before retrying — absorbs transient LLM 503s

CATEGORIES: tuple[str, ...] = ("Model", "Paper", "Tool", "Misc", "Community")


@dataclass(frozen=True)
class DigestItem:
    title: str
    url: str
    source: str
    importance: int                # 0–10
    summary_kr: str                # single concise sentence (may be "" in fallback)


@dataclass(frozen=True)
class Digest:
    categories: dict[str, tuple[DigestItem, ...]]
    notes: str = ""
    fallback: bool = False        # True when raw-link dump path was used

    def total_items(self) -> int:
        return sum(len(v) for v in self.categories.values())


from .eval.constants import BANNED_WORDS, JARGON_TERMS, MAX_SUMMARY_LENGTH
from .sources.registry import COMMUNITY_SOURCES

_BANNED_LIST = ", ".join(f"'{w}'" for w in BANNED_WORDS)
_JARGON_LIST = ", ".join(f"'{w}'" for w in JARGON_TERMS)
_COMMUNITY_LIST = ", ".join(f"'{s}'" for s in sorted(COMMUNITY_SOURCES))

SYSTEM_PROMPT = f"""\
당신은 한국어 AI 뉴스 다이제스트 큐레이터다.

규칙:
1. 사용자 입력에 정규화된 AI 뉴스 항목 목록이 JSON으로 들어온다.
2. emit_digest 도구를 정확히 한 번 호출해 다이제스트를 반환한다. 자연어 응답은 하지 않는다.
3. 중복 제거는 하지 않는다. 같은 주제가 여러 소스에 나오면 각각 별개 항목으로
   유지하고 source 규칙대로 각자 카테고리에 분류한다(예: 같은 발표의 공식 블로그는
   Model에, 같은 발표의 커뮤니티 토론은 Community에 — 둘 다 보존).
4. 카테고리(영어 키 그대로 사용, 번역하지 말 것):
   - Model: 새로운 모델·주요 모델 업데이트·API 변경
   - Paper: 연구·논문·기술 보고서
   - Tool: 라이브러리·서비스·SDK·통합·플랫폼 발표
   - Misc: 위 셋에 명확히 안 맞는 의미 있는 AI 뉴스 (단, 커뮤니티 출처는 제외)
   - Community: source가 {_COMMUNITY_LIST} 중 하나인 모든 항목 (커뮤니티 반응·토론).
     1차 소스에서 온 항목은 절대 여기로 분류하지 않는다.
5. importance는 0–10 정수. 우선순위:
   ① 업계 파급력(새 모델·주요 API 변경 등)
   ② 출처 신뢰도(1차 소스 우선)
   ③ AI 전반 관련성
   화제성/신규성은 동점일 때만 보조 지표로 사용.

   추가 가중치:
   - **높임**: 새 모델·중요 모델 업데이트·기술 발전·논문·AI 규제·정책·실제 사건(사고/소송/보안).
   - **낮춤**: 단순 파트너십·협력·통합·인프라 보도자료성 발표
     (예: 'X가 Y GPU 채택', 'A와 B 통합', 'X 클라우드에서 Y 모델 사용 가능',
     'X 행사·이벤트·할인 안내', '가격·요금제 변경 외 새 기능 없는 비즈니스 소식').
6. summary_kr은 짧은 한 줄 문자열(1–2개의 짧은 문장). 다음을 모두 지킨다:
   - 제목을 번역만 한 문장 금지. 본문(raw_text)에서 핵심을 풀어 설명한다.
   - '이게 뭔지(누가/무엇을)' + '왜 중요한지/뭐가 새로운지' 둘 다 담는다.
   - 전문용어(예: {_JARGON_LIST})는 **반드시 풀어 쓰거나 빼고**,
     비전문가가 한 번 읽고 감 잡을 수준으로.
   - **추상적 평가어·미사여구 절대 금지**:
     {_BANNED_LIST}.
     구체적으로 무엇이 어떻게 달라지는지만 쓴다.
   - 가능하면 한국어 {MAX_SUMMARY_LENGTH}자 이내.

   예시:
   - 나쁨: "통합된 인코더 없는 멀티모달 모델로 AI 아키텍처 혁신을 확장한다"
     (전문용어 그대로 + 빈 칭찬 + 뭐가 새로운지 없음)
   - 좋음: "구글이 이미지와 글을 함께 이해하는 새 AI 모델을 냈다. 구조를 단순하게 만들어 더 가볍고 빠르다."
     (누가·무엇을·뭐가 달라지는지 구체적, 전문용어 풀어 씀)
7. 각 카테고리에서 importance 내림차순으로 정렬해 상위 3개만 남긴다.
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
    if not isinstance(summary, str):
        raise ValueError("summary_kr must be a string")
    importance = int(d["importance"])
    return DigestItem(
        title=str(d["title"]).strip(),
        url=str(d["url"]).strip(),
        source=str(d["source"]).strip(),
        importance=max(0, min(10, importance)),
        summary_kr=summary.strip(),
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
            summary_kr="",
        )
        for it in items
    )
    cats: dict[str, tuple[DigestItem, ...]] = {c: () for c in CATEGORIES}
    cats["Misc"] = dump
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
