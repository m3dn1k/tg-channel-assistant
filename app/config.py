"""Настройки из переменных окружения (.env). Секреты — только там."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CA_FILE = ROOT / "certs" / "russian_trusted_root_ca.pem"
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"
PROVIDERS = ("gigachat", "xai", "ollama", "deepseek")
_OFF = {"off", "none", "no", "false", "0", "-"}


def _env(env: dict, key: str, default: str = "") -> str:
    return (env.get(key) or "").strip() or default


def parse_ids(raw: str) -> frozenset[int]:
    out = set()
    for part in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        if part.strip().lstrip("-").isdigit():
            out.add(int(part))
    return frozenset(out)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    channel: str
    data_dir: Path
    session_name: str = "user"
    bot_token: str = ""
    allowed_user_ids: frozenset[int] = frozenset()
    admin_ids: frozenset[int] = frozenset()
    sync_interval_sec: int = 120
    vault_path: Path | None = None
    prompt_file: Path | None = None
    # ответы
    history_turns: int = 6
    top_k: int = 6
    max_tokens: int = 1500
    temperature: float = 0.5
    # LLM
    llm_provider: str = "ollama"
    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2-Pro"
    gigachat_auth_url: str = GIGACHAT_AUTH_URL
    gigachat_base_url: str = GIGACHAT_BASE_URL
    gigachat_ca_file: Path | None = DEFAULT_CA_FILE
    xai_api_key: str = ""
    xai_model: str = "grok-4"
    xai_base_url: str = "https://api.x.ai/v1"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    @property
    def session_path(self) -> Path:
        return self.data_dir / self.session_name

    @property
    def db_path(self) -> Path:
        return self.data_dir / "channel.db"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"


def from_env(env: dict | None = None, *, require_telegram: bool = True) -> Config:
    e = dict(os.environ if env is None else env)
    if require_telegram:
        missing = [k for k in ("TG_API_ID", "TG_API_HASH", "TG_CHANNEL") if not _env(e, k)]
        if missing:
            raise SystemExit(f"не заданы: {', '.join(missing)} (см. .env.example)")
    token = _env(e, "BOT_TOKEN")
    allowed = parse_ids(_env(e, "ALLOWED_USER_IDS"))
    admins = parse_ids(_env(e, "ADMIN_IDS"))
    if token and not (allowed or admins):
        raise SystemExit("BOT_TOKEN задан, но ALLOWED_USER_IDS и ADMIN_IDS пусты: бот никому не ответит")
    provider = _env(e, "LLM_PROVIDER", "ollama").lower()
    if provider not in PROVIDERS:
        raise SystemExit(f"LLM_PROVIDER={provider}: ожидается одно из {', '.join(PROVIDERS)}")
    need = {"gigachat": "GIGACHAT_AUTH_KEY", "xai": "XAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(provider)
    if need and not _env(e, need):
        raise SystemExit(f"LLM_PROVIDER={provider} требует {need}")
    vault = _env(e, "VAULT_PATH")
    prompt = _env(e, "PROMPT_FILE")
    ca = _env(e, "GIGACHAT_CA_FILE")
    data_dir = Path(_env(e, "DATA_DIR", str(ROOT / "data")))
    return Config(
        api_id=int(_env(e, "TG_API_ID", "0")),
        api_hash=_env(e, "TG_API_HASH"),
        channel=_env(e, "TG_CHANNEL"),
        data_dir=data_dir,
        session_name=_env(e, "TG_SESSION", "user"),
        bot_token=token,
        allowed_user_ids=allowed,
        admin_ids=admins,
        sync_interval_sec=int(_env(e, "SYNC_INTERVAL_SEC", "120")),
        vault_path=None if not vault or vault.lower() in _OFF else Path(vault).expanduser(),
        prompt_file=Path(prompt).expanduser() if prompt else None,
        history_turns=int(_env(e, "HISTORY_TURNS", "6")),
        top_k=int(_env(e, "TOP_K", "6")),
        max_tokens=int(_env(e, "MAX_TOKENS", "1500")),
        temperature=float(_env(e, "TEMPERATURE", "0.5")),
        llm_provider=provider,
        gigachat_auth_key=_env(e, "GIGACHAT_AUTH_KEY"),
        gigachat_scope=_env(e, "GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_model=_env(e, "GIGACHAT_MODEL", "GigaChat-2-Pro"),
        gigachat_auth_url=_env(e, "GIGACHAT_AUTH_URL", GIGACHAT_AUTH_URL),
        gigachat_base_url=_env(e, "GIGACHAT_BASE_URL", GIGACHAT_BASE_URL).rstrip("/"),
        gigachat_ca_file=Path(ca).expanduser() if ca else DEFAULT_CA_FILE,
        xai_api_key=_env(e, "XAI_API_KEY"),
        xai_model=_env(e, "XAI_MODEL", "grok-4"),
        xai_base_url=_env(e, "XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/"),
        ollama_url=_env(e, "OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=_env(e, "OLLAMA_MODEL", "qwen3:4b"),
        deepseek_api_key=_env(e, "DEEPSEEK_API_KEY"),
        deepseek_model=_env(e, "DEEPSEEK_MODEL", "deepseek-chat"),
        deepseek_base_url=_env(e, "DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
    )


def load_config() -> Config:
    load_dotenv(ROOT / ".env")
    return from_env()
