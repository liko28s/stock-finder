import logging

import pytest

from stockfinder.config import Config, load

TOML = '[ai]\nbackend = "ollama"\n[thresholds]\nttl_seconds = 5\n'


def _write(tmp_path, toml=TOML):
    p = tmp_path / "config.toml"
    p.write_text(toml)
    return p


def test_loads_toml_and_env(tmp_path):
    env = {"FINNHUB_API_KEY": "fk", "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}
    c = load(_write(tmp_path), env)
    assert isinstance(c, Config)
    assert c.ai["backend"] == "ollama"
    assert c.keys["finnhub"] == "fk"


def test_missing_key_raises(tmp_path):
    with pytest.raises(KeyError, match="FINNHUB_API_KEY"):
        load(_write(tmp_path), {})


def test_keys_not_logged(tmp_path, caplog):
    env = {"FINNHUB_API_KEY": "SECRET123", "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}
    with caplog.at_level(logging.DEBUG):
        c = load(_write(tmp_path), env)
    assert "SECRET123" not in caplog.text
    assert "SECRET123" not in repr(c)
