"""Slack sender — **scaffold only**.

The class wiring, config validation, and body rendering are in place so the
pipeline can pick this sender up when ``DELIVERY=slack``. The actual HTTP
POST to the webhook is deliberately deferred per PLAN §9 row 5
("실제 HTTP 호출은 추후 단계에서 활성화"); ``send()`` raises until then.
"""

from __future__ import annotations

from datetime import datetime

from ..ai_processor import Digest
from ..render import render_text
from .base import Sender


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
    ) -> None:
        # The body we *would* send. Built now so wiring later is a one-line
        # change (post a Block Kit message built around this text).
        _body = render_text(digest, run_at=run_at, failed_sources=failed_sources)
        del _body  # not used yet — silences linters
        raise NotImplementedError(
            "SlackSender is scaffolded but not wired. Keep DRY_RUN=1 (default) "
            "to use ConsoleSender; activate this sender in a later step when "
            "the SLACK_WEBHOOK_URL is configured."
        )
