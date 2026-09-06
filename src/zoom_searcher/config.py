"""Где лежат данные. В репозитории их нет и быть не должно."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_DIR = "ZOOM_SEARCHER_DIR"
DEFAULT_DIR = "~/.local/share/zoom-searcher"


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path

    @classmethod
    def resolve(cls, override: str | Path | None = None) -> Paths:
        raw = str(override) if override else os.environ.get(ENV_DIR) or DEFAULT_DIR
        return cls(Path(raw).expanduser().resolve())

    @property
    def transcripts(self) -> Path:
        return self.root

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def state(self) -> Path:
        return self.root / ".state"

    @property
    def csrf_token(self) -> Path:
        return self.state / "csrftoken"

    @property
    def aliases(self) -> Path:
        return self.root / "aliases.json"

    @property
    def index(self) -> Path:
        return self.root / "index.tsv"

    @property
    def browser_profile(self) -> Path:
        return self.state / "chrome-profile"

    def ensure(self) -> None:
        for d in (self.root, self.raw, self.state):
            d.mkdir(parents=True, exist_ok=True)
