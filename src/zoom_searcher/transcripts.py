"""Чтение готовых .txt: шапка встречи и реплики."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from zoom_searcher.config import Paths
from zoom_searcher.models import Entry, TranscriptMeta

_HEADER_FIELDS = (
    ("Встреча: ", "meeting"),
    ("Дата: ", "when"),
    ("Zoom ID: ", "zoom_id"),
    ("Говорят: ", "speakers"),
)

_ENTRY = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s*(?:([^:]{1,60}):\s*)?(.*)$", re.S)

# Ранние выгрузки писались без пустой строки после разделителя, и первая реплика
# приклеивалась к нему. Срезаем разделитель, иначе такие файлы теряют начало встречи.
_SEPARATOR = re.compile(r"\A[\u2014\u2013-]{10,}[^\n]*\n")

_DATE_LEN = 10


def load(path: Path) -> tuple[TranscriptMeta, list[Entry]]:
    """Разбирает готовый транскрипт: шапку встречи и список реплик."""
    text = path.read_text(encoding="utf-8")
    fields = {"meeting": "", "when": "", "zoom_id": "", "speakers": ""}
    for line in text.split("\n"):
        if not line.strip():
            break
        for prefix, key in _HEADER_FIELDS:
            if line.startswith(prefix):
                fields[key] = line[len(prefix) :].strip()

    meta = TranscriptMeta(
        file=path.name,
        date=path.name[:_DATE_LEN],
        when=fields["when"],
        meeting=fields["meeting"],
        speakers=tuple(name.strip() for name in fields["speakers"].split(",") if name.strip()),
        zoom_id=fields["zoom_id"],
    )

    entries = []
    for block in text.split("\n\n"):
        found = _ENTRY.match(_SEPARATOR.sub("", block.strip()))
        if found:
            entries.append(
                Entry(
                    at=found.group(1),
                    speaker=(found.group(2) or "").strip(),
                    text=found.group(3).strip(),
                )
            )
    return meta, entries


def iter_transcripts(paths: Paths, since: str | None = None, until: str | None = None) -> Iterator[Path]:
    """Файлы транскриптов от свежих к старым. Дата встречи — первые символы имени файла."""
    for path in sorted(paths.transcripts.glob("*.txt"), reverse=True):
        date = path.name[:_DATE_LEN]
        if since and date < since:
            continue
        if until and date > until:
            continue
        yield path
