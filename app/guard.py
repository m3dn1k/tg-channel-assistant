"""Простая защита: попытки вытащить промпт/сменить роль и вычистка служебного из ответа."""

from __future__ import annotations

import re

from app.prompt import CANARY

_PROBE = re.compile(
    r"(систем\w*\s+(промпт|инструкц|сообщени)|твои\s+(инструкц|правила|настройк)|"
    r"(покажи|выведи|повтори|напиши)\s.{0,30}(промпт|инструкц|правила)|"
    r"(забудь|игнорируй|отмени)\s.{0,30}(инструкц|правила|предыдущ)|"
    r"system\s*prompt|ignore\s+(all\s+)?(previous|prior)\s+instructions|developer\s+mode|jailbreak|"
    r"теперь\s+ты\s+\w+|притворись|ты\s+больше\s+не)",
    re.I,
)

REFUSAL = "Про настройки бота не рассказываю. Спросите что-нибудь по материалам канала."


def is_probe(text: str) -> bool:
    return bool(_PROBE.search(text or ""))


def scrub(answer: str) -> str:
    """Убрать служебную метку; если модель начала цитировать промпт — заменить ответ отказом."""
    if CANARY in answer:
        return REFUSAL
    return re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
