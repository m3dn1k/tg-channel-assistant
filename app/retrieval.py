"""BM25 по постам канала из SQLite. Индекс перестраивается, когда в базе появились новые сообщения."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.channel import message_link
from app.db import _STOP

_WORD = re.compile(r"[0-9a-zа-яё]+", re.I)
CHUNK_CHARS = 1200


def tokens(text: str) -> list[str]:
    out = []
    for word in _WORD.findall(text.casefold().replace("ё", "е")):
        if len(word) < 3 or word in _STOP:
            continue
        out.append(word[:6] if len(word) > 6 else word)  # грубый стемминг: обрезка окончаний
    return out


def split(text: str, size: int = CHUNK_CHARS) -> list[str]:
    if len(text) <= size:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) + 2 > size:
            parts.append(cur)
            cur = ""
        while len(para) > size:
            parts.append(para[:size])
            para = para[size:]
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


@dataclass(frozen=True)
class Passage:
    chat_id: int
    msg_id: int
    date: int
    text: str

    @property
    def link(self) -> str:
        return message_link(self.chat_id, self.msg_id)


class Index:
    def __init__(self, passages: list[Passage], k1: float = 1.4, b: float = 0.75):
        self.passages = passages
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(p.text)) for p in passages]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 6) -> list[Passage]:
        q = set(tokens(query))
        if not q or not self.docs:
            return []
        scored = []
        for i, doc in enumerate(self.docs):
            score = 0.0
            for t in q:
                f = doc.get(t)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avg or 1))
                score += self.idf[t] * f * (self.k1 + 1) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        seen, out = set(), []
        for _, i in scored:
            p = self.passages[i]
            if p.msg_id in seen:
                continue
            seen.add(p.msg_id)
            out.append(p)
            if len(out) == k:
                break
        return out


class Retriever:
    def __init__(self, store, min_chars: int = 40):
        self.store = store
        self.min_chars = min_chars
        self._stamp: tuple[int, int] | None = None
        self._index = Index([])

    def index(self) -> Index:
        stamp = self.store.stats()
        if stamp != self._stamp:
            passages = [Passage(r["chat_id"], r["msg_id"], r["date"], chunk)
                        for r in self.store.posts(min_chars=self.min_chars) for chunk in split(r["text"])]
            self._index = Index(passages)
            self._stamp = stamp
        return self._index

    def search(self, query: str, k: int = 6) -> list[Passage]:
        return self.index().search(query, k)
