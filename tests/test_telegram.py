import pytest
import requests

from stockfinder.telegram import LIMIT, NotifyError, Telegram, format_pick

from test_finnhub import Resp


class FakeHttp:
    def __init__(self, resp=None):
        self.resp, self.calls = resp or Resp({"ok": True}), []

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


def tg(http):
    return Telegram("TOKEN", "42", http)


@pytest.mark.parametrize("signal,reasoning", [
    ("neutral", "RSI 27.4"), ("", "RSI 27.4"), (None, "RSI 27.4"), ("pre-bull", ""), ("pre-bull", "   "), ("pre-bull", None),
])
def test_refuses_without_signal_or_reasoning(signal, reasoning):
    http = FakeHttp()
    with pytest.raises(NotifyError):
        tg(http).send("AAPL", signal, reasoning)
    assert http.calls == []  # nothing left the process


def test_sends_ticker_signal_reasoning():
    http = FakeHttp()
    tg(http).send("AAPL", "pre-bear", "RSI 78.1 overbought", 0.8, "finnhub")
    url, body = http.calls[0]
    assert url.endswith("/botTOKEN/sendMessage") and body["chat_id"] == "42"
    assert all(s in body["text"] for s in ("AAPL", "PRE-BEAR", "RSI 78.1", "80%", "finnhub"))


def test_truncates_to_telegram_limit():
    assert len(format_pick("X", "pre-bull", "a" * 10000)) == LIMIT


def test_failure_does_not_leak_token():
    with pytest.raises(NotifyError) as e:
        tg(FakeHttp(requests.ConnectionError("https://api.telegram.org/botTOKEN/sendMessage"))).send(
            "AAPL", "pre-bull", "RSI 27.4")
    assert "TOKEN" not in str(e.value)


def test_ok_false_raises():
    with pytest.raises(NotifyError):
        tg(FakeHttp(Resp({"ok": False}))).send("AAPL", "pre-bull", "RSI 27.4")
