"""Per-rule checkers. Each returns a list of (detail) strings describing
violations; an empty list means the rule passed for that item."""

from __future__ import annotations

import re

from .constants import (
    BANNED_EXCEPTIONS,
    BANNED_WORDS,
    JARGON_TERMS,
    MAX_SUMMARY_LENGTH,
    TITLE_SIM_THRESHOLD,
)

_TOKEN_SPLIT = re.compile(r"[^\w가-힣]+", re.UNICODE)


def check_banned_words(summary: str) -> list[str]:
    """Substring-match BANNED_WORDS against summary, masking exception phrases
    so legitimate compounds (e.g. '강화학습' contains '강화') don't trigger.
    Returns the list of banned words found.
    """
    found: list[str] = []
    for word in BANNED_WORDS:
        masked = summary
        for exc in BANNED_EXCEPTIONS.get(word, ()):
            masked = masked.replace(exc, " " * len(exc))
        if word in masked:
            found.append(word)
    return found


def check_jargon(summary: str) -> list[str]:
    """Case-insensitive substring scan for JARGON_TERMS in summary."""
    lowered = summary.lower()
    return [term for term in JARGON_TERMS if term.lower() in lowered]


def title_similarity(title: str, summary: str) -> float:
    """Jaccard similarity over whitespace+punctuation tokens of title and
    summary. Returns 0.0 if either side has no tokens.

    Known limitation: Korean particles ('이/가/을/를/…') stick to nouns so
    'GPT-5' and 'GPT-5을' tokenize differently and Jaccard under-counts. If
    that turns out to miss real title-translation cases in practice, swap
    to character n-gram similarity.
    """
    t_tokens = {t for t in _TOKEN_SPLIT.split(title.lower()) if t}
    s_tokens = {t for t in _TOKEN_SPLIT.split(summary.lower()) if t}
    if not t_tokens or not s_tokens:
        return 0.0
    return len(t_tokens & s_tokens) / len(t_tokens | s_tokens)


def check_title_translation(title: str, summary: str) -> list[str]:
    sim = title_similarity(title, summary)
    if sim >= TITLE_SIM_THRESHOLD:
        return [f"{sim:.2f} >= {TITLE_SIM_THRESHOLD:.2f}"]
    return []


def check_length(summary: str) -> list[str]:
    n = len(summary)
    if n > MAX_SUMMARY_LENGTH:
        return [f"{n} > {MAX_SUMMARY_LENGTH}"]
    return []
