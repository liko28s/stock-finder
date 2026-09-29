import time

import pytest
import requests

from stockfinder.data import SourceError
from stockfinder.finnhub import Finnhub


class Resp:
    def __init__(self, data, err=None):
        self.data, self.err = data, err

    def raise_for_status(self):
        if self.err:
            raise self.err

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        r = self.routes[url.split("/api/v1")[1]]
        if isinstance(r, Exception):
            raise r
        return Resp(r)


SERIES = {"rsi": [40, 55.5], "c": [10.0] * 49 + [12.0], "v": [100] * 20 + [300]}
ROUTES = {
    "/index/constituents": {"constituents": ["AAPL", "MSFT"]},
    "/stock/metric": {"metric": {"peTTM": 20.5, "beta": 1.1}},
    "/indicator": SERIES,
}


def test_snapshot_shape_and_timestamp():
    s = Finnhub("k", FakeHttp(ROUTES)).snapshot("AAPL")
    assert s["source"] == "finnhub" and abs(s["fetched_at"] - time.time()) < 5
    assert s["fundamentals"] == {"pe": 20.5, "beta": 1.1}
    t = s["technicals"]
    assert t["rsi"] == 55.5 and t["volume_ratio"] == 3.0 and t["close"] == 12.0
    assert t["sma20"] > t["sma20_prev"]


def test_constituents():
    assert Finnhub("k", FakeHttp(ROUTES)).constituents("^GSPC") == ["AAPL", "MSFT"]


def test_empty_fundamentals_is_source_error():
    routes = {**ROUTES, "/stock/metric": {"metric": {}}}
    with pytest.raises(SourceError):
        Finnhub("k", FakeHttp(routes)).fundamentals("AAPL")


def test_http_error_wrapped_without_leaking_key():
    routes = {**ROUTES, "/stock/metric": requests.ConnectionError("https://x?token=SECRET")}
    with pytest.raises(SourceError) as e:
        Finnhub("SECRET", FakeHttp(routes)).fundamentals("AAPL")
    assert "SECRET" not in str(e.value)
