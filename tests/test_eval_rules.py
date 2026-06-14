"""Unit tests for eval rules and the score aggregator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_news_digest.eval.constants import (
    MAX_SUMMARY_LENGTH,
    TITLE_SIM_THRESHOLD,
)
from ai_news_digest.eval.rules import (
    check_banned_words,
    check_jargon,
    check_length,
    check_title_translation,
    title_similarity,
)
from ai_news_digest.eval.scorer import (
    RULE_BANNED,
    RULE_JARGON,
    RULE_LENGTH,
    RULE_TITLE_SIM,
    score_item,
    score_items,
)


# --- check_banned_words -------------------------------------------------


def test_banned_words_flags_single_hit():
    assert check_banned_words("이 모델은 혁신적이다") == ["혁신"]


def test_banned_words_flags_multiple():
    found = check_banned_words("역량을 강화하는 기술적 진전이 발표됐다.")
    assert set(found) == {"역량", "강화", "진전"}


def test_banned_words_skips_강화학습_compound():
    # '강화' is banned but '강화학습' is a legitimate technical term
    assert check_banned_words("강화학습으로 게임 AI를 훈련한다.") == []


def test_banned_words_still_flags_standalone_강화_after_compound():
    found = check_banned_words("강화학습 연구로 모델 능력을 강화했다.")
    assert "강화" in found


def test_banned_words_skips_확장가능_compound():
    assert check_banned_words("확장 가능한 분산 학습 인프라.") == []


def test_banned_words_flags_standalone_확장():
    assert "확장" in check_banned_words("AI 아키텍처 혁신을 확장한다.")


def test_banned_words_returns_empty_for_clean_text():
    assert check_banned_words("구글이 Gemini 3을 출시했다.") == []


# --- check_jargon -------------------------------------------------------


def test_jargon_flags_english_term():
    assert "encoder-free" in check_jargon("encoder-free 모델 출시")


def test_jargon_flags_korean_transliteration():
    assert "인코더 없는" in check_jargon("인코더 없는 멀티모달 모델")


def test_jargon_flags_self_consistency():
    assert "self-consistency" in check_jargon("self-consistency 기법 적용")


def test_jargon_is_case_insensitive():
    assert "grpo" not in check_jargon("Grpo 적용")  # exact case for short acronyms
    assert "GRPO" in check_jargon("Grpo 적용")


def test_jargon_returns_empty_for_unpacked_text():
    assert check_jargon("구글이 이미지와 글을 함께 이해하는 모델을 냈다.") == []


# --- title_similarity ---------------------------------------------------


def test_similarity_one_for_identical_strings():
    assert title_similarity("Foo bar baz", "Foo bar baz") == pytest.approx(1.0)


def test_similarity_zero_for_disjoint_strings():
    assert title_similarity("Foo bar", "Baz qux") == pytest.approx(0.0)


def test_similarity_zero_when_either_side_empty():
    assert title_similarity("", "anything") == 0.0
    assert title_similarity("anything", "") == 0.0


def test_similarity_partial_overlap():
    # Three tokens vs three tokens, one shared → Jaccard = 1/5
    assert title_similarity("a b c", "c d e") == pytest.approx(1 / 5)


# --- check_title_translation -------------------------------------------


def test_title_translation_flags_near_identical():
    # Same content, light rephrasing
    title = "구글이 Gemini 3을 출시했다"
    summary = "구글이 Gemini 3을 출시했다."
    violations = check_title_translation(title, summary)
    assert violations  # should flag
    assert str(TITLE_SIM_THRESHOLD) in violations[0] or "0." in violations[0]


def test_title_translation_passes_for_paraphrase_with_added_context():
    title = "Position: Hippocampal Explicit Memory Is the Cornerstone for AGI"
    summary = "LLM을 AGI 수준으로 끌어올리려면 명시적 기억 시스템이 필수라고 주장하는 논문."
    assert check_title_translation(title, summary) == []


# --- check_length ------------------------------------------------------


def test_length_passes_at_exact_max():
    text = "x" * MAX_SUMMARY_LENGTH
    assert check_length(text) == []


def test_length_fails_one_over_max():
    text = "x" * (MAX_SUMMARY_LENGTH + 1)
    violations = check_length(text)
    assert violations
    assert str(MAX_SUMMARY_LENGTH + 1) in violations[0]


def test_length_passes_for_short_text():
    assert check_length("짧은 요약.") == []


# --- score_item --------------------------------------------------------


def test_score_item_collects_all_violations():
    item = score_item(
        title="새 기술",
        summary_kr="역량을 강화하는 self-consistency 기반의 기술적 진전이 발표됐다.",
    )
    rules_violated = {v.rule for v in item.violations}
    assert RULE_BANNED in rules_violated   # 역량/강화/진전
    assert RULE_JARGON in rules_violated   # self-consistency
    assert not item.passed


def test_score_item_passes_clean_summary():
    item = score_item(
        title="Anthropic releases Claude Sonnet 5",
        summary_kr="Anthropic이 Claude Sonnet 5를 공개했다. 코딩 벤치마크가 20% 향상됐다.",
    )
    assert item.passed
    assert item.violations == ()


# --- score_items aggregate ---------------------------------------------


def test_score_items_pass_rate():
    items = [
        {"title": "X", "summary_kr": "깨끗한 요약."},
        {"title": "Y", "summary_kr": "혁신적이다."},  # banned
        {"title": "Z", "summary_kr": "또 다른 깨끗한 요약."},
    ]
    score = score_items(items)
    assert score.total == 3
    assert score.passed_count == 2
    assert score.pass_rate == pytest.approx(2 / 3)


def test_score_items_violations_by_rule():
    items = [
        {"title": "X", "summary_kr": "혁신적 발표"},
        {"title": "Y", "summary_kr": "encoder-free 모델"},
        {"title": "Z", "summary_kr": "x" * (MAX_SUMMARY_LENGTH + 5)},
    ]
    counts = score_items(items).violations_by_rule()
    assert counts[RULE_BANNED] >= 1
    assert counts[RULE_JARGON] >= 1
    assert counts[RULE_LENGTH] >= 1


def test_score_items_empty_input():
    score = score_items([])
    assert score.total == 0
    assert score.pass_rate == 0.0


# --- fixture sample set ------------------------------------------------


def test_fixture_samples_score_as_labeled():
    path = Path(__file__).parent / "fixtures" / "eval_samples.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    score = score_items(items)

    # Walk items by index, cross-check labels with pass/fail
    for i, (item, scored) in enumerate(zip(items, score.items), 1):
        label = item.get("_label", "")
        if label.startswith("good"):
            assert scored.passed, (
                f"sample #{i} labeled good but failed: {scored.violations}"
            )
        elif label.startswith("bad"):
            assert not scored.passed, (
                f"sample #{i} labeled bad but passed: {item['summary_kr']}"
            )
