"""Unit tests for the env-driven Config."""

from __future__ import annotations

import pytest

from ai_news_digest.config import Config


def test_defaults_are_safe():
    cfg = Config.from_env(env={})
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_model is None
    assert cfg.window_hours == 26
    assert cfg.dry_run is True
    assert cfg.delivery == ""


def test_provider_name_lowercased_and_stripped():
    cfg = Config.from_env(env={"LLM_PROVIDER": "  CLAUDE  "})
    assert cfg.llm_provider == "claude"


def test_empty_model_becomes_none():
    assert Config.from_env(env={"LLM_MODEL": ""}).llm_model is None
    assert Config.from_env(env={"LLM_MODEL": "  "}).llm_model is None


def test_model_override_kept():
    assert Config.from_env(env={"LLM_MODEL": "gemini-2.5-flash-lite"}).llm_model == "gemini-2.5-flash-lite"


def test_window_hours_parses_int():
    assert Config.from_env(env={"WINDOW_HOURS": "12"}).window_hours == 12


def test_window_hours_rejects_garbage():
    with pytest.raises(ValueError, match="WINDOW_HOURS"):
        Config.from_env(env={"WINDOW_HOURS": "abc"})


def test_dry_run_truthy_strings_kept():
    assert Config.from_env(env={"DRY_RUN": "1"}).dry_run is True
    assert Config.from_env(env={"DRY_RUN": "true"}).dry_run is True
    assert Config.from_env(env={"DRY_RUN": "yes"}).dry_run is True


def test_dry_run_falsy_strings_disabled():
    for v in ("0", "false", "False", "no", "off"):
        assert Config.from_env(env={"DRY_RUN": v}).dry_run is False, v


def test_dry_run_empty_string_falls_back_to_default():
    assert Config.from_env(env={"DRY_RUN": ""}).dry_run is True


def test_delivery_lowercased():
    assert Config.from_env(env={"DELIVERY": "SLACK"}).delivery == "slack"
