"""Браузер и эндпоинты Zoom. Вход в аккаунт делает человек, здесь только чтение."""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .models import Meeting

TRANSCRIPTS_URL = "https://zoom.us/recording/meeting/transcript"
LIST_URL = "https://zoom.us/rest/meeting/transcript/user/list"
DOWNLOAD_URL = "https://zoom.us/rest/meeting/transcript/user/download"

# Рядом стоит кнопка удаления, классы те же: ищем строго по data-testid.
DOWNLOAD_BUTTON = 'button[data-testid$=":action:download"]'

CHROME_BINARIES = ("/usr/bin/google-chrome", "google-chrome-stable", "chromium")
MAX_PAGES = 40
PAGE_PAUSE_MS = 200
SETTLE_MS = 3000
CDP_TIMEOUT = 2.0
LAUNCH_TIMEOUT = 30.0

_LIST_JS = """async ([url, page]) => {
  const r = await fetch(`${url}?page=${page}`, { credentials: "include" })
  const j = await r.json()
  return { data: j.result?.data ?? [], hasNext: !!j.result?.hasNextPage, total: j.result?.total ?? 0 }
}"""

_DOWNLOAD_JS = """async ([url, token, meetingId, sortKey]) => {
  const r = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: {
      "content-type": "application/json",
      "accept": "application/json, text/plain, */*",
      "zoom-csrftoken": token,
      "x-requested-with": "XMLHttpRequest, OWASP CSRFGuard Project",
    },
    body: JSON.stringify({ meetingId, sortKey }),
  })
  return { status: r.status, body: await r.text() }
}"""


class ZoomBrowser:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9223") -> None:
        self.cdp_url = cdp_url
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def __enter__(self) -> ZoomBrowser:
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
            contexts = self._browser.contexts
            if not contexts:
                raise RuntimeError(
                    f"Chrome на {self.cdp_url} не открыл ни одного окна. Откройте {TRANSCRIPTS_URL} вручную."
                )
            pages = contexts[0].pages
            self._page = next((p for p in pages if "zoom.us" in p.url), pages[0] if pages else None)
            if self._page is None:
                self._page = contexts[0].new_page()
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self._page = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    @property
    def _live(self) -> Page:
        if self._page is None:
            raise RuntimeError("Браузер не подключен: используйте ZoomBrowser как контекстный менеджер.")
        return self._page

    def open_transcripts(self) -> None:
        page = self._live
        if "/recording/meeting/transcript" not in page.url:
            page.goto(TRANSCRIPTS_URL, wait_until="networkidle")
            page.wait_for_timeout(SETTLE_MS)

    def list_meetings(self) -> list[Meeting]:
        page = self._live
        meetings: list[Meeting] = []
        for number in range(1, MAX_PAGES + 1):
            answer: dict[str, Any] = page.evaluate(_LIST_JS, [LIST_URL, number])
            meetings.extend(_meeting(row) for row in answer.get("data", []))
            if not answer.get("hasNext"):
                break
            page.wait_for_timeout(PAGE_PAUSE_MS)
        return meetings

    def capture_csrf_token(self) -> str:
        """Токена нет ни в cookie, ни в meta, ни в window — только в заголовке исходящего запроса."""
        page = self._live
        button = page.locator(DOWNLOAD_BUTTON).first
        if button.count() == 0:
            raise RuntimeError(
                "Кнопки скачивания на странице транскриптов нет — нечего перехватывать. "
                f"Проверьте, что {TRANSCRIPTS_URL} открыт и в списке есть доступные записи."
            )
        with page.expect_request(DOWNLOAD_URL) as caught:
            button.click()
        request = caught.value
        token = request.headers.get("zoom-csrftoken") or request.all_headers().get("zoom-csrftoken")
        if not token:
            raise RuntimeError("Zoom не прислал заголовок zoom-csrftoken. Обновите страницу и повторите.")
        return token

    def fetch_transcript(self, token: str, meeting: Meeting) -> tuple[int, str]:
        answer: dict[str, Any] = self._live.evaluate(
            _DOWNLOAD_JS, [DOWNLOAD_URL, token, meeting.meeting_id, meeting.sort_key]
        )
        return int(answer["status"]), str(answer["body"])


def _meeting(row: dict[str, Any]) -> Meeting:
    return Meeting(
        meeting_id=str(row.get("meetingId", "")),
        sort_key=str(row.get("sortKey", "")),
        number=str(row.get("meetingNumber", "")),
        topic=str(row.get("topic", "")),
        created=str(row.get("createTime", "")),
        can_download=bool(row.get("canDownload")),
    )


def launch_chrome(profile_dir: Path, port: int = 9223) -> None:
    """Отдельный профиль обязателен: в общем профиле Chrome молча игнорирует порт отладки."""
    binary = _chrome_binary()
    profile_dir.mkdir(parents=True, exist_ok=True)
    log = profile_dir / "chrome.log"
    with log.open("ab") as sink:
        subprocess.Popen(
            [
                binary,
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={port}",
                "--no-first-run",
                "--no-default-browser-check",
                TRANSCRIPTS_URL,
            ],
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    cdp_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + LAUNCH_TIMEOUT
    while time.monotonic() < deadline:
        if cdp_alive(cdp_url):
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"Chrome не открыл порт отладки {port} за {LAUNCH_TIMEOUT:.0f} секунд. Смотрите {log}."
    )


def cdp_alive(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=CDP_TIMEOUT) as answer:
            return bool(answer.status == 200)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def _chrome_binary() -> str:
    for candidate in CHROME_BINARIES:
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError("Chrome не найден. Установите google-chrome или chromium и повторите.")
