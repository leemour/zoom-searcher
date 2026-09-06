"""Имена участников. Zoom подписывает человека именем устройства, поэтому имен бывает несколько."""

from __future__ import annotations

import json
from typing import Any

from zoom_searcher.config import Paths
from zoom_searcher.models import TranscriptMeta


def load_aliases(paths: Paths) -> dict[str, list[str]]:
    """Читает aliases.json из каталога данных. Нет файла, битой записи или ключа-комментария — пропускаем."""
    if not paths.aliases.is_file():
        return {}
    try:
        raw: Any = json.loads(paths.aliases.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: [str(item) for item in value] for key, value in raw.items() if isinstance(value, list)}


def is_participant(meta: TranscriptMeta, aliases: dict[str, list[str]], name: str) -> bool:
    """Человек был на встрече, если любое из имен встречается в шапке встречи или в имени файла."""
    wanted = aliases.get(name) or [name]
    haystack = (", ".join(meta.speakers) + " " + meta.file).lower()
    return any(alias.lower() in haystack for alias in wanted)
