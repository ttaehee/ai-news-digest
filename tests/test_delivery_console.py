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
    summary=("요점", "배경", "의의"),
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
    assert "# 모델출시" not in text


def test_includes_only_nonempty_categories():
    text = render_text(
        _digest(cats={"모델출시": (_item(),)}), run_at=RUN_AT
    )
    assert "# 모델출시" in text
    assert "# 논문" not in text
    assert "# 툴" not in text
    assert "# 기타" not in text


def test_item_line_includes_title_source_and_url():
    text = render_text(
        _digest(cats={"모델출시": (_item(title="Foo", source="OpenAI Blog", url="https://e/foo"),)}),
        run_at=RUN_AT,
    )
    assert "- Foo (OpenAI Blog) · https://e/foo" in text


def test_summary_lines_indented_and_dotted():
    text = render_text(
        _digest(cats={"논문": (_item(summary=("first", "second", "third")),)}),
        run_at=RUN_AT,
    )
    assert "  · first" in text
    assert "  · second" in text
    assert "  · third" in text


def test_empty_summary_lines_skipped():
    item = _item(summary=("only line", "", ""))
    text = render_text(_digest(cats={"논문": (item,)}), run_at=RUN_AT)
    assert "  · only line" in text
    # exactly one summary bullet, not three
    assert text.count("  · ") == 1


def test_fallback_notice_when_fallback_flag_set():
    text = render_text(
        _digest(cats={"기타": (_item(),)}, fallback=True),
        run_at=RUN_AT,
    )
    assert "원본 링크 덤프(폴백) 모드" in text


def test_notes_emitted_when_present():
    text = render_text(_digest(notes="추가 메모"), run_at=RUN_AT)
    assert "메모: 추가 메모" in text


def test_failed_sources_footer():
    text = render_text(
        _digest(cats={"논문": (_item(),)}),
        run_at=RUN_AT,
        failed_sources=["BAIR", "Microsoft Research"],
    )
    assert "(일부 소스 실패: BAIR, Microsoft Research)" in text


def test_failed_sources_omitted_when_empty():
    text = render_text(_digest(cats={"논문": (_item(),)}), run_at=RUN_AT)
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
            "모델출시": (_item(title="m"),),
            "논문":     (_item(title="p"),),
            "툴":       (_item(title="t"),),
            "기타":     (_item(title="o"),),
        }
    )
    text = render_text(full, run_at=RUN_AT)
    # PLAN §5 order: 모델출시 → 논문 → 툴 → 기타
    assert text.index("# 모델출시") < text.index("# 논문") < text.index("# 툴") < text.index("# 기타")


# --- ConsoleSender -------------------------------------------------------


def test_console_sender_writes_to_injected_stream():
    buf = io.StringIO()
    sender = ConsoleSender(stream=buf)
    sender.send(_digest(cats={"모델출시": (_item(title="hello"),)}), run_at=RUN_AT)
    out = buf.getvalue()
    assert "AI 뉴스 다이제스트 — 2026-06-09 (KST)" in out
    assert "# 모델출시" in out
    assert "- hello" in out


def test_console_sender_defaults_to_stdout(capsys):
    sender = ConsoleSender()
    sender.send(_digest(cats={"논문": (_item(title="paperX"),)}), run_at=RUN_AT)
    captured = capsys.readouterr()
    assert "paperX" in captured.out


def test_console_sender_forwards_failed_sources():
    buf = io.StringIO()
    ConsoleSender(stream=buf).send(
        _digest(cats={"논문": (_item(),)}),
        run_at=RUN_AT,
        failed_sources=["NVIDIA Blogs"],
    )
    assert "(일부 소스 실패: NVIDIA Blogs)" in buf.getvalue()


def test_console_sender_renders_fallback_digest():
    buf = io.StringIO()
    fb = _digest(
        cats={"기타": (_item(title="raw1", summary=("", "", "")),)},
        notes="원본 링크 덤프(폴백)",
        fallback=True,
    )
    ConsoleSender(stream=buf).send(fb, run_at=RUN_AT)
    out = buf.getvalue()
    assert "원본 링크 덤프(폴백) 모드" in out
    assert "raw1" in out
