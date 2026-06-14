"""Rule-based evaluation harness for summary_kr quality.

Loads:
* `constants` — banned words / jargon terms / thresholds (single source of
  truth; ai_processor.SYSTEM_PROMPT imports the same lists)
* `rules` — four per-item checkers (banned, jargon, title-similarity, length)
* `scorer` — aggregate ItemScore / DigestScore
"""

from .scorer import (
    DigestScore,
    ItemScore,
    RuleViolation,
    score_digest,
    score_item,
    score_items,
)

__all__ = [
    "DigestScore",
    "ItemScore",
    "RuleViolation",
    "score_digest",
    "score_item",
    "score_items",
]
