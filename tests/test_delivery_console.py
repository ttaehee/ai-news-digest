"""Tests for ConsoleSender and the shared render_text formatter."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pytest

from ai_news_digest.ai_processor import CATEGORIES, Digest, DigestItem
from ai_news_digest.delivery.console import ConsoleSender
from ai_news_digest.render import KST, render_text


# 2026-06-09 00:00 UTC == 2026-06-09 09:00 KST (the target morning slot)
RUN_AT = datetime(2026, 6, 9, 0, 0, 0, tzinfo=timezone.utc)


def _item(
    title="New model X",
    url="https://e/x",
    source="OpenAI Blog",
    importance=9,
    summary="요약 한 줄",
) -> DigestItem:
    return DigestItem(
        title=title,
        url=url,
        source=source,
        importance=importance,
        summary_kr=summary,
    )


def _digest(
    cats: dict[str, tuple[DigestItem, ...]] | None = None,
    notes: str = "",
    fallback: bool = False,
) -> Digest:
    base = {c: () for c in CATEGORIES}
    if cats:
        base.update(cats)
    return Digest(categories=base, notes=notes, fallback=fallback)


# --- render_text ---------------------------------------------------------


def test_header_uses_kst_date_from_utc_run_at():
    text = render_text(_digest(), run_at=RUN_AT)
    assert text.startswith("AI 뉴스 다이제스트 — 2026-06-09 (KST)\n")


def test_late_utc_run_renders_next_day_in_kst():
    # 23:00 UTC on the 9th -> 08:00 KST on the 10th
    late = datetime(2026, 6, 9, 23, 0, 0, tzinfo=timezone.utc)
    text = render_text(_digest(), run_at=late)
    assert "2026-06-10 (KST)" in text


def test_empty_digest_shows_no_items_notice():
    text = render_text(_digest(), run_at=RUN_AT)
    assert "(다이제스트에 포함할 항목 없음)" in text
    # no category headings emitted when everything's empty
    assert "# Model" not in text


def test_includes_only_nonempty_categories():
    text = render_text(
        _digest(cats={"Model": (_item(),)}), run_at=RUN_AT
    )
    assert "# Model" in text
    assert "# Paper" not in text
    assert "# Tool" not in text
    assert "# Misc" not in text
    assert "# Community" not in text


def test_item_line_inlines_summary_between_title_and_source():
    text = render_text(
        _digest(cats={"Model": (_item(title="Foo", summary="간결 한 줄", source="OpenAI Blog", url="https://e/foo"),)}),
        run_at=RUN_AT,
    )
    assert "- Foo — 간결 한 줄 (OpenAI Blog) · https://e/foo" in text


def test_empty_summary_omits_em_dash_segment():
    text = render_text(
        _digest(cats={"Paper": (_item(title="bare", summary=""),)}),
        run_at=RUN_AT,
    )
    # When summary is empty (e.g. fallback dump), line collapses to title+source+url only.
    assert "- bare (OpenAI Blog) · https://e/x" in text
    assert "bare —" not in text  # no orphan em-dash


def test_fallback_notice_when_fallback_flag_set():
    text = render_text(
        _digest(cats={"Misc": (_item(),)}, fallback=True),
        run_at=RUN_AT,
    )
    assert "원본 링크 덤프(폴백) 모드" in text


def test_notes_emitted_when_present():
    text = render_text(_digest(notes="추가 메모"), run_at=RUN_AT)
    assert "메모: 추가 메모" in text


def test_failed_sources_footer():
    text = render_text(
        _digest(cats={"Paper": (_item(),)}),
        run_at=RUN_AT,
        failed_sources=["BAIR", "Microsoft Research"],
    )
    assert "(일부 소스 실패: BAIR, Microsoft Research)" in text


def test_failed_sources_omitted_when_empty():
    text = render_text(_digest(cats={"Paper": (_item(),)}), run_at=RUN_AT)
    assert "일부 소스 실패" not in text


def test_render_text_requires_tz_aware_run_at():
    with pytest.raises(ValueError, match="tz-aware"):
        render_text(_digest(), run_at=datetime(2026, 6, 9))


def test_render_text_defaults_run_at_to_now():
    # We just need it not to crash and to produce a date.
    text = render_text(_digest())
    assert "AI 뉴스 다이제스트 — " in text
    assert "(KST)" in text


def test_kst_offset_is_plus_9():
    assert KST.utcoffset(None) == timedelta(hours=9)


def test_category_order_follows_canonical_list():
    full = _digest(
        cats={
            "Model":     (_item(title="m"),),
            "Paper":     (_item(title="p"),),
            "Tool":      (_item(title="t"),),
            "Misc":      (_item(title="o"),),
            "Community": (_item(title="c"),),
        }
    )
    text = render_text(full, run_at=RUN_AT)
    # CATEGORIES order: Model → Paper → Tool → Misc → Community
    indices = [
        text.index("# Model"),
        text.index("# Paper"),
        text.index("# Tool"),
        text.index("# Misc"),
        text.index("# Community"),
    ]
    assert indices == sorted(indices)


# --- ConsoleSender -------------------------------------------------------


def test_console_sender_writes_to_injected_stream():
    buf = io.StringIO()
    sender = ConsoleSender(stream=buf)
    sender.send(_digest(cats={"Model": (_item(title="hello"),)}), run_at=RUN_AT)
    out = buf.getvalue()
    assert "AI 뉴스 다이제스트 — 2026-06-09 (KST)" in out
    assert "# Model" in out
    assert "- hello" in out


def test_console_sender_defaults_to_stdout(capsys):
    sender = ConsoleSender()
    sender.send(_digest(cats={"Paper": (_item(title="paperX"),)}), run_at=RUN_AT)
    captured = capsys.readouterr()
    assert "paperX" in captured.out


def test_console_sender_forwards_failed_sources():
    buf = io.StringIO()
    ConsoleSender(stream=buf).send(
        _digest(cats={"Paper": (_item(),)}),
        run_at=RUN_AT,
        failed_sources=["NVIDIA Blogs"],
    )
    assert "(일부 소스 실패: NVIDIA Blogs)" in buf.getvalue()


def test_console_sender_renders_fallback_digest():
    buf = io.StringIO()
    fb = _digest(
        cats={"Misc": (_item(title="raw1", summary=""),)},
        notes="원본 링크 덤프(폴백)",
        fallback=True,
    )
    ConsoleSender(stream=buf).send(fb, run_at=RUN_AT)
    out = buf.getvalue()
    assert "원본 링크 덤프(폴백) 모드" in out
    assert "raw1" in out
