"""Имена участников: чтение aliases.json и проверка участия во встрече."""

from __future__ import annotations

import json
from pathlib import Path

from zoom_searcher.aliases import is_participant, load_aliases
from zoom_searcher.config import Paths
from zoom_searcher.models import TranscriptMeta

META = TranscriptMeta(
    file="2026-06-10_1157_Ivan-Maria.txt",
    date="2026-06-10",
    when="Jun 10, 2026 11:57 AM",
    meeting="Иван - Мария",
    speakers=("Иван Петров", "Мария Сидорова"),
    zoom_id="12345678901",
)

ALIASES = {
    "Иван": ["Иван Петров", "iPhone (Иван)"],
    "Маша": ["Мария Сидорова", "Masha", "Galaxy S23"],
}


def _paths(tmp_path: Path, payload: str | None = None) -> Paths:
    if payload is not None:
        (tmp_path / "aliases.json").write_text(payload, encoding="utf-8")
    return Paths(root=tmp_path)


def test_load_aliases_without_file(tmp_path: Path) -> None:
    assert load_aliases(_paths(tmp_path)) == {}


def test_load_aliases_reads_lists(tmp_path: Path) -> None:
    paths = _paths(tmp_path, json.dumps(ALIASES, ensure_ascii=False))

    assert load_aliases(paths) == ALIASES


def test_load_aliases_skips_comment_key(tmp_path: Path) -> None:
    payload = json.dumps(
        {"_комментарий": "так выглядит aliases.example.json", "Иван": ["Иван Петров"]},
        ensure_ascii=False,
    )

    assert load_aliases(_paths(tmp_path, payload)) == {"Иван": ["Иван Петров"]}


def test_load_aliases_survives_broken_json(tmp_path: Path) -> None:
    assert load_aliases(_paths(tmp_path, "{ это не json")) == {}


def test_load_aliases_survives_wrong_root_type(tmp_path: Path) -> None:
    assert load_aliases(_paths(tmp_path, '["Иван"]')) == {}


def test_is_participant_by_alias_in_header() -> None:
    assert is_participant(META, ALIASES, "Иван") is True
    assert is_participant(META, ALIASES, "Маша") is True


def test_is_participant_without_alias_falls_back_to_name() -> None:
    assert is_participant(META, {}, "Петров") is True
    assert is_participant(META, {}, "Кузнецов") is False


def test_is_participant_found_only_in_filename() -> None:
    meta = TranscriptMeta(
        file="2026-06-11_1000_Masha-Anna.txt",
        date="2026-06-11",
        when="Jun 11, 2026 10:00 AM",
        meeting="Masha - Anna",
        speakers=("Иван Петров",),
    )

    assert is_participant(meta, ALIASES, "Маша") is True


def test_is_participant_rejects_stranger() -> None:
    assert is_participant(META, ALIASES, "Олег") is False
