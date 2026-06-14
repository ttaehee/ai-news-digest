"""Aggregate scoring — per-item and per-digest."""

from __future__ import annotations

from dataclasses import dataclass, field

from .rules import (
    check_banned_words,
    check_jargon,
    check_length,
    check_title_translation,
    title_similarity,
)

RULE_BANNED = "banned"
RULE_JARGON = "jargon"
RULE_TITLE_SIM = "title_sim"
RULE_LENGTH = "length"
RULES: tuple[str, ...] = (RULE_BANNED, RULE_JARGON, RULE_TITLE_SIM, RULE_LENGTH)


@dataclass(frozen=True)
class RuleViolation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}({self.detail})"


@dataclass(frozen=True)
class ItemScore:
    title: str
    summary_kr: str
    violations: tuple[RuleViolation, ...]
    title_sim: float

    @property
    def passed(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class DigestScore:
    items: tuple[ItemScore, ...]

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for i in self.items if i.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total if self.total else 0.0

    def violations_by_rule(self) -> dict[str, int]:
        counts: dict[str, int] = {r: 0 for r in RULES}
        for item in self.items:
            for v in item.violations:
                counts[v.rule] = counts.get(v.rule, 0) + 1
        return counts


def score_item(title: str, summary_kr: str) -> ItemScore:
    violations: list[RuleViolation] = []
    for word in check_banned_words(summary_kr):
        violations.append(RuleViolation(RULE_BANNED, word))
    for term in check_jargon(summary_kr):
        violations.append(RuleViolation(RULE_JARGON, term))
    for detail in check_title_translation(title, summary_kr):
        violations.append(RuleViolation(RULE_TITLE_SIM, detail))
    for detail in check_length(summary_kr):
        violations.append(RuleViolation(RULE_LENGTH, detail))
    return ItemScore(
        title=title,
        summary_kr=summary_kr,
        violations=tuple(violations),
        title_sim=title_similarity(title, summary_kr),
    )


def score_items(items: list[dict]) -> DigestScore:
    """Score a list of {title, summary_kr, ...} dicts. Extra fields ignored."""
    scored = tuple(
        score_item(item.get("title", ""), item.get("summary_kr", ""))
        for item in items
    )
    return DigestScore(items=scored)
