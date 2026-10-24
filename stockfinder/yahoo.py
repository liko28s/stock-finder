import logging
from itertools import zip_longest
from datetime import datetime, timezone

import yfinance

from .data import SourceError, rsi, snapshot, technicals

log = logging.getLogger(__name__)

FUND_KEYS = {"pe": "trailingPE", "eps_growth": "earningsGrowth", "revenue_growth": "revenueGrowth",
             "net_margin": "profitMargins", "beta": "beta", "52w_high": "fiftyTwoWeekHigh", "52w_low": "fiftyTwoWeekLow"}


class Yahoo:
    def __init__(self, ticker_factory=yfinance.Ticker, screen_fn=yfinance.screen):
        self.ticker = ticker_factory
        self.screen_fn = screen_fn

    def discover(self, screens, count=50):
        """Symbols from Yahoo predefined screens (most_actives etc). One screen failing never aborts the rest."""
        lists = []
        for s in screens:
            try:
                r = self.screen_fn(s, count=count)
            except Exception as e:  # unofficial endpoint: any failure just skips that screen
                log.warning("discover %s: %s", s, type(e).__name__)
                continue
            lists.append([q["symbol"] for q in (r.get("quotes") if isinstance(r, dict) else r) or []
                          if q.get("symbol")])
        # interleave so a max_tickers cap takes the top of every screen, not all of the first one
        return [x for row in zip_longest(*lists) for x in row if x]

    def fundamentals(self, ticker):
        try:
            info = self.ticker(ticker).info or {}
        except Exception as e:  # yfinance raises assorted types on scrape/rate-limit failures
            raise SourceError(f"yahoo info {ticker}: {type(e).__name__}") from e
        f = {k: float(info[v]) for k, v in FUND_KEYS.items() if isinstance(info.get(v), (int, float))}
        if not f:
            raise SourceError(f"yahoo: no fundamentals for {ticker}")
        return f

    def technicals(self, ticker):
        try:
            h = self.ticker(ticker).history(period="1y", interval="1d")
            closes, vols = h["Close"].dropna().tolist(), h["Volume"].dropna().tolist()
            hc = h.dropna(subset=["Close"])  # keep highs/lows aligned with closes
            highs, lows = (hc["High"].tolist(), hc["Low"].tolist()) if {"High", "Low"} <= set(h) else (None, None)
        except Exception as e:
            raise SourceError(f"yahoo history {ticker}: {type(e).__name__}") from e
        if not closes:  # yfinance returns an empty frame instead of raising
            raise SourceError(f"yahoo: no history for {ticker}")
        return technicals(closes, vols, rsi(closes), highs, lows)

    def path(self, ticker, since_ts):
        """Daily bars from the alert day to now: [{date, open, high, low, close}] for post-mortems."""
        start = datetime.fromtimestamp(since_ts, timezone.utc).date().isoformat()
        try:
            h = self.ticker(ticker).history(start=start, interval="1d").dropna(subset=["Close"])
            bars = [{"date": str(i.date()), **{k: round(float(r[c]), 2) for k, c in
                     (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"))}}
                    for i, r in h.iterrows()]
        except Exception as e:
            raise SourceError(f"yahoo path {ticker}: {type(e).__name__}") from e
        if not bars:
            raise SourceError(f"yahoo: no bars for {ticker} since {start}")
        return bars

    def candles(self, ticker, period="3mo"):
        """Daily candles for charting: [{x: epoch ms, o, h, l, c}]."""
        try:
            h = self.ticker(ticker).history(period=period, interval="1d").dropna(subset=["Close"])
            return [{"x": int(i.timestamp() * 1000), "o": float(r["Open"]), "h": float(r["High"]),
                     "l": float(r["Low"]), "c": float(r["Close"])} for i, r in h.iterrows()]
        except Exception as e:
            raise SourceError(f"yahoo candles {ticker}: {type(e).__name__}") from e

    def snapshot(self, ticker):
        return snapshot(ticker, "yahoo", self.fundamentals(ticker), self.technicals(ticker))
