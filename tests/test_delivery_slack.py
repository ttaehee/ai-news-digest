"""Tests for SlackSender. httpx is mocked via respx — no real network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from ai_news_digest.ai_processor import CATEGORIES, Digest, DigestItem
from ai_news_digest.delivery.slack import SlackSender
from ai_news_digest.eval.scorer import DigestScore, ItemScore, RuleViolation


WEBHOOK = "https://hooks.slack.example.com/services/T0/B0/XYZ"
RUN_AT = datetime(2026, 6, 14, 0, 0, 0, tzinfo=timezone.utc)


def _item(title="Foo released", url="https://e/foo", source="OpenAI Blog") -> DigestItem:
    return DigestItem(
        title=title,
        url=url,
        source=source,
        importance=9,
        summary_kr="간결 한 줄",
    )


def _digest_with(items: tuple[DigestItem, ...] = (), cat: str = "Model") -> Digest:
    base = {c: () for c in CATEGORIES}
    base[cat] = items
    return Digest(categories=base)


def _empty_digest() -> Digest:
    return Digest(categories={c: () for c in CATEGORIES})


def _sent_payload(route) -> dict:
    return json.loads(route.calls.last.request.content)


# --- constructor ---------------------------------------------------------


def test_requires_webhook_url():
    with pytest.raises(ValueError, match="webhook"):
        SlackSender("")


def test_stores_webhook_url():
    assert SlackSender("https://hooks.example.com/abc").webhook_url == "https://hooks.example.com/abc"


# --- send ----------------------------------------------------------------


def test_posts_rendered_text_to_webhook():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(_digest_with((_item(),)), run_at=RUN_AT)
    assert route.called
    text = _sent_payload(route)["text"]
    assert "AI 뉴스 다이제스트" in text
    assert "Foo released" in text
    assert "https://e/foo" in text


def test_category_header_uses_slack_bold_not_markdown_pound():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(_digest_with((_item(),)), run_at=RUN_AT)
    text = _sent_payload(route)["text"]
    assert "*Model*" in text
    # Slack mrkdwn doesn't render `#` headings — must not emit them.
    assert "# Model" not in text


def test_title_wrapped_in_slack_link_syntax():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(
            _digest_with((_item(title="Foo", url="https://e/foo"),)),
            run_at=RUN_AT,
        )
    text = _sent_payload(route)["text"]
    assert "<https://e/foo|Foo>" in text


def test_item_line_inlines_summary_after_link():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(
            _digest_with((_item(title="Foo", url="https://e/foo", source="OpenAI Blog"),)),
            run_at=RUN_AT,
        )
    text = _sent_payload(route)["text"]
    # default _item summary is "간결 한 줄"
    assert "• <https://e/foo|Foo> — 간결 한 줄 (OpenAI Blog)" in text


def test_category_header_has_emoji_prefix():
    items_by_cat = {
        "Model":     (_item(title="m"),),
        "Paper":     (_item(title="p"),),
        "Tool":      (_item(title="t"),),
        "Misc":      (_item(title="o"),),
        "Community": (_item(title="c"),),
    }
    base = {c: () for c in CATEGORIES}
    base.update(items_by_cat)
    digest = Digest(categories=base)
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(digest, run_at=RUN_AT)
    text = _sent_payload(route)["text"]
    assert "🌵 *Model*" in text
    assert "📖 *Paper*" in text
    assert "🍄‍🟫 *Tool*" in text
    assert "🌿 *Misc*" in text
    assert "🍊 *Community*" in text


def test_blank_line_separates_categories():
    items_a = (_item(title="a", url="https://e/a"),)
    items_b = (_item(title="b", url="https://e/b"),)
    base = {c: () for c in CATEGORIES}
    base["Model"] = items_a
    base["Paper"] = items_b
    digest = Digest(categories=base)
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(digest, run_at=RUN_AT)
    text = _sent_payload(route)["text"]
    a_idx = text.index("*Model*")
    b_idx = text.index("*Paper*")
    # at least one blank line between the two category sections
    assert "\n\n" in text[a_idx:b_idx]


def test_empty_summary_omits_em_dash_segment():
    item = DigestItem(
        title="bare", url="https://e/bare", source="X", importance=0, summary_kr=""
    )
    base = {c: () for c in CATEGORIES}
    base["Misc"] = (item,)
    digest = Digest(categories=base)
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(digest, run_at=RUN_AT)
    text = _sent_payload(route)["text"]
    assert "• <https://e/bare|bare> (X)" in text
    assert "bare —" not in text  # no orphan em-dash when summary is blank


def test_uses_kst_date_in_header():
    # 2026-06-14 00:00 UTC == 2026-06-14 09:00 KST
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(_digest_with((_item(),)), run_at=RUN_AT)
    assert "2026-06-14 (KST)" in _sent_payload(route)["text"]


def test_passes_failed_sources_into_body():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(
            _digest_with((_item(),)),
            run_at=RUN_AT,
            failed_sources=["Microsoft Research"],
        )
    assert "(일부 소스 실패: Microsoft Research)" in _sent_payload(route)["text"]


def test_sends_exactly_once_per_call():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(_empty_digest(), run_at=RUN_AT)
    assert route.call_count == 1


def test_payload_is_text_only_no_extra_keys():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(_digest_with((_item(),)), run_at=RUN_AT)
    payload = _sent_payload(route)
    assert set(payload.keys()) == {"text"}


def test_raises_on_4xx_status():
    with respx.mock() as router:
        router.post(WEBHOOK).mock(return_value=httpx.Response(400, text="invalid_payload"))
        with pytest.raises(httpx.HTTPStatusError):
            SlackSender(WEBHOOK).send(_empty_digest(), run_at=RUN_AT)


def test_raises_on_5xx_status():
    with respx.mock() as router:
        router.post(WEBHOOK).mock(return_value=httpx.Response(503, text="busy"))
        with pytest.raises(httpx.HTTPStatusError):
            SlackSender(WEBHOOK).send(_empty_digest(), run_at=RUN_AT)


def _score(passed: int, total: int) -> DigestScore:
    items = tuple(
        ItemScore(
            title=f"t{i}",
            summary_kr="s",
            violations=() if i < passed else (RuleViolation("banned", "혁신"),),
            title_sim=0.0,
        )
        for i in range(total)
    )
    return DigestScore(items=items)


def test_quality_line_appears_with_slack_bold():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(
            _digest_with((_item(),)),
            run_at=RUN_AT,
            score=_score(passed=12, total=15),
        )
    text = _sent_payload(route)["text"]
    assert "📊 *요약 품질*: 12/15 통과 (80%)" in text


def test_quality_line_warns_below_threshold_in_slack():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(
            _digest_with((_item(),)),
            run_at=RUN_AT,
            score=_score(passed=5, total=15),
        )
    text = _sent_payload(route)["text"]
    assert "⚠️ *요약 품질*: 5/15 통과 (33%) — 기준 70% 미달" in text


def test_quality_line_omitted_when_score_none_in_slack():
    with respx.mock() as router:
        route = router.post(WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))
        SlackSender(WEBHOOK).send(_digest_with((_item(),)), run_at=RUN_AT)
    text = _sent_payload(route)["text"]
    assert "요약 품질" not in text


def test_raises_on_network_error():
    with respx.mock() as router:
        router.post(WEBHOOK).mock(side_effect=httpx.ConnectError("network down"))
        with pytest.raises(httpx.ConnectError):
            SlackSender(WEBHOOK).send(_empty_digest(), run_at=RUN_AT)
