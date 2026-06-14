"""SMTP email sender — **scaffold only**.

Constructor validates the SMTP config so misconfigurations fail at startup,
not at send time. The actual ``smtplib`` call is deferred per PLAN §9 row 5;
``send()`` raises until activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..ai_processor import Digest
from ..eval import DigestScore
from ..render import render_text
from .base import Sender


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    user: str
    password: str
    mail_to: str

    def __post_init__(self) -> None:
        for field in ("host", "user", "password", "mail_to"):
            if not getattr(self, field):
                raise ValueError(f"SMTPConfig.{field} must be set")
        if not (0 < self.port < 65536):
            raise ValueError("SMTPConfig.port must be in (0, 65535]")


class EmailSender(Sender):
    def __init__(self, config: SMTPConfig) -> None:
        self.config = config

    def send(
        self,
        digest: Digest,
        *,
        run_at: datetime | None = None,
        failed_sources: list[str] | None = None,
        score: DigestScore | None = None,
    ) -> None:
        _body = render_text(
            digest, run_at=run_at, failed_sources=failed_sources, score=score
        )
        del _body
        raise NotImplementedError(
            "EmailSender is scaffolded but not wired. Keep DRY_RUN=1 (default) "
            "to use ConsoleSender; activate this sender in a later step when "
            "SMTP credentials are configured."
        )
