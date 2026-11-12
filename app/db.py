"""SQLite-хранилище сообщений канала: текст, автор, дата, полнотекстовый индекс (FTS5, триграммы)."""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

_STOP = frozenset(
    """
    и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
    только ее мне было вот от меня еще ещё нет о из ему теперь когда даже ну вдруг ли
    если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя
    ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без
    будто чего раз тоже себе под будет тогда кто этот этого потому эта эти эту этом
    этой про это какие какой какая какое почему зачем такое такая такие можно при
    после перед между над the and for with from that this
    """.split()
)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS messages (
  chat_id INTEGER NOT NULL,
  msg_id INTEGER NOT NULL,
  date INTEGER NOT NULL,
  sender_id INTEGER,
  sender_name TEXT NOT NULL DEFAULT '',
  topic_id INTEGER,
  reply_to INTEGER,
  text TEXT NOT NULL,
  norm TEXT NOT NULL,
  PRIMARY KEY (chat_id, msg_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  norm, content='messages', content_rowid='rowid', tokenize='trigram case_sensitive 0'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, norm) VALUES (new.rowid, new.norm);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, norm) VALUES ('delete', old.rowid, old.norm);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, norm) VALUES ('delete', old.rowid, old.norm);
  INSERT INTO messages_fts(rowid, norm) VALUES (new.rowid, new.norm);
END;

CREATE TABLE IF NOT EXISTS sync_state (
  chat_id INTEGER PRIMARY KEY,
  last_msg_id INTEGER NOT NULL
);
"""

_UPSERT = """
INSERT INTO messages (chat_id, msg_id, date, sender_id, sender_name, topic_id, reply_to, text, norm)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(chat_id, msg_id) DO UPDATE SET
  date=excluded.date, sender_id=excluded.sender_id, sender_name=excluded.sender_name,
  topic_id=excluded.topic_id, reply_to=excluded.reply_to, text=excluded.text, norm=excluded.norm
"""

_ADVANCE = """
INSERT INTO sync_state (chat_id, last_msg_id) VALUES (?, ?)
ON CONFLICT(chat_id) DO UPDATE SET last_msg_id=MAX(sync_state.last_msg_id, excluded.last_msg_id)
"""


def terms(question: str) -> list[str]:
    found: list[str] = []
    for word in re.findall(r"[0-9a-zа-яё]{3,}", question.casefold()):
        if word in _STOP or word in found:
            continue
        found.append(word)
        if len(found) == 12:
            break
    return found


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._pending = 0
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.conn.commit()
            self.conn.close()

    def commit(self) -> None:
        with self.lock:
            self.conn.commit()
            self._pending = 0

    def last_id(self, chat_id: int) -> int:
        with self.lock:
            row = self.conn.execute("SELECT last_msg_id FROM sync_state WHERE chat_id = ?", (chat_id,)).fetchone()
        return int(row[0]) if row else 0

    def save(self, *, chat_id: int, msg_id: int, date: int = 0, sender_id: int | None = None,
             sender_name: str = "", topic_id: int | None = None, reply_to: int | None = None,
             text: str | None = None) -> None:
        """Сохранить сообщение (если есть текст) и продвинуть курсор синхронизации."""
        with self.lock:
            if text:
                self.conn.execute(_UPSERT, (chat_id, msg_id, date, sender_id, sender_name, topic_id, reply_to,
                                            text, text.casefold()))
            self.conn.execute(_ADVANCE, (chat_id, msg_id))
            self._pending += 1
            if self._pending >= 50:
                self.conn.commit()
                self._pending = 0

    def search(self, question: str, limit: int = 8) -> list[sqlite3.Row]:
        """Быстрый полнотекстовый поиск (FTS5). Для ответов бота используется BM25 из retrieval.py."""
        words = terms(question)
        if not words:
            return []
        match = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
        with self.lock:
            return self.conn.execute(
                """SELECT m.* FROM messages_fts JOIN messages m ON m.rowid = messages_fts.rowid
                   WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts) LIMIT ?""",
                (match, limit),
            ).fetchall()

    def posts(self, since: int = 0, min_chars: int = 1) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                "SELECT chat_id, msg_id, date, sender_name, text FROM messages "
                "WHERE date > ? AND length(text) >= ? ORDER BY date", (since, min_chars),
            ).fetchall()

    def stats(self) -> tuple[int, int]:
        """(сообщений с текстом, максимальный курсор синхронизации)."""
        with self.lock:
            count = int(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
            last = self.conn.execute("SELECT MAX(last_msg_id) FROM sync_state").fetchone()[0]
        return count, int(last or 0)

    def max_date(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT COALESCE(MAX(date), 0) FROM messages").fetchone()[0])
