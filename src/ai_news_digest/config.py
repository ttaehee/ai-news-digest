"""Environment-driven runtime configuration.

Reads `.env`-style variables once at startup. Defaults are tuned for the
safe path: free Gemini + dry-run console output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from e


@dataclass(frozen=True)
class Config:
    llm_provider: str
    llm_model: str | None
    window_hours: int
    dry_run: bool
    delivery: str           # "" | "console" | "slack" | "email"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = env if env is not None else dict(os.environ)
        # Reuse os.environ-style access via temporary swap so helpers see `env`.
        saved = os.environ
        os.environ = env  # type: ignore[assignment]
        try:
            return cls(
                llm_provider=(env.get("LLM_PROVIDER") or "gemini").strip().lower(),
                llm_model=(env.get("LLM_MODEL") or "").strip() or None,
                window_hours=_env_int("WINDOW_HOURS", 26),
                dry_run=_env_bool("DRY_RUN", True),
                delivery=(env.get("DELIVERY") or "").strip().lower(),
            )
        finally:
            os.environ = saved  # type: ignore[assignment]
