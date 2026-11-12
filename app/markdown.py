"""Необязательная копия канала в Markdown (например, для Obsidian): один файл на сообщение, папки по месяцам.

Импорт JSON-выгрузки Telegram Desktop («Экспорт истории чата» → JSON) — в SQLite и, при желании, сюда же.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.channel import message_link

_HOME = """# Архив канала

Личная выгрузка для поиска и заметок. Не публикуйте её и не включайте облачную синхронизацию,
если у вас нет права распространять содержимое канала.

Сообщения лежат в `Сообщения/ГГГГ-ММ/<id>.md` и перезаписываются при синхронизации — свои заметки
держите в `Заметки/`.
"""


def safe_stem(value: str, limit: int = 80) -> str:
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", value).strip().strip(".")
    return re.sub(r"\s+", " ", stem)[:limit] or "без-имени"


def init_vault(path: Path) -> None:
    for folder in ("Сообщения", "Заметки"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    home = path / "Главная.md"
    if not home.exists():
        home.write_text(_HOME, encoding="utf-8")


def write_message(vault: Path, *, chat_id: int, msg_id: int, date: int, sender_name: str, text: str) -> Path:
    init_vault(vault)
    month = datetime.fromtimestamp(date).strftime("%Y-%m") if date else "без-даты"
    folder = vault / "Сообщения" / month
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["---", "type: telegram-message", f"chat_id: {chat_id}", f"msg_id: {msg_id}"]
    if date:
        lines.append(f"date: {datetime.fromtimestamp(date).isoformat(timespec='minutes')}")
    if sender_name:
        lines.append(f"author: {json.dumps(sender_name, ensure_ascii=False)}")
    lines += [f"source: {message_link(chat_id, msg_id)}", "---", "", text.replace("\x00", ""), ""]
    path = folder / f"{msg_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def plain_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(item if isinstance(item, str) else str(item.get("text") or "")
                       for item in value if isinstance(item, (str, dict)))
    return str(value)


def _export_date(raw: str) -> int:
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()) if raw else 0
    except ValueError:
        return 0


def _export_chat_id(payload: dict) -> int:
    raw = int(payload.get("id") or 0)
    kind = str(payload.get("type") or "")
    if raw > 0 and ("channel" in kind or "supergroup" in kind):
        return int(f"-100{raw}")
    return raw


def import_telegram_export(path: Path, store=None, vault: Path | None = None) -> int:
    """JSON-выгрузка Telegram Desktop → SQLite (store) и/или Markdown (vault). Возвращает число сообщений."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    chat_id = _export_chat_id(payload)
    count = 0
    for msg in payload.get("messages") or []:
        if msg.get("type") != "message":
            continue
        text = plain_text(msg.get("text")).strip()
        if not text:
            continue
        reply = msg.get("reply_to_message_id")
        fields = dict(chat_id=chat_id, msg_id=int(msg["id"]), date=_export_date(str(msg.get("date") or "")),
                      sender_name=str(msg.get("from") or msg.get("actor") or "").strip(), text=text)
        if store is not None:
            store.save(**fields, reply_to=int(reply) if reply else None)
        if vault is not None:
            write_message(vault, **fields)
        count += 1
    if store is not None:
        store.commit()
    return count
