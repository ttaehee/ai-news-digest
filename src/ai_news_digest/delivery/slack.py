"""Slack sender — POSTs the rendered digest to an Incoming Webhook."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from ..ai_processor import Digest
from ..render import render_text
from .base import Sender

log = logging.getLogger(__name__)

_TIMEOUT_S = 10.0


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
        body = render_text(digest, run_at=run_at, failed_sources=failed_sources)
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
