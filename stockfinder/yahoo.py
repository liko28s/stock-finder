import yfinance

from .data import SourceError, rsi, snapshot, technicals

FUND_KEYS = {"pe": "trailingPE", "eps_growth": "earningsGrowth", "revenue_growth": "revenueGrowth",
             "net_margin": "profitMargins", "beta": "beta", "52w_high": "fiftyTwoWeekHigh", "52w_low": "fiftyTwoWeekLow"}


class Yahoo:
    def __init__(self, ticker_factory=yfinance.Ticker):
        self.ticker = ticker_factory

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
        except Exception as e:
            raise SourceError(f"yahoo history {ticker}: {type(e).__name__}") from e
        if not closes:  # yfinance returns an empty frame instead of raising
            raise SourceError(f"yahoo: no history for {ticker}")
        return technicals(closes, vols, rsi(closes))

    def snapshot(self, ticker):
        return snapshot(ticker, "yahoo", self.fundamentals(ticker), self.technicals(ticker))
