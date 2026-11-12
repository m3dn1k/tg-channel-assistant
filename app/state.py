"""Состояние бота в JSON-файле: история диалога, длина ответов, пользователи, добавленные админом, оценки."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

LENGTHS = {"short": 400, "mid": 900, "long": 1800}


class State:
    def __init__(self, directory: Path, history_turns: int = 6):
        self.path = Path(directory) / "state.json"
        self.turns = history_turns
        self.lock = threading.Lock()
        self.data = {"history": {}, "length": {}, "users": [], "feedback": {"up": 0, "down": 0}, "asked": 0}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # история
    def history(self, uid: int) -> list[dict]:
        return list(self.data["history"].get(str(uid), []))

    def remember(self, uid: int, question: str, answer: str) -> None:
        with self.lock:
            items = self.data["history"].setdefault(str(uid), [])
            items += [{"role": "user", "content": question, "t": int(time.time())},
                      {"role": "assistant", "content": answer}]
            del items[: max(0, len(items) - 2 * self.turns)]
            self.data["asked"] += 1
            self._save()

    def last_question(self, uid: int) -> str | None:
        for item in reversed(self.history(uid)):
            if item["role"] == "user":
                return item["content"]
        return None

    def forget(self, uid: int) -> None:
        with self.lock:
            self.data["history"].pop(str(uid), None)
            self._save()

    # длина ответа
    def length(self, uid: int) -> str:
        return self.data["length"].get(str(uid), "mid")

    def set_length(self, uid: int, value: str) -> None:
        if value not in LENGTHS:
            raise ValueError(value)
        with self.lock:
            self.data["length"][str(uid)] = value
            self._save()

    # пользователи, добавленные админом через /add
    def users(self) -> set[int]:
        return {int(x) for x in self.data["users"]}

    def add_user(self, uid: int) -> None:
        with self.lock:
            if uid not in self.users():
                self.data["users"].append(uid)
                self._save()

    def remove_user(self, uid: int) -> bool:
        with self.lock:
            if uid not in self.users():
                return False
            self.data["users"] = [x for x in self.data["users"] if int(x) != uid]
            self._save()
            return True

    def feedback(self, good: bool) -> None:
        with self.lock:
            self.data["feedback"]["up" if good else "down"] += 1
            self._save()

    def stats(self) -> dict:
        return {"asked": self.data["asked"], "users_with_history": len(self.data["history"]),
                "added_users": len(self.data["users"]), **self.data["feedback"]}
