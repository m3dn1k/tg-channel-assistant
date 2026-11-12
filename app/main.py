"""Точка входа: фоновая синхронизация канала + бот (если задан BOT_TOKEN)."""

import asyncio
import contextlib
import logging

from telethon import TelegramClient

from app.channel import parse_channel
from app.config import load_config
from app.db import Store
from app.llm import describe
from app.markdown import init_vault
from app.sync import sync_new

log = logging.getLogger("tg-channel")


async def sync_loop(client: TelegramClient, store: Store, channel: str, vault, interval: int) -> None:
    entity = None
    while True:
        try:
            if entity is None:
                entity = await client.get_entity(parse_channel(channel))
                log.info("канал: %s", getattr(entity, "title", None) or channel)
            await sync_new(client, store, entity, vault)
        except Exception:
            log.exception("ошибка синхронизации")
            entity = None
        await asyncio.sleep(interval)


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if cfg.vault_path is not None:
        init_vault(cfg.vault_path)
    store = Store(cfg.db_path)
    log.info("модель: %s", describe(cfg))
    client = TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash)
    await client.start()
    task = asyncio.create_task(sync_loop(client, store, cfg.channel, cfg.vault_path, cfg.sync_interval_sec))
    try:
        if cfg.bot_token:
            from app.bot import run_bot
            await run_bot(store, cfg)
        else:
            log.info("BOT_TOKEN пуст — только синхронизация")
            await task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await client.disconnect()
        store.close()


if __name__ == "__main__":
    asyncio.run(amain())
