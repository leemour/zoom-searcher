"""Типы, общие для скачивания и поиска. Менять только вместе с обеими сторонами."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Cue:
    """Кусок речи из файла WebVTT, как его нарезал Zoom."""

    start: str
    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class Paragraph:
    """Подряд идущие куски одного говорящего, склеенные в реплику."""

    start: str
    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptMeta:
    file: str
    date: str
    when: str
    meeting: str
    speakers: tuple[str, ...] = ()
    zoom_id: str = ""


@dataclass(frozen=True, slots=True)
class Entry:
    """Реплика из готового .txt."""

    at: str
    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class Hit:
    meta: TranscriptMeta
    entry: Entry
    matched: tuple[str, ...]
    context: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.meta.date,
            "when": self.meta.when,
            "meeting": self.meta.meeting,
            "file": self.meta.file,
            "at": self.entry.at,
            "speaker": self.entry.speaker,
            "text": self.entry.text,
            "matched": list(self.matched),
            "context": list(self.context),
        }


@dataclass(frozen=True, slots=True)
class Meeting:
    """Строка из списка транскриптов Zoom."""

    meeting_id: str
    sort_key: str
    number: str
    topic: str
    created: str
    can_download: bool


@dataclass
class PullReport:
    listed: int = 0
    saved: int = 0
    skipped: int = 0
    failed: list[tuple[str, str, str]] = field(default_factory=list)
