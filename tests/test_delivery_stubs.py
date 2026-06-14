"""Tests for the Email sender scaffold.

SlackSender was promoted to a real implementation; its tests live in
tests/test_delivery_slack.py. EmailSender remains a scaffold per
PLAN §9 row 5 — these tests pin the construction-time config validation
and the explicit "not wired yet" send() refusal.
"""

from __future__ import annotations

import pytest

from ai_news_digest.ai_processor import CATEGORIES, Digest
from ai_news_digest.delivery.email_smtp import EmailSender, SMTPConfig


def _empty_digest() -> Digest:
    return Digest(categories={c: () for c in CATEGORIES})


def _valid_smtp_config(**overrides) -> SMTPConfig:
    defaults = dict(
        host="smtp.example.com",
        port=587,
        user="me",
        password="pw",
        mail_to="you@example.com",
    )
    defaults.update(overrides)
    return SMTPConfig(**defaults)


def test_smtp_config_requires_all_string_fields():
    for field in ("host", "user", "password", "mail_to"):
        with pytest.raises(ValueError, match=field):
            _valid_smtp_config(**{field: ""})


def test_smtp_config_rejects_invalid_port():
    with pytest.raises(ValueError, match="port"):
        _valid_smtp_config(port=0)
    with pytest.raises(ValueError, match="port"):
        _valid_smtp_config(port=70000)


def test_smtp_config_accepts_valid_settings():
    cfg = _valid_smtp_config()
    assert cfg.host == "smtp.example.com"
    assert cfg.port == 587


def test_email_sender_send_raises_until_wired():
    sender = EmailSender(_valid_smtp_config())
    with pytest.raises(NotImplementedError, match="scaffolded"):
        sender.send(_empty_digest())
