"""Ответ на вопрос: защита → поиск по архиву → промпт + история → LLM → вычистка."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from app import guard, llm
from app.config import Config
from app.prompt import system_prompt
from app.retrieval import Passage, Retriever
from app.state import LENGTHS, State

NOTHING = "В архиве канала не нашлось ничего по этому вопросу. Попробуйте переформулировать."


def excerpts(passages: list[Passage]) -> str:
    blocks = []
    for n, p in enumerate(passages, 1):
        date = datetime.fromtimestamp(p.date).strftime("%Y-%m-%d") if p.date else "?"
        blocks.append(f"[{n}] {date}\n{p.text}")
    return "\n\n".join(blocks)


def sources(passages: list[Passage], limit: int = 3) -> str:
    return "\n".join(f"[{n}] {p.link}" for n, p in enumerate(passages[:limit], 1))


class Engine:
    def __init__(self, cfg: Config, retriever: Retriever, state: State,
                 chat: Callable[..., str] | None = None):
        self.cfg, self.retriever, self.state = cfg, retriever, state
        self.chat = chat or (lambda messages, max_tokens, temperature: llm.chat(cfg, messages, max_tokens, temperature))

    def messages(self, uid: int, question: str, passages: list[Passage]) -> list[dict]:
        limit = LENGTHS[self.state.length(uid)]
        system = system_prompt(self.cfg.prompt_file, self.cfg.channel)
        system += f"\n\nОбъём ответа: до {limit} символов."
        history = [{"role": h["role"], "content": h["content"]} for h in self.state.history(uid)]
        user = f"Выдержки:\n\n{excerpts(passages)}\n\nВопрос: {question}"
        return [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]

    def answer(self, uid: int, question: str) -> str:
        question = question.strip()
        if guard.is_probe(question):
            return guard.REFUSAL
        passages = self.retriever.search(question, self.cfg.top_k)
        if not passages:
            return NOTHING
        text = guard.scrub(self.chat(self.messages(uid, question, passages), self.cfg.max_tokens, self.cfg.temperature))
        self.state.remember(uid, question, text)
        if text == guard.REFUSAL:
            return text
        return f"{text}\n\nИсточники:\n{sources(passages)}"
