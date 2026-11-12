"""Системный промпт из файла (правка файла — без пересборки) + служебная метка для защиты от утечки промпта."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from app.config import ROOT

CANARY = "CANARY-" + secrets.token_hex(4)
EXAMPLE = ROOT / "prompts" / "system.example.md"
DEFAULT = ROOT / "prompts" / "system.md"
_cache: dict[str, tuple[float, str]] = {}


def _read(path: Path) -> str:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return ""
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    text = path.read_text(encoding="utf-8")
    _cache[str(path)] = (mtime, text)
    return text


def prompt_path(configured: Path | None) -> Path:
    if configured:
        return configured
    return DEFAULT if DEFAULT.exists() else EXAMPLE


def system_prompt(configured: Path | None, channel: str) -> str:
    raw = _read(prompt_path(configured))
    body = re.sub(r"<!--.*?-->", "", raw, flags=re.S).strip()
    body = body.replace("{CHANNEL}", channel or "канала").replace("{CANARY}", CANARY)
    return f"[{CANARY}]\n\n{body}"
