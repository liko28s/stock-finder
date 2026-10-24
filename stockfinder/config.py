import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED = {}
OPTIONAL = {"alphavantage": "ALPHAVANTAGE_API_KEY", "tg_token": "TELEGRAM_BOT_TOKEN", "tg_chat": "TELEGRAM_CHAT_ID"}


@dataclass
class Config:
    universe: dict
    thresholds: dict
    ai: dict
    keys: dict = field(repr=False)
    feedback: dict = field(default_factory=dict)
    alerts: dict = field(default_factory=dict)  # V6: never in repr/logs


def _dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return {}
    pairs = (l.split("=", 1) for l in p.read_text().splitlines() if "=" in l and not l.startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs if v.strip()}


def load(path="config.toml", env=None) -> Config:
    if env is None:
        env = {**_dotenv(), **os.environ}
    raw = tomllib.loads(Path(path).read_text())
    ai = raw.get("ai", {})
    required = dict(REQUIRED)
    if ai.get("backend", "openrouter") == "openrouter":
        required["openrouter"] = "OPENROUTER_API_KEY"
    keys = {n: env[v] for n, v in required.items() if v in env}
    for n, v in required.items():
        if n not in keys:
            raise KeyError(v)
    keys.update({n: env[v] for n, v in OPTIONAL.items() if v in env})
    return Config(raw.get("universe", {}), raw.get("thresholds", {}), ai, keys, raw.get("feedback", {}), raw.get("alerts", {}))
