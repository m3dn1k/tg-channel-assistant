"""LLM-провайдеры по LLM_PROVIDER: gigachat, xai (Grok), ollama, deepseek. Только стандартная библиотека."""

from __future__ import annotations

import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from app.config import Config

_TOKEN_MARGIN_SEC = 60
_token_lock = threading.Lock()
_token: dict = {"value": "", "expires": 0.0, "key": ""}


class LLMError(RuntimeError):
    pass


def describe(cfg: Config) -> str:
    return {
        "gigachat": f"GigaChat, {cfg.gigachat_model}",
        "xai": f"Grok, {cfg.xai_model}",
        "deepseek": f"DeepSeek, {cfg.deepseek_model}",
    }.get(cfg.llm_provider, f"Ollama, {cfg.ollama_model}")


def _request(req: urllib.request.Request, name: str, ctx: ssl.SSLContext | None = None) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        error = LLMError(f"{name} {exc.code}: {detail}")
        error.code = exc.code  # type: ignore[attr-defined]
        raise error from None
    except urllib.error.URLError as exc:
        raise LLMError(f"{name} недоступен: {exc.reason}") from None


def _json_request(url: str, payload: dict, headers: dict) -> urllib.request.Request:
    return urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                  headers={"Content-Type": "application/json", "Accept": "application/json", **headers})


def _content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    return ((choices[0].get("message") or {}).get("content") or "").strip()


# ---------- GigaChat ----------

def _gigachat_ssl(cfg: Config) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # Цепочка Сбера идёт от Russian Trusted Root CA (Минцифры) — публичный корневой сертификат лежит в certs/.
    if cfg.gigachat_ca_file and cfg.gigachat_ca_file.exists():
        ctx.load_verify_locations(cafile=str(cfg.gigachat_ca_file))
    return ctx


def gigachat_token(cfg: Config) -> str:
    with _token_lock:
        now = time.time()
        if _token["value"] and _token["key"] == cfg.gigachat_auth_key and now < _token["expires"] - _TOKEN_MARGIN_SEC:
            return _token["value"]
        req = urllib.request.Request(
            cfg.gigachat_auth_url, method="POST",
            data=urllib.parse.urlencode({"scope": cfg.gigachat_scope}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                     "RqUID": str(uuid.uuid4()), "Authorization": f"Basic {cfg.gigachat_auth_key}"},
        )
        data = _request(req, "gigachat oauth", _gigachat_ssl(cfg))
        value = data.get("access_token") or ""
        if not value:
            raise LLMError("gigachat oauth: в ответе нет access_token")
        raw = data.get("expires_at")
        expires = float(raw) / 1000 if raw else now + 30 * 60
        _token.update(value=value, expires=expires, key=cfg.gigachat_auth_key)
        return value


def reset_token() -> None:
    with _token_lock:
        _token.update(value="", expires=0.0, key="")


def _gigachat(cfg: Config, messages: list[dict], max_tokens: int, temperature: float) -> str:
    payload = {"model": cfg.gigachat_model, "messages": messages, "stream": False,
               "max_tokens": max_tokens, "temperature": temperature}
    url = f"{cfg.gigachat_base_url}/chat/completions"
    ctx = _gigachat_ssl(cfg)
    try:
        data = _request(_json_request(url, payload, {"Authorization": f"Bearer {gigachat_token(cfg)}"}), "gigachat", ctx)
    except LLMError as exc:
        if getattr(exc, "code", None) != 401:
            raise
        reset_token()
        data = _request(_json_request(url, payload, {"Authorization": f"Bearer {gigachat_token(cfg)}"}), "gigachat", ctx)
    return _content(data)


# ---------- OpenAI-совместимые: xAI (Grok), DeepSeek ----------

def _openai_like(base: str, key: str, model: str, name: str, messages: list[dict], max_tokens: int,
                 temperature: float) -> str:
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    return _content(_request(_json_request(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"}), name))


# ---------- Ollama ----------

def _ollama(cfg: Config, messages: list[dict], max_tokens: int, temperature: float) -> str:
    payload = {"model": cfg.ollama_model, "stream": False, "messages": messages,
               "options": {"num_predict": max_tokens, "temperature": temperature}}
    data = _request(_json_request(f"{cfg.ollama_url}/api/chat", payload, {}), "ollama")
    text = (data.get("message") or {}).get("content") or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def chat(cfg: Config, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.5) -> str:
    """messages — [{"role": "system"|"user"|"assistant", "content": "..."}]."""
    if cfg.llm_provider == "gigachat":
        text = _gigachat(cfg, messages, max_tokens, temperature)
    elif cfg.llm_provider == "xai":
        text = _openai_like(cfg.xai_base_url, cfg.xai_api_key, cfg.xai_model, "grok", messages, max_tokens, temperature)
    elif cfg.llm_provider == "deepseek":
        text = _openai_like(cfg.deepseek_base_url, cfg.deepseek_api_key, cfg.deepseek_model, "deepseek", messages,
                            max_tokens, temperature)
    else:
        text = _ollama(cfg, messages, max_tokens, temperature)
    if not text:
        raise LLMError("модель вернула пустой ответ")
    return text
