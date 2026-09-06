"""Разбор готовых .txt и обход каталога транскриптов."""

from __future__ import annotations

from pathlib import Path

from zoom_searcher.config import Paths
from zoom_searcher.transcripts import iter_transcripts, load

SAMPLE = """Встреча: Иван - Мария
Дата: Jun 10, 2026 11:57 AM
Zoom ID: 12345678901
Говорят: Иван Петров, Мария Сидорова
Реплик: 4

————————————————————————————————————————

[00:14:35] Иван Петров: Обсудили размер уставного капитала.

[00:15:08] Мария Сидорова: Первая строка реплики.
Вторая строка той же реплики.

[00:16:02] Реплика без имени говорящего

[00:17:40] Мария Сидорова: Тогда закрываем встречу.
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_parses_header(tmp_path: Path) -> None:
    meta, _ = load(_write(tmp_path, "2026-06-10_1157_Ivan-Maria.txt", SAMPLE))

    assert meta.file == "2026-06-10_1157_Ivan-Maria.txt"
    assert meta.date == "2026-06-10"
    assert meta.meeting == "Иван - Мария"
    assert meta.when == "Jun 10, 2026 11:57 AM"
    assert meta.zoom_id == "12345678901"
    assert meta.speakers == ("Иван Петров", "Мария Сидорова")


def test_load_parses_entries(tmp_path: Path) -> None:
    _, entries = load(_write(tmp_path, "2026-06-10_1157_Ivan-Maria.txt", SAMPLE))

    assert len(entries) == 4
    assert entries[0].at == "00:14:35"
    assert entries[0].speaker == "Иван Петров"
    assert entries[0].text == "Обсудили размер уставного капитала."
    assert entries[3].text == "Тогда закрываем встречу."


def test_load_keeps_multiline_entry(tmp_path: Path) -> None:
    _, entries = load(_write(tmp_path, "2026-06-10_1157_Ivan-Maria.txt", SAMPLE))

    assert entries[1].text.splitlines() == ["Первая строка реплики.", "Вторая строка той же реплики."]


def test_load_entry_without_speaker(tmp_path: Path) -> None:
    _, entries = load(_write(tmp_path, "2026-06-10_1157_Ivan-Maria.txt", SAMPLE))

    assert entries[2].speaker == ""
    assert entries[2].text == "Реплика без имени говорящего"


def test_load_survives_missing_header(tmp_path: Path) -> None:
    meta, entries = load(_write(tmp_path, "2026-06-10_1157_Solo.txt", "[00:00:01] Кто-то: Привет.\n"))

    assert meta.meeting == ""
    assert meta.speakers == ()
    assert len(entries) == 1


def test_iter_transcripts_newest_first(tmp_path: Path) -> None:
    for name in ("2026-06-10_1157_A.txt", "2026-06-12_0900_B.txt", "2026-06-11_1000_C.txt"):
        _write(tmp_path, name, SAMPLE)
    _write(tmp_path, "заметки.md", "не транскрипт")

    names = [path.name for path in iter_transcripts(Paths(root=tmp_path))]

    assert names == ["2026-06-12_0900_B.txt", "2026-06-11_1000_C.txt", "2026-06-10_1157_A.txt"]


def test_iter_transcripts_filters_by_date(tmp_path: Path) -> None:
    for name in ("2026-06-10_1157_A.txt", "2026-06-12_0900_B.txt", "2026-06-11_1000_C.txt"):
        _write(tmp_path, name, SAMPLE)

    paths = Paths(root=tmp_path)

    assert [p.name for p in iter_transcripts(paths, since="2026-06-11")] == [
        "2026-06-12_0900_B.txt",
        "2026-06-11_1000_C.txt",
    ]
    assert [p.name for p in iter_transcripts(paths, until="2026-06-10")] == ["2026-06-10_1157_A.txt"]
    assert [p.name for p in iter_transcripts(paths, since="2026-06-11", until="2026-06-11")] == [
        "2026-06-11_1000_C.txt"
    ]


LEGACY_NO_BLANK_LINE = """Встреча: Иван - Мария
Дата: Jun 10, 2026 11:57 AM
Zoom ID: 12345678901
Говорят: Иван Петров
Реплик: 1

————————————————————————————————————————
[00:03:41] Иван Петров: Первая реплика встречи.

[00:04:10] Иван Петров: Вторая реплика.
"""


def test_load_keeps_first_entry_glued_to_separator(tmp_path: Path) -> None:
    """Ранние выгрузки писались без пустой строки после разделителя."""
    _, entries = load(_write(tmp_path, "2026-06-10_1157_Ivan-Maria.txt", LEGACY_NO_BLANK_LINE))

    assert [e.text for e in entries] == ["Первая реплика встречи.", "Вторая реплика."]
