import time

import requests

from .data import SourceError, snapshot, technicals

BASE = "https://finnhub.io/api/v1"
FUND_KEYS = {"pe": "peTTM", "eps_growth": "epsGrowthTTMYoy", "revenue_growth": "revenueGrowthTTMYoy",
             "net_margin": "netProfitMarginTTM", "beta": "beta", "52w_high": "52WeekHigh", "52w_low": "52WeekLow"}


class Finnhub:
    def __init__(self, key, http=requests):
        self.key, self.http = key, http

    def _get(self, path, **params):
        try:
            r = self.http.get(BASE + path, params={**params, "token": self.key}, timeout=15)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            raise SourceError(f"finnhub {path}: {type(e).__name__}") from e  # no URL: it carries the token

    def constituents(self, index):
        out = self._get("/index/constituents", symbol=index).get("constituents")
        if not out:
            raise SourceError(f"finnhub: no constituents for {index}")
        return out

    def fundamentals(self, ticker):
        m = self._get("/stock/metric", symbol=ticker, metric="all").get("metric") or {}
        f = {k: m[v] for k, v in FUND_KEYS.items() if m.get(v) is not None}
        if not f:
            raise SourceError(f"finnhub: no fundamentals for {ticker}")
        return f

    def technicals(self, ticker):
        now = int(time.time())
        d = self._get("/indicator", symbol=ticker, resolution="D", **{"from": now - 150 * 86400, "to": now},
                      indicator="rsi", indicator_fields='{"timeperiod": 14}')
        if not d.get("rsi") or not d.get("c") or not d.get("v"):
            raise SourceError(f"finnhub: no technicals for {ticker}")
        return technicals(d["c"], d["v"], d["rsi"][-1])

    def snapshot(self, ticker):
        return snapshot(ticker, "finnhub", self.fundamentals(ticker), self.technicals(ticker))
