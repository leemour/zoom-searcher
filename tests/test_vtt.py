"""Фикстуры придуманы: настоящие транскрипты в репозиторий не попадают."""

from __future__ import annotations

import pytest

from zoom_searcher.models import Cue, Paragraph, TranscriptMeta
from zoom_searcher.vtt import RULE, parse_cues, render, slugify, speakers, stamp, to_paragraphs

SAMPLE = """WEBVTT

1
00:00:01.100 --> 00:00:04.000
Алиса Смирнова: Начнем разбор итогов

2
00:00:04.500 --> 00:00:07.100
Алиса Смирнова: и посмотрим на цифры

3
00:00:07.500 --> 00:00:09.000
Борис Ким: Цифры готовы

4
00:00:09.500 --> 00:00:12.000
запись без имени говорящего
"""


def test_parse_cues_reads_start_speaker_and_text() -> None:
    cues = parse_cues(SAMPLE)
    assert len(cues) == 4
    assert cues[0] == Cue(start="00:00:01", speaker="Алиса Смирнова", text="Начнем разбор итогов")
    assert cues[2] == Cue(start="00:00:07", speaker="Борис Ким", text="Цифры готовы")


def test_parse_cues_ignores_line_endings() -> None:
    assert parse_cues(SAMPLE.replace("\n", "\r\n")) == parse_cues(SAMPLE)


def test_parse_cues_keeps_cue_without_speaker() -> None:
    assert parse_cues(SAMPLE)[3] == Cue(start="00:00:09", speaker="", text="запись без имени говорящего")


def test_parse_cues_joins_multiline_cue() -> None:
    vtt = """WEBVTT

00:01:00.000 --> 00:01:05.000
Алиса: первая строка
вторая строка
"""
    expected = Cue(start="00:01:00", speaker="Алиса", text="первая строка вторая строка")
    assert parse_cues(vtt) == [expected]


def test_parse_cues_skips_blocks_without_timing_or_text() -> None:
    vtt = """WEBVTT

NOTE служебный блок

7
00:02:00.000 --> 00:02:01.000

"""
    assert parse_cues(vtt) == []


def test_parse_cues_returns_nothing_for_garbage() -> None:
    assert parse_cues("") == []


def test_to_paragraphs_merges_consecutive_cues_of_one_speaker() -> None:
    paragraphs = to_paragraphs(parse_cues(SAMPLE))
    assert paragraphs[0] == Paragraph(
        start="00:00:01", speaker="Алиса Смирнова", text="Начнем разбор итогов и посмотрим на цифры"
    )


def test_to_paragraphs_breaks_when_speaker_changes() -> None:
    paragraphs = to_paragraphs(parse_cues(SAMPLE))
    assert [(p.start, p.speaker) for p in paragraphs] == [
        ("00:00:01", "Алиса Смирнова"),
        ("00:00:07", "Борис Ким"),
        ("00:00:09", ""),
    ]


def test_speakers_are_unique_and_keep_order() -> None:
    assert speakers(parse_cues(SAMPLE)) == ["Алиса Смирнова", "Борис Ким"]


def test_speakers_empty_when_nobody_is_named() -> None:
    assert speakers([Cue(start="00:00:01", speaker="", text="текст")]) == []


@pytest.mark.parametrize(
    ("created", "expected"),
    [
        ("Jun 10, 2026 11:57 AM", ("2026-06-10", "1157")),
        ("Jun 10, 2026 01:05 PM", ("2026-06-10", "1305")),
        ("Dec 03, 2025 12:30 AM", ("2025-12-03", "0030")),
        ("Dec 3, 2025 12:30 PM", ("2025-12-03", "1230")),
        ("Jan 1, 2026 09:00 AM", ("2026-01-01", "0900")),
        ("вчера вечером", ("unknown", "0000")),
        ("Foo 10, 2026 11:57 AM", ("unknown", "0000")),
    ],
)
def test_stamp(created: str, expected: tuple[str, str]) -> None:
    assert stamp(created) == expected


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        ("Планерка команды", "Планерка-команды"),
        ("Anna's 1:1 / weekly", "Annas-1-1-weekly"),
        ("Обсуждение «бюджета» — 2026!", "Обсуждение-бюджета-2026"),
        ("   ", "meeting"),
        ("!!!", "meeting"),
        ("я" * 80, "я" * 60),
    ],
)
def test_slugify(topic: str, expected: str) -> None:
    assert slugify(topic) == expected


def test_render_writes_the_agreed_header() -> None:
    meta = TranscriptMeta(
        file="2026-06-10_1157_planerka.txt",
        date="2026-06-10",
        when="Jun 10, 2026 11:57 AM",
        meeting="Планерка",
        speakers=("Алиса Смирнова", "Борис Ким"),
        zoom_id="123 456 7890",
    )
    paragraphs = [
        Paragraph(start="00:14:35", speaker="Алиса Смирнова", text="Начнем разбор итогов"),
        Paragraph(start="00:15:08", speaker="Борис Ким", text="Цифры готовы"),
    ]
    assert render(meta, paragraphs) == (
        "Встреча: Планерка\n"
        "Дата: Jun 10, 2026 11:57 AM\n"
        "Zoom ID: 123 456 7890\n"
        "Говорят: Алиса Смирнова, Борис Ким\n"
        "Реплик: 2\n"
        "\n"
        f"{RULE}\n"
        "\n"
        "[00:14:35] Алиса Смирнова: Начнем разбор итогов\n"
        "\n"
        "[00:15:08] Борис Ким: Цифры готовы\n"
    )


def test_render_marks_missing_speakers_with_a_dash() -> None:
    meta = TranscriptMeta(file="f.txt", date="2026-06-10", when="Jun 10, 2026 11:57 AM", meeting="Планерка")
    body = render(meta, [Paragraph(start="00:00:01", speaker="", text="текст")])
    assert "Говорят: —\n" in body
    assert body.endswith("\n\n[00:00:01] текст\n")


def test_render_without_paragraphs_ends_after_the_rule() -> None:
    meta = TranscriptMeta(file="f.txt", date="2026-06-10", when="Jun 10, 2026 11:57 AM", meeting="Планерка")
    assert render(meta, []).endswith(f"Реплик: 0\n\n{RULE}\n")


def test_rule_is_sixty_em_dashes() -> None:
    assert RULE == "—" * 60
