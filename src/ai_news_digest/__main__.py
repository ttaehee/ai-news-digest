"""Entry point: ``python -m ai_news_digest``.

Reads env via Config, wires sources/provider/sender, runs the pipeline,
exits 0 on success (including the "0 items, nothing to send" case).
"""

from __future__ import annotations

import logging
import os
import sys

from .config import Config
from .delivery.base import Sender
from .delivery.console import ConsoleSender
from .delivery.email_smtp import EmailSender, SMTPConfig
from .delivery.slack import SlackSender
from .pipeline import run
from .providers import get_provider
from .sources.registry import DEFAULT_SOURCES

log = logging.getLogger("ai_news_digest")


def _build_sender(cfg: Config) -> Sender:
    # DRY_RUN trumps DELIVERY: safe path is always console.
    if cfg.dry_run or cfg.delivery in ("", "console"):
        log.info("sender: console (DRY_RUN=%s, DELIVERY=%r)", cfg.dry_run, cfg.delivery)
        return ConsoleSender()
    if cfg.delivery == "slack":
        url = os.environ.get("SLACK_WEBHOOK_URL", "")
        log.info("sender: slack (webhook configured=%s)", bool(url))
        return SlackSender(url)
    if cfg.delivery == "email":
        smtp_cfg = SMTPConfig(
            host=os.environ.get("SMTP_HOST", ""),
            port=int(os.environ.get("SMTP_PORT", "587") or "587"),
            user=os.environ.get("SMTP_USER", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            mail_to=os.environ.get("MAIL_TO", ""),
        )
        log.info("sender: email (to=%s)", smtp_cfg.mail_to)
        return EmailSender(smtp_cfg)
    raise ValueError(f"unknown DELIVERY: {cfg.delivery!r}")


def main(argv: list[str] | None = None) -> int:
    del argv  # no CLI flags yet; everything via env
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = Config.from_env()
    log.info(
        "config: LLM_PROVIDER=%s, model=%s, WINDOW_HOURS=%d, DRY_RUN=%s, DELIVERY=%r",
        cfg.llm_provider, cfg.llm_model or "default", cfg.window_hours, cfg.dry_run, cfg.delivery,
    )

    provider = get_provider(cfg.llm_provider, model=cfg.llm_model)
    sender = _build_sender(cfg)

    result = run(
        sources=DEFAULT_SOURCES,
        provider=provider,
        sender=sender,
        window_hours=cfg.window_hours,
    )
    log.info(
        "done: raw=%d, kept=%d, failed_sources=%d, sent=%s, %.2fs",
        result.raw_count, result.normalized_count, len(result.failed_sources),
        result.sent, result.elapsed_total_s,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
