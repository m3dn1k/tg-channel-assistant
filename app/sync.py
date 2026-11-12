"""Инкрементальная выгрузка канала через Telethon в SQLite (и, по желанию, в Markdown)."""

from __future__ import annotations

import logging
from pathlib import Path

from telethon import TelegramClient, utils

from app.markdown import write_message

log = logging.getLogger("tg-channel")


def sender_of(msg) -> tuple[int | None, str]:
    sender = msg.sender
    sender_id = getattr(sender, "id", None) if sender is not None else None
    author = (getattr(msg, "post_author", None) or "").strip()
    if author:
        return sender_id, author
    if sender is None:
        return sender_id, ""
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    name = f"{first} {last}".strip()
    return sender_id, name or getattr(sender, "username", None) or getattr(sender, "title", None) or ""


def topic_reply(msg) -> tuple[int | None, int | None]:
    header = msg.reply_to
    if header is None:
        return None, None
    topic = header.reply_to_top_id if getattr(header, "forum_topic", False) else None
    return topic, header.reply_to_msg_id


async def sync_new(client: TelegramClient, store, entity, vault: Path | None = None) -> int:
    """Скачать сообщения новее курсора. Возвращает число новых сообщений с текстом."""
    chat_id = utils.get_peer_id(entity)
    last = store.last_id(chat_id)
    added = seen = 0
    async for msg in client.iter_messages(entity, min_id=last, reverse=True):
        seen += 1
        text = (msg.message or "").strip()
        if not text or msg.action is not None:
            store.save(chat_id=chat_id, msg_id=msg.id)
            continue
        sender_id, sender_name = sender_of(msg)
        topic, reply = topic_reply(msg)
        date = int(msg.date.timestamp()) if msg.date else 0
        store.save(chat_id=chat_id, msg_id=msg.id, date=date, sender_id=sender_id, sender_name=sender_name,
                   topic_id=topic, reply_to=reply, text=text)
        if vault is not None:
            write_message(vault, chat_id=chat_id, msg_id=msg.id, date=date, sender_name=sender_name, text=text)
        added += 1
        if seen % 200 == 0:
            store.commit()
            log.info("просмотрено %s, с текстом %s, последний id %s", seen, added, msg.id)
    store.commit()
    if added:
        log.info("новых сообщений с текстом: %s", added)
    return added
