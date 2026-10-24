import pytest
import requests

from stockfinder.telegram import LIMIT, Console, NotifyError, Telegram, format_pick

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


def test_hashtags_for_search_and_reaction_hint():
    t = format_pick("BRK-B", "pre-bull", "RSI 27.4", 0.7, "yahoo", "some/model:free")
    assert "#BRK_B #pre_bull" in t and "some/model:free" in t and "👍" in t and "👎" in t


def test_send_returns_message_id():
    assert tg(FakeHttp(Resp({"ok": True, "result": {"message_id": 7}}))).send("AAPL", "pre-bull", "RSI 27.4") == 7


def test_send_text_plain_and_failure_safe():
    http = FakeHttp()
    tg(http).send_text("digest")
    assert http.calls[0][1]["text"] == "digest"
    with pytest.raises(NotifyError):
        tg(FakeHttp(Resp({"ok": False}))).send_text("x")


def test_console_prints_pick_and_keeps_v3(capsys):
    pick = {"ticker": "AAPL", "snapshot": {"source": "yahoo"}}
    assert Console().send_pick(pick, {"signal": "pre-bull", "reasoning": "RSI 27.4", "confidence": 0.7}) is None
    out = capsys.readouterr().out
    assert "#AAPL" in out and "RSI 27.4" in out and "React" not in out
    with pytest.raises(NotifyError):
        Console().send_pick(pick, {"signal": "neutral", "reasoning": "x", "confidence": 0.5})
