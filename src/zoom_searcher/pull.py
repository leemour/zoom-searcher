"""Дозабирает новые транскрипты Zoom. Уже скачанное не перекачивает."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from .config import Paths
from .models import Meeting, PullReport, TranscriptMeta
from .vtt import parse_cues, render, slugify, speakers, stamp, to_paragraphs
from .zoom import ZoomBrowser, cdp_alive, launch_chrome

ATTEMPTS = 3
PAUSE = 0.25
RETRY_PAUSE = 1.5
UNAVAILABLE = "Zoom помечает как недоступный для скачивания"
INDEX_COLUMNS = ("date", "when", "topic", "file", "bytes")
HEADER_LINES = 10


def pull(
    paths: Paths,
    *,
    cdp_url: str = "http://127.0.0.1:9223",
    limit: int | None = None,
    launch: bool = True,
) -> PullReport:
    paths.ensure()
    if not cdp_alive(cdp_url):
        if not launch:
            raise RuntimeError(f"Chrome не отвечает по адресу {cdp_url}. Запуск браузера отключен.")
        launch_chrome(paths.browser_profile, _port(cdp_url))

    report = PullReport()
    with ZoomBrowser(cdp_url) as browser:
        browser.open_transcripts()
        meetings = browser.list_meetings()
        if not meetings:
            raise RuntimeError(
                "Zoom вернул пустой список транскриптов. Войдите в аккаунт в открытом окне Chrome "
                "и запустите команду снова."
            )
        if limit is not None:
            meetings = meetings[:limit]
        report.listed = len(meetings)

        token = _token(paths, browser, meetings)
        for meeting in meetings:
            _save_one(paths, browser, token, meeting, report)

    write_index(paths)
    return report


def write_index(paths: Paths) -> None:
    rows: list[tuple[str, ...]] = []
    for path in sorted(paths.transcripts.glob("*.txt")):
        topic, when = _head(path)
        rows.append((path.name[:10], when, topic, path.name, str(path.stat().st_size)))
    rows.sort(key=lambda row: row[0], reverse=True)
    lines = ["\t".join(INDEX_COLUMNS), *("\t".join(row) for row in rows)]
    paths.index.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _save_one(paths: Paths, browser: ZoomBrowser, token: str, meeting: Meeting, report: PullReport) -> None:
    date, clock = stamp(meeting.created)
    base = f"{date}_{clock}_{slugify(meeting.topic)}"
    txt = paths.transcripts / f"{base}.txt"

    if txt.exists():
        report.skipped += 1
        return
    if not meeting.can_download:
        report.failed.append((meeting.topic, meeting.created, UNAVAILABLE))
        return

    vtt = _fetch(browser, token, meeting, report)
    if vtt is None:
        return

    (paths.raw / f"{base}.vtt").write_text(vtt, encoding="utf-8", newline="\n")
    cues = parse_cues(vtt)
    meta = TranscriptMeta(
        file=txt.name,
        date=date,
        when=meeting.created,
        meeting=meeting.topic,
        speakers=tuple(speakers(cues)),
        zoom_id=meeting.number,
    )
    # .txt пишется последним: именно он говорит, что запись забрана целиком.
    txt.write_text(render(meta, to_paragraphs(cues)), encoding="utf-8", newline="\n")
    report.saved += 1
    time.sleep(PAUSE)


def _fetch(browser: ZoomBrowser, token: str, meeting: Meeting, report: PullReport) -> str | None:
    for attempt in range(1, ATTEMPTS + 1):
        status, body = browser.fetch_transcript(token, meeting)
        if status == 200 and body.startswith("WEBVTT"):
            return body
        if attempt == ATTEMPTS:
            report.failed.append((meeting.topic, meeting.created, f"HTTP {status}: {body[:100]}"))
        else:
            time.sleep(RETRY_PAUSE)
    return None


def _token(paths: Paths, browser: ZoomBrowser, meetings: Sequence[Meeting]) -> str:
    cached = paths.csrf_token.read_text(encoding="utf-8").strip() if paths.csrf_token.exists() else ""
    canary = next((m for m in meetings if m.can_download), None)
    if cached:
        if canary is None:
            return cached
        status, body = browser.fetch_transcript(cached, canary)
        if status == 200 and body.startswith("WEBVTT"):
            return cached

    token = browser.capture_csrf_token()
    paths.state.mkdir(parents=True, exist_ok=True)
    paths.csrf_token.write_text(token, encoding="utf-8", newline="\n")
    paths.csrf_token.chmod(0o600)
    return token


def _head(path: Path) -> tuple[str, str]:
    topic = when = ""
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle):
            if line.startswith("Встреча: "):
                topic = line[len("Встреча: ") :].strip()
            elif line.startswith("Дата: "):
                when = line[len("Дата: ") :].strip()
            elif line.startswith("—") or number >= HEADER_LINES:
                break
    return topic.replace("\t", " "), when.replace("\t", " ")


def _port(cdp_url: str) -> int:
    return urlsplit(cdp_url).port or 9223
