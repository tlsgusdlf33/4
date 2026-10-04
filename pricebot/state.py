"""가격 기록과 알림 중복 방지 상태 (state/prices.json)."""

from __future__ import annotations

import json
from pathlib import Path


def load(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save(path: str | Path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")
