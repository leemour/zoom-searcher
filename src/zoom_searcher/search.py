"""Поиск по корням слов: морфология без ИИ, результат отдается человеку или агенту."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

import snowballstemmer

from zoom_searcher.aliases import is_participant, load_aliases
from zoom_searcher.config import Paths
from zoom_searcher.models import Entry, Hit, TranscriptMeta
from zoom_searcher.transcripts import iter_transcripts, load

_WORD = re.compile(r"[\w-]+", re.UNICODE)

_MIN_WORD = 3
_MIN_FUZZY = 4
_PROBE_LEN = 4

_RU = snowballstemmer.stemmer("russian")
_EN = snowballstemmer.stemmer("english")


def stem_word(word: str) -> str:
    """Корень слова: английский стеммер для латиницы, русский для всего остального."""
    lowered = word.lower()
    stemmer = _EN if lowered.isascii() else _RU
    return str(stemmer.stemWord(lowered))


def stems(text: str) -> set[str]:
    """Корни слов текста. Слова короче трех символов смысла не несут."""
    return {stem_word(word) for word in _WORD.findall(text) if len(word) >= _MIN_WORD}


@dataclass(frozen=True, slots=True)
class Tokens:
    """Абзац в двух видах: корни ловят словоизменение, целые слова держат точность."""

    stems: frozenset[str]
    words: frozenset[str]

    def union(self, other: Tokens) -> Tokens:
        return Tokens(self.stems | other.stems, self.words | other.words)


def tokenize(text: str) -> Tokens:
    found = [word.lower() for word in _WORD.findall(text) if len(word) >= _MIN_WORD]
    return Tokens(frozenset(stem_word(word) for word in found), frozenset(found))


def matches(query: str, tokens: Tokens, exact: bool = False) -> bool:
    """Слово запроса нашлось в абзаце.

    Нестрогое сравнение идет по целым словам, а не по корням: snowball срезает у
    «устав» последнюю букву корня до «уста», и сравнение корней притягивало
    «устарел», «установить», «устанут». Сравнение начал слов оставляет «уставный»
    и исковерканное распознаванием «капиталда», но отсекает этот шум.
    """
    lowered = query.lower()
    if stem_word(lowered) in tokens.stems:
        return True
    if exact or len(lowered) < _MIN_FUZZY:
        return False
    return any(
        word.startswith(lowered) or (len(word) >= _MIN_FUZZY and lowered.startswith(word))
        for word in tokens.words
    )


@dataclass(frozen=True, slots=True)
class Query:
    words: tuple[str, ...]
    any_word: bool = False
    near: int = 0
    exact: bool = False
    participants: tuple[str, ...] = ()
    speaker: str | None = None
    since: str | None = None
    until: str | None = None
    context: int = 0
    limit: int = 20


def search(paths: Paths, query: Query) -> list[Hit]:
    """Совпадения от свежих встреч к старым, срезанные по query.limit."""
    aliases = load_aliases(paths) if query.participants else {}
    probes = _probes([stem_word(word) for word in query.words], query.any_word)
    require = any if query.any_word else all

    hits: list[Hit] = []
    for path in iter_transcripts(paths, query.since, query.until):
        if probes:
            raw = path.read_text(encoding="utf-8").lower()
            if not require(probe in raw for probe in probes):
                continue
        meta, entries = load(path)
        if not all(is_participant(meta, aliases, who) for who in query.participants):
            continue
        hits.extend(_scan(meta, entries, query))
    return hits[: query.limit]


def _probes(query_stems: list[str], any_word: bool) -> list[str]:
    """Дешевый отсев файлов до морфологии: snowball только отрезает окончания,
    поэтому начало корня обязано встретиться в тексте как есть.

    Отсев в режиме «хотя бы одно слово» годится, только когда зонд дал каждое слово
    запроса: иначе файл, где нашлось лишь слово покороче, отсеется зря.
    """
    probes = [stem[:_PROBE_LEN] for stem in query_stems if len(stem) >= _PROBE_LEN]
    if any_word and len(probes) != len(query_stems):
        return []
    return probes


def _scan(meta: TranscriptMeta, entries: list[Entry], query: Query) -> Iterator[Hit]:
    pool = [tokenize(entry.text) for entry in entries]
    for index, entry in enumerate(entries):
        if query.speaker and query.speaker.lower() not in entry.speaker.lower():
            continue
        window = pool[index]
        if query.near:
            for near in pool[max(0, index - query.near) : index + query.near + 1]:
                window = window.union(near)
        found = tuple(word for word in query.words if matches(word, window, query.exact))
        if not (found if query.any_word else len(found) == len(query.words)):
            continue
        yield Hit(meta=meta, entry=entry, matched=found, context=_context(entries, index, query.context))


def _context(entries: list[Entry], index: int, size: int) -> tuple[str, ...]:
    if not size:
        return ()
    lo, hi = max(0, index - size), min(len(entries), index + size + 1)
    return tuple(f"[{entry.at}] {entry.speaker}: {entry.text}" for entry in entries[lo:hi])
