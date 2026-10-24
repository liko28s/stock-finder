import pytest

from stockfinder.alphavantage import AlphaVantage
from stockfinder.data import SourceError, rsi

from test_finnhub import Resp


class FakeHttp:
    def __init__(self, by_function):
        self.by_function = by_function

    def get(self, url, params, timeout):
        return Resp(self.by_function[params["function"]])


def _series(n=60):
    return {f"2026-01-{i + 1:02d}" if i < 31 else f"2026-02-{i - 30:02d}":
            {"2. high": str(10.5 + i * 0.1), "3. low": str(9.5 + i * 0.1), "4. close": str(10 + i * 0.1), "5. volume": "100" if i < n - 1 else "300"} for i in range(n)}


ROUTES = {
    "OVERVIEW": {"PERatio": "18.2", "Beta": "1.3", "ProfitMargin": "None"},
    "TIME_SERIES_DAILY": {"Time Series (Daily)": _series()},
}


def test_snapshot_shape():
    s = AlphaVantage("k", FakeHttp(ROUTES)).snapshot("IBM")
    assert s["source"] == "alphavantage"
    assert s["fundamentals"] == {"pe": 18.2, "beta": 1.3}  # "None" dropped
    assert s["technicals"]["volume_ratio"] == 3.0
    assert s["technicals"]["rsi"] == 100.0  # monotonic uptrend


def test_rate_limit_body_is_source_error():
    routes = {**ROUTES, "OVERVIEW": {"Information": "rate limit reached"}}
    with pytest.raises(SourceError):
        AlphaVantage("k", FakeHttp(routes)).fundamentals("IBM")


def test_rsi_known_values():
    assert rsi([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]) == 100.0
    assert rsi([15 - i for i in range(15)]) == 0.0
    assert 40 < rsi([10, 11] * 10) < 60
