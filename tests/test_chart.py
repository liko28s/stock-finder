import time

import requests

from stockfinder import chart
from stockfinder.telegram import format_pick

from test_finnhub import Resp

PICK = {"ticker": "BRK-B", "signal": "pre-bull", "snapshot": {"technicals": {"close": 17.42}}}
CANDLES = [{"x": 1000, "o": 1, "h": 2, "l": 0.5, "c": 1.5}, {"x": 2000, "o": 1.5, "h": 3, "l": 1, "c": 2}]


class Http:
    def __init__(self, err=None):
        self.err, self.sent = err, []

    def post(self, url, json, timeout):
        self.sent.append(json)
        return Resp({"url": "https://quickchart.io/chart/render/zf-1"}, err=self.err)


class Yahoo:
    def candles(self, t):
        return CANDLES


def test_links_mark_alert_candle_and_price_and_tradingview_symbol():
    http = Http()
    out = chart.links(PICK, time.time(), Yahoo(), http)
    ann = http.sent[0]["chart"]["options"]["plugins"]["annotation"]["annotations"]
    assert ann["when"]["xMin"] == 2000 and ann["at"]["yMin"] == 17.42  # last candle + alert price level
    assert out["chart"].endswith("zf-1") and "symbol=BRK.B" in out["tradingview"]


def test_chart_failure_keeps_tradingview_and_never_raises():
    out = chart.links(PICK, time.time(), Yahoo(), Http(err=requests.HTTPError("500")))
    assert out["chart"] is None and out["tradingview"]
    out = chart.links(PICK, time.time(), object(), Http())  # candles unavailable
    assert out["chart"] is None


def test_message_shows_time_price_and_links():
    links = {"chart": "https://q/1", "tradingview": "https://tv/1", "when": "2026-10-24 12:14 -05", "price": 17.42}
    t = format_pick("LKQ", "pre-bull", "RSI 22", 0.35, "yahoo", "m", links)
    assert "Alerted 2026-10-24 12:14 -05 @ 17.42" in t and "📈 Chart: https://q/1" in t and "🔗 TradingView: https://tv/1" in t
    assert "📈" not in format_pick("LKQ", "pre-bull", "RSI 22", links={**links, "chart": None})
