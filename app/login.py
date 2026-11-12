"""Разовый вход в Telegram по коду: создаёт data/<TG_SESSION>.session и выходит.

Docker: docker compose run --rm bot python -m app.login
"""

import asyncio

from telethon import TelegramClient

from app.config import load_config


async def amain() -> None:
    cfg = load_config()
    client = TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash)
    await client.start()
    me = await client.get_me()
    print(f"сессия готова: {getattr(me, 'username', None) or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(amain())
