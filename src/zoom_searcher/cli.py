"""Командная строка ztx: скачать транскрипты и искать по ним."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from zoom_searcher import __version__
from zoom_searcher.config import ENV_DIR, Paths
from zoom_searcher.models import Hit
from zoom_searcher.search import Query, search

_MAX_LINE = 1500
_DEFAULT_CDP = "http://127.0.0.1:9223"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ztx", description="транскрипты встреч Zoom: скачать и найти")
    parser.add_argument("--version", action="version", version=f"ztx {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    finder = commands.add_parser("search", help="поиск по транскриптам по корням слов")
    finder.add_argument("words", nargs="+", help="слова запроса")
    finder.add_argument(
        "--any",
        dest="any_word",
        action="store_true",
        help="достаточно одного слова (по умолчанию нужны все)",
    )
    finder.add_argument(
        "--near",
        type=int,
        default=0,
        metavar="N",
        help="слова могут быть раскиданы по N соседним абзацам",
    )
    finder.add_argument(
        "--exact",
        action="store_true",
        help="строгое совпадение корня, без поправки на кривое распознавание",
    )
    finder.add_argument(
        "--with",
        dest="participants",
        action="append",
        default=[],
        metavar="ИМЯ",
        help="участник встречи (можно повторять, нужны все перечисленные)",
    )
    finder.add_argument("--speaker", metavar="ИМЯ", help="слова сказал именно этот человек")
    finder.add_argument("--from", dest="since", metavar="YYYY-MM-DD", help="встречи не раньше этой даты")
    finder.add_argument("--to", dest="until", metavar="YYYY-MM-DD", help="встречи не позже этой даты")
    finder.add_argument(
        "--context", type=int, default=0, metavar="N", help="показать N реплик вокруг найденной"
    )
    finder.add_argument("--limit", type=int, default=20, metavar="N", help="сколько совпадений показать")
    finder.add_argument("--json", dest="as_json", action="store_true", help="выдать результат в JSON")
    finder.add_argument("--dir", metavar="ПУТЬ", help="каталог транскриптов")
    finder.set_defaults(handler=run_search)

    puller = commands.add_parser("pull", help="скачать из Zoom транскрипты новых встреч")
    puller.add_argument("--cdp", default=_DEFAULT_CDP, metavar="URL", help="адрес отладочного порта Chrome")
    puller.add_argument("--limit", type=int, default=None, metavar="N", help="сколько встреч обработать")
    puller.add_argument("--dir", metavar="ПУТЬ", help="каталог транскриптов")
    puller.add_argument(
        "--no-launch",
        dest="launch",
        action="store_false",
        help="не запускать браузер, подключиться к уже открытому",
    )
    puller.set_defaults(handler=run_pull)

    return parser


def run_search(args: argparse.Namespace) -> int:
    paths = Paths.resolve(args.dir)
    if not paths.transcripts.is_dir():
        print(_no_data_dir(paths), file=sys.stderr)
        return 1

    query = Query(
        words=tuple(args.words),
        any_word=args.any_word,
        near=args.near,
        exact=args.exact,
        participants=tuple(args.participants),
        speaker=args.speaker,
        since=args.since,
        until=args.until,
        context=args.context,
        limit=args.limit,
    )
    hits = search(paths, query)

    if args.as_json:
        print(json.dumps([hit.as_dict() for hit in hits], ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print("ничего не найдено")
        return 0
    for hit in hits:
        _print_hit(hit)
    print(f"\n— {len(hits)} совпадений")
    return 0


def run_pull(args: argparse.Namespace) -> int:
    from zoom_searcher.pull import pull  # playwright нужен только здесь, поиск работает и без него

    paths = Paths.resolve(args.dir)
    report = pull(paths, cdp_url=args.cdp, limit=args.limit, launch=args.launch)
    print(f"в списке: {report.listed}")
    print(f"скачано: {report.saved}")
    print(f"пропущено: {report.skipped}")
    for meeting_id, topic, reason in report.failed:
        print(f"не вышло: {meeting_id} {topic} — {reason}")
    return 1 if report.failed else 0


def main() -> int:
    args = build_parser().parse_args()
    handler: Callable[[argparse.Namespace], int] = args.handler
    return handler(args)


def _print_hit(hit: Hit) -> None:
    head = f"{hit.meta.date}  {hit.meta.meeting}  [{hit.entry.at}] {hit.entry.speaker}"
    print(f"\n{_bold(head)}  ({hit.meta.file})")
    for line in hit.context or (hit.entry.text,):
        print("  " + line[:_MAX_LINE])


def _bold(text: str) -> str:
    """Управляющие последовательности только для терминала: в файле или в конвейере это мусор."""
    return f"\033[1m{text}\033[0m" if sys.stdout.isatty() else text


def _no_data_dir(paths: Paths) -> str:
    return (
        f"каталог транскриптов не найден: {paths.root}\n"
        f"укажите другой ключом --dir или переменной окружения {ENV_DIR}, "
        f"затем скачайте транскрипты командой «ztx pull»"
    )
