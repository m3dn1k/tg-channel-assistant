"""Импорт JSON-выгрузки Telegram Desktop: python -m app.import_json result.json [--vault PATH]"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import ROOT, load_dotenv
from app.db import Store
from app.markdown import import_telegram_export


def main() -> None:
    load_dotenv(ROOT / ".env")
    import os

    parser = argparse.ArgumentParser(description="Импорт JSON-выгрузки Telegram Desktop в SQLite (и Markdown).")
    parser.add_argument("path", type=Path)
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("DATA_DIR", ROOT / "data")) / "channel.db")
    parser.add_argument("--vault", type=Path, default=None, help="папка для Markdown-копии (необязательно)")
    args = parser.parse_args()
    store = Store(args.db)
    try:
        print(import_telegram_export(args.path, store, args.vault))
    finally:
        store.close()


if __name__ == "__main__":
    main()
