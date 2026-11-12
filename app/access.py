"""Кто может пользоваться ботом: ALLOWED_USER_IDS + ADMIN_IDS из .env и добавленные админом через /add."""

from __future__ import annotations

from app.config import Config
from app.state import State


def is_admin(cfg: Config, uid: int | None) -> bool:
    return uid is not None and uid in cfg.admin_ids


def is_allowed(cfg: Config, state: State, uid: int | None) -> bool:
    if uid is None:
        return False
    return uid in cfg.allowed_user_ids or uid in cfg.admin_ids or uid in state.users()


def parse_user_id(arg: str | None) -> int | None:
    arg = (arg or "").strip()
    return int(arg) if arg.lstrip("-").isdigit() else None
