"""Tests for SlackSender. httpx is mocked via respx — no real network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from ai_news_digest.ai_processor import CATEGORIES, Digest, DigestItem
from ai_news_digest.delivery.slack import SlackSender


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


def _digest_with(items: tuple[DigestItem, ...] = (), cat: str = "모델출시") -> Digest:
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


def test_raises_on_network_error():
    with respx.mock() as router:
        router.post(WEBHOOK).mock(side_effect=httpx.ConnectError("network down"))
        with pytest.raises(httpx.ConnectError):
            SlackSender(WEBHOOK).send(_empty_digest(), run_at=RUN_AT)
