"""Разбор WebVTT и сборка готового .txt. Чистая логика: ни файлов, ни сети."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .models import Cue, Paragraph, TranscriptMeta

RULE = "—" * 60
DASH = "—"
APOSTROPHES = ("'", "\N{RIGHT SINGLE QUOTATION MARK}")

MONTHS = {
    "Jan": "01",
    "Feb": "02",
    "Mar": "03",
    "Apr": "04",
    "May": "05",
    "Jun": "06",
    "Jul": "07",
    "Aug": "08",
    "Sep": "09",
    "Oct": "10",
    "Nov": "11",
    "Dec": "12",
}

_CREATED = re.compile(r"^(\w{3}) (\d{1,2}), (\d{4}) (\d{1,2}):(\d{2}) (AM|PM)$")
_SPEAKER = re.compile(r"^([^:]{1,60}):\s*(.*)$", re.DOTALL)
_DASHES = re.compile(r"-+")


def parse_cues(vtt: str) -> list[Cue]:
    cues: list[Cue] = []
    for block in vtt.replace("\r", "").split("\n\n"):
        lines = [line for line in block.split("\n") if line]
        timing = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if timing == -1:
            continue
        start = lines[timing].split("-->")[0].strip().split(".")[0]
        text = " ".join(lines[timing + 1 :]).strip()
        if not text:
            continue
        named = _SPEAKER.match(text)
        if named:
            cues.append(Cue(start=start, speaker=named.group(1).strip(), text=named.group(2)))
        else:
            cues.append(Cue(start=start, speaker="", text=text))
    return cues


def to_paragraphs(cues: Iterable[Cue]) -> list[Paragraph]:
    """Zoom режет речь на куски в три-восемь слов, и фраза постоянно попадает на стык двух
    кусков. Склейка соседних кусков одного говорящего — то, ради чего поиск потом работает."""
    paragraphs: list[Paragraph] = []
    for cue in cues:
        if paragraphs and paragraphs[-1].speaker == cue.speaker:
            last = paragraphs[-1]
            paragraphs[-1] = Paragraph(start=last.start, speaker=last.speaker, text=f"{last.text} {cue.text}")
        else:
            paragraphs.append(Paragraph(start=cue.start, speaker=cue.speaker, text=cue.text))
    return paragraphs


def speakers(cues: Iterable[Cue]) -> list[str]:
    return list(dict.fromkeys(cue.speaker for cue in cues if cue.speaker))


def render(meta: TranscriptMeta, paragraphs: Sequence[Paragraph]) -> str:
    head = "\n".join(
        (
            f"Встреча: {meta.meeting}",
            f"Дата: {meta.when}",
            f"Zoom ID: {meta.zoom_id}",
            f"Говорят: {', '.join(meta.speakers) or DASH}",
            f"Реплик: {len(paragraphs)}",
        )
    )
    body = "\n\n".join(f"[{p.start}] {p.speaker + ': ' if p.speaker else ''}{p.text}" for p in paragraphs)
    return f"{head}\n\n{RULE}\n\n{body}\n" if body else f"{head}\n\n{RULE}\n"


def stamp(created: str) -> tuple[str, str]:
    parsed = _CREATED.match(created.strip())
    if not parsed:
        return "unknown", "0000"
    month, day, year, hour, minute, meridiem = parsed.groups()
    number = MONTHS.get(month)
    if number is None:
        return "unknown", "0000"
    clock = int(hour) % 12 + (12 if meridiem == "PM" else 0)
    return f"{year}-{number}-{int(day):02d}", f"{clock:02d}{minute}"


def slugify(topic: str) -> str:
    bare = topic
    for mark in APOSTROPHES:
        bare = bare.replace(mark, "")
    dashed = "".join(char if char.isalnum() else "-" for char in bare)
    return _DASHES.sub("-", dashed).strip("-")[:60] or "meeting"
