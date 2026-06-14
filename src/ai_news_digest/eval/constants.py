"""Single source of truth for prompt-and-checker constants.

`ai_processor.SYSTEM_PROMPT` imports these and renders them into the prompt
text, so editing the lists here updates both the model's instructions and
the evaluator's pass/fail rules in one place — no drift.
"""

from __future__ import annotations

# Abstract hype / filler vocabulary the model is told to avoid and the
# evaluator flags on detection. Substring-matched against summary_kr, with
# exceptions below to skip legitimate compounds.
BANNED_WORDS: tuple[str, ...] = (
    "혁신",
    "강화",
    "확장",
    "진전",
    "발전",
    "도약",
    "역량",
    "기대된다",
    "중요한 이정표",
    "주목할 만하다",
    "할 것입니다",
    "할 수 있다",
)

# Compound phrases that contain a banned word but are legitimate technical
# vocabulary — these get masked out before the banned-word substring scan
# so we don't flag things like "강화학습". Add new entries when a false
# positive shows up.
BANNED_EXCEPTIONS: dict[str, tuple[str, ...]] = {
    "강화": ("강화학습", "강화 학습"),
    "확장": ("확장성", "확장 가능", "확장가능"),
}

# Opaque technical terms the model is told to unpack or drop. Both English
# spellings and Korean transliterations are listed because the model has
# been observed leaving the rendered form ("인코더 없는") when told to avoid
# "encoder-free".
JARGON_TERMS: tuple[str, ...] = (
    "encoder-free",
    "인코더 없는",
    "self-consistency",
    "KV cache",
    "GRPO",
    "distillation",
    "embedding",
)

# Title-translation similarity gate. Jaccard over whitespace+punctuation
# tokens of (title, summary_kr); a score at or above this is flagged.
TITLE_SIM_THRESHOLD: float = 0.5

# Hard length cap for summary_kr (characters).
MAX_SUMMARY_LENGTH: int = 120
