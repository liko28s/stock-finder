"""Chart links for alerts: a QuickChart candlestick image marked at the alert (free, no key) and a TradingView
page for the interactive view. Links are optional: any failure returns None and the alert still goes out."""
import logging
from datetime import datetime

import requests

log = logging.getLogger(__name__)
QUICKCHART = "https://quickchart.io/chart/create"


def tradingview_url(ticker):
    return f"https://www.tradingview.com/chart/?symbol={ticker.replace('-', '.')}&interval=D"


def alert_time(ts):
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def chart_url(ticker, signal, candles, price, ts, http=requests):
    """candles: [{x: ms, o, h, l, c}]. Marks the last candle (the alert day) plus the alert price level."""
    mark = {"borderColor": "blue", "borderWidth": 2, "borderDash": [6, 4], "type": "line"}
    cfg = {"type": "candlestick", "data": {"datasets": [{"label": ticker, "data": candles}]},
           "options": {"plugins": {"legend": {"display": False},
                                   "title": {"display": True, "text": f"#{ticker} {signal} alert {alert_time(ts)} @ {price:.2f}"},
                                   "annotation": {"annotations": {
                                       "when": {**mark, "xMin": candles[-1]["x"], "xMax": candles[-1]["x"]},
                                       "at": {**mark, "yMin": price, "yMax": price}}}}}}
    r = http.post(QUICKCHART, json={"chart": cfg, "version": "3", "width": 800, "height": 450,
                                    "backgroundColor": "white"}, timeout=20)
    r.raise_for_status()
    return r.json()["url"]


def links(pick, ts, yahoo, http=requests):
    """{'chart': url|None, 'tradingview': url, 'when': str, 'price': float} for the alert message."""
    tk, price = pick["ticker"], pick["snapshot"]["technicals"]["close"]
    out = {"tradingview": tradingview_url(tk), "when": alert_time(ts), "price": price, "chart": None}
    try:
        out["chart"] = chart_url(tk, pick["signal"], yahoo.candles(tk), price, ts, http)
    except Exception as e:  # optional extra: never block the alert
        log.warning("%s: chart link skipped (%s)", tk, type(e).__name__)
    return out
