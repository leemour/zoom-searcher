"""Поиск по корням слов и вывод командной строки."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from zoom_searcher import __version__
from zoom_searcher.cli import main
from zoom_searcher.config import Paths
from zoom_searcher.search import Query, matches, search, stem_word, stems, tokenize

Entries = list[tuple[str, str, str]]

FIRST: Entries = [
    ("00:14:35", "Иван Петров", "Обсудили размер уставного фонда, расшифровка местами врет."),
    ("00:15:08", "Мария Сидорова", "Расшифровка написала капиталда вместо нужного слова."),
    ("00:16:02", "Иван Петров", "Договор аренды пока не подписан."),
    ("00:17:40", "Мария Сидорова", "Бюджет на квартал согласовали."),
    ("00:18:10", "Иван Петров", "Релиз назначили на пятницу."),
    ("00:19:00", "Мария Сидорова", "Тогда закрываем."),
]

SECOND: Entries = [
    ("00:02:11", "Иван Петров", "Бюджет на дизайн вырос вдвое."),
    ("00:03:00", "Иван Петров", "Обещали прислать макеты завтра."),
]

THIRD: Entries = [
    ("00:05:00", "Мария Сидорова", "Бюджет утвердили без правок."),
    ("00:06:30", "Олег Кузнецов", "Тогда закрываем."),
]


def _transcript(meeting: str, when: str, speakers: str, entries: Entries) -> str:
    head = "\n".join(
        [
            f"Встреча: {meeting}",
            f"Дата: {when}",
            "Zoom ID: 12345678901",
            f"Говорят: {speakers}",
            f"Реплик: {len(entries)}",
        ]
    )
    body = "\n\n".join(f"[{at}] {who}: {text}" for at, who, text in entries)
    return f"{head}\n\n{'—' * 40}\n\n{body}\n"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    files = {
        "2026-06-10_1157_Ivan-Maria.txt": _transcript(
            "Иван - Мария", "Jun 10, 2026 11:57 AM", "Иван Петров, Мария Сидорова", FIRST
        ),
        "2026-06-11_1000_Masha-Anna.txt": _transcript(
            "Masha - Anna", "Jun 11, 2026 10:00 AM", "Иван Петров", SECOND
        ),
        "2026-06-12_0900_Team.txt": _transcript(
            "Team", "Jun 12, 2026 09:00 AM", "Мария Сидорова, Олег Кузнецов", THIRD
        ),
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "aliases.json").write_text(
        json.dumps(
            {
                "Иван": ["Иван Петров"],
                "Маша": ["Мария Сидорова", "Masha"],
                "Олег": ["Олег Кузнецов"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


def _find(root: Path, *words: str, **options: Any) -> list[str]:
    hits = search(Paths(root=root), Query(words=words, **options))
    return [hit.entry.text for hit in hits]


def test_stem_word_picks_stemmer_by_script() -> None:
    assert stem_word("Уставного") == "уставн"
    assert stem_word("Deployments") == "deploy"


def test_stems_drops_short_words() -> None:
    assert stems("Мы за бюджет") == {"бюджет"}


def test_matches_exact_and_fuzzy() -> None:
    tokens = tokenize("Обсудили уставный капиталда и договор")

    assert matches("уставный", tokens) is True
    assert matches("капитал", tokens) is True
    assert matches("капитал", tokens, exact=True) is False
    assert matches("рек", tokens) is False


def test_matches_inflection_by_word_prefix() -> None:
    assert matches("устав", tokenize("Обсудили размер уставного фонда")) is True


def test_over_stemmed_word_does_not_drag_in_neighbours() -> None:
    """snowball срезает «устав» до «уста», и сравнение корней тянуло чужие слова."""
    tokens = tokenize("Оборудование устарело, надо установить новое, все устанут")

    assert matches("устав", tokens) is False


def test_finds_word_by_stem(data_dir: Path) -> None:
    assert _find(data_dir, "устав") == ["Обсудили размер уставного фонда, расшифровка местами врет."]


def test_finds_exact_stem_in_strict_mode(data_dir: Path) -> None:
    assert _find(data_dir, "договора", exact=True) == ["Договор аренды пока не подписан."]


def test_fuzzy_finds_garbled_word(data_dir: Path) -> None:
    assert _find(data_dir, "капитал") == ["Расшифровка написала капиталда вместо нужного слова."]


def test_exact_rejects_garbled_word(data_dir: Path) -> None:
    assert _find(data_dir, "капитал", exact=True) == []


def test_all_words_must_share_one_entry(data_dir: Path) -> None:
    assert _find(data_dir, "бюджет", "аренда") == []


def test_any_word_matches_separate_entries(data_dir: Path) -> None:
    found = _find(data_dir, "аренда", "релиз", any_word=True)

    assert found == ["Договор аренды пока не подписан.", "Релиз назначили на пятницу."]


def test_any_word_keeps_files_with_only_the_short_word(tmp_path: Path) -> None:
    (tmp_path / "2026-06-13_1200_Court.txt").write_text(
        _transcript(
            "Court",
            "Jun 13, 2026 12:00 PM",
            "Иван Петров",
            [("00:01:00", "Иван Петров", "Подали иск, договор пока не подписан.")],
        ),
        encoding="utf-8",
    )

    assert _find(tmp_path, "иск", "интеграция", any_word=True) == ["Подали иск, договор пока не подписан."]


def test_near_spreads_words_over_neighbours(data_dir: Path) -> None:
    assert _find(data_dir, "бюджет", "релиз") == []
    assert _find(data_dir, "бюджет", "релиз", near=1) == [
        "Бюджет на квартал согласовали.",
        "Релиз назначили на пятницу.",
    ]


def test_participant_filter_uses_aliases(data_dir: Path) -> None:
    found = _find(data_dir, "бюджет", participants=("Маша",))

    assert found == [
        "Бюджет утвердили без правок.",
        "Бюджет на дизайн вырос вдвое.",
        "Бюджет на квартал согласовали.",
    ]


def test_participant_filter_requires_every_name(data_dir: Path) -> None:
    assert _find(data_dir, "бюджет", participants=("Маша", "Олег")) == ["Бюджет утвердили без правок."]


def test_participant_filter_falls_back_to_bare_name(data_dir: Path) -> None:
    found = _find(data_dir, "бюджет", participants=("Петров",))

    assert found == ["Бюджет на дизайн вырос вдвое.", "Бюджет на квартал согласовали."]


def test_speaker_filter(data_dir: Path) -> None:
    assert _find(data_dir, "расшифровка", speaker="Мария") == [
        "Расшифровка написала капиталда вместо нужного слова."
    ]
    assert _find(data_dir, "расшифровка", speaker="петров") == [
        "Обсудили размер уставного фонда, расшифровка местами врет."
    ]


def test_date_filters(data_dir: Path) -> None:
    assert _find(data_dir, "бюджет", since="2026-06-12") == ["Бюджет утвердили без правок."]
    assert _find(data_dir, "бюджет", until="2026-06-10") == ["Бюджет на квартал согласовали."]


def test_results_are_newest_first(data_dir: Path) -> None:
    hits = search(Paths(root=data_dir), Query(words=("бюджет",)))

    assert [hit.meta.date for hit in hits] == ["2026-06-12", "2026-06-11", "2026-06-10"]


def test_limit_cuts_results(data_dir: Path) -> None:
    assert _find(data_dir, "бюджет", limit=1) == ["Бюджет утвердили без правок."]


def test_nothing_found(data_dir: Path) -> None:
    assert _find(data_dir, "криптовалюта") == []


def test_context_wraps_neighbour_entries(data_dir: Path) -> None:
    hits = search(Paths(root=data_dir), Query(words=("капитал",), context=1))

    assert hits[0].context == (
        "[00:14:35] Иван Петров: Обсудили размер уставного фонда, расшифровка местами врет.",
        "[00:15:08] Мария Сидорова: Расшифровка написала капиталда вместо нужного слова.",
        "[00:16:02] Иван Петров: Договор аренды пока не подписан.",
    )


def test_hit_reports_matched_stems(data_dir: Path) -> None:
    hits = search(Paths(root=data_dir), Query(words=("бюджет",), limit=1))

    assert hits[0].matched == ("бюджет",)
    assert hits[0].as_dict()["meeting"] == "Team"


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["ztx", *argv])
    return main()


def test_cli_prints_hits_without_ansi(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["search", "бюджет", "--dir", str(data_dir)], monkeypatch) == 0

    out = capsys.readouterr().out
    assert "\033[" not in out
    assert "2026-06-12  Team  [00:05:00] Мария Сидорова  (2026-06-12_0900_Team.txt)" in out
    assert "  Бюджет утвердили без правок." in out
    assert out.rstrip().endswith("— 3 совпадений")


def test_cli_highlights_only_in_terminal(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    screen = Terminal()
    monkeypatch.setattr(sys, "stdout", screen)
    assert _run(["search", "бюджет", "--limit", "1", "--dir", str(data_dir)], monkeypatch) == 0

    assert "\033[1m2026-06-12  Team" in screen.getvalue()


def test_cli_json_output(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["search", "капитал", "--json", "--context", "1", "--dir", str(data_dir)], monkeypatch) == 0

    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["speaker"] == "Мария Сидорова"
    assert payload[0]["matched"] == ["капитал"]
    assert len(payload[0]["context"]) == 3


def test_cli_reports_empty_result(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["search", "капитал", "--exact", "--dir", str(data_dir)], monkeypatch) == 0

    assert capsys.readouterr().out.strip() == "ничего не найдено"


def test_cli_passes_every_filter(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "search",
        "бюджет",
        "релиз",
        "--any",
        "--near",
        "1",
        "--with",
        "Маша",
        "--speaker",
        "Мария",
        "--from",
        "2026-06-10",
        "--to",
        "2026-06-10",
        "--limit",
        "5",
        "--dir",
        str(data_dir),
    ]
    assert _run(argv, monkeypatch) == 0

    out = capsys.readouterr().out
    assert "Бюджет на квартал согласовали." in out
    assert "Обсудили размер уставного фонда" not in out
    assert "— 2 совпадений" in out


def test_cli_complains_about_missing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["search", "бюджет", "--dir", str(tmp_path / "нет-такого")], monkeypatch) == 1

    err = capsys.readouterr().err
    assert "ZOOM_SEARCHER_DIR" in err
    assert "ztx pull" in err


def test_cli_version(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_code:
        _run(["--version"], monkeypatch)

    assert exit_code.value.code == 0
    assert __version__ in capsys.readouterr().out
