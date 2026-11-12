import json

import pytest

from app import llm
from app.config import from_env

BASE = {"TG_API_ID": "1", "TG_API_HASH": "x", "TG_CHANNEL": "@example_channel"}


def test_ollama_strips_think(monkeypatch):
    cfg = from_env({**BASE, "LLM_PROVIDER": "ollama"})
    seen = {}

    def fake(req, name, ctx=None):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data)
        return {"message": {"content": "<think>x</think> Ответ"}}

    monkeypatch.setattr(llm, "_request", fake)
    assert llm.chat(cfg, [{"role": "user", "content": "привет"}]) == "Ответ"
    assert seen["url"].endswith("/api/chat") and seen["body"]["messages"][0]["content"] == "привет"


def test_xai_openai_compatible(monkeypatch):
    cfg = from_env({**BASE, "LLM_PROVIDER": "xai", "XAI_API_KEY": "test-key"})
    monkeypatch.setattr(llm, "_request", lambda req, name, ctx=None: {"choices": [{"message": {"content": "ок"}}]})
    assert llm.chat(cfg, [{"role": "user", "content": "?"}]) == "ок"


def test_gigachat_token_refresh_on_401(monkeypatch):
    cfg = from_env({**BASE, "LLM_PROVIDER": "gigachat", "GIGACHAT_AUTH_KEY": "dGVzdA=="})
    llm.reset_token()
    calls = []

    def fake(req, name, ctx=None):
        calls.append(name)
        if name == "gigachat oauth":
            return {"access_token": f"tok{len(calls)}", "expires_at": 9_999_999_999_000}
        if calls.count("gigachat") == 1:
            err = llm.LLMError("401")
            err.code = 401
            raise err
        return {"choices": [{"message": {"content": "готово"}}]}

    monkeypatch.setattr(llm, "_request", fake)
    assert llm.chat(cfg, [{"role": "user", "content": "?"}]) == "готово"
    assert calls == ["gigachat oauth", "gigachat", "gigachat oauth", "gigachat"]


def test_empty_answer_raises(monkeypatch):
    cfg = from_env({**BASE, "LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "k"})
    monkeypatch.setattr(llm, "_request", lambda req, name, ctx=None: {"choices": []})
    with pytest.raises(llm.LLMError):
        llm.chat(cfg, [{"role": "user", "content": "?"}])
