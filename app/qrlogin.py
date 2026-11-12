"""Вход в Telegram по QR-коду (без SMS и кода из приложения).

Docker: docker compose run --rm bot python -m app.qrlogin
На телефоне: Telegram → Настройки → Устройства → Подключить устройство, отсканировать QR.
"""

import asyncio
import getpass

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import load_config


def show(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


async def amain() -> None:
    cfg = load_config()
    client = TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        qr = await client.qr_login()
        while True:
            print("\nTelegram → Настройки → Устройства → Подключить устройство, отсканируйте QR:\n")
            show(qr.url)
            try:
                await qr.wait(timeout=60)
                break
            except asyncio.TimeoutError:
                print("QR устарел, показываю новый…")
                await qr.recreate()
            except SessionPasswordNeededError:
                await client.sign_in(password=getpass.getpass("Облачный пароль (2FA): "))
                break
    me = await client.get_me()
    print(f"сессия готова: {getattr(me, 'username', None) or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(amain())
