import requests

from .data import SourceError, rsi, snapshot, technicals

URL = "https://www.alphavantage.co/query"
FUND_KEYS = {"pe": "PERatio", "eps_growth": "QuarterlyEarningsGrowthYOY", "revenue_growth": "QuarterlyRevenueGrowthYOY",
             "net_margin": "ProfitMargin", "beta": "Beta", "52w_high": "52WeekHigh", "52w_low": "52WeekLow"}


class AlphaVantage:
    def __init__(self, key, http=requests):
        self.key, self.http = key, http

    def _get(self, **params):
        try:
            r = self.http.get(URL, params={**params, "apikey": self.key}, timeout=15)
            r.raise_for_status()
            d = r.json()
        except (requests.RequestException, ValueError) as e:
            raise SourceError(f"alphavantage {params['function']}: {type(e).__name__}") from e
        if "Note" in d or "Information" in d or "Error Message" in d:  # rate limit / bad symbol arrive as 200
            raise SourceError(f"alphavantage {params['function']}: {next(iter(d.values()))[:80]}")
        return d

    def fundamentals(self, ticker):
        d = self._get(function="OVERVIEW", symbol=ticker)
        f = {}
        for k, v in FUND_KEYS.items():
            try:
                f[k] = float(d[v])
            except (KeyError, ValueError):  # missing or "None"
                pass
        if not f:
            raise SourceError(f"alphavantage: no fundamentals for {ticker}")
        return f

    def technicals(self, ticker):
        d = self._get(function="TIME_SERIES_DAILY", symbol=ticker, outputsize="compact").get("Time Series (Daily)")
        if not d:
            raise SourceError(f"alphavantage: no series for {ticker}")
        days = sorted(d)  # ISO dates, oldest first
        closes = [float(d[k]["4. close"]) for k in days]
        vols = [float(d[k]["5. volume"]) for k in days]
        return technicals(closes, vols, rsi(closes))

    def snapshot(self, ticker):
        return snapshot(ticker, "alphavantage", self.fundamentals(ticker), self.technicals(ticker))
