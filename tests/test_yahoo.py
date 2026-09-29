import time

import pandas as pd
import pytest

from stockfinder.data import SourceError
from stockfinder.yahoo import Yahoo

INFO = {"trailingPE": 21.5, "beta": 1.2, "profitMargins": None, "earningsGrowth": "n/a"}


class FakeTicker:
    def __init__(self, info=INFO, hist=None, err=None):
        self._info, self._hist, self.err = info, hist, err

    @property
    def info(self):
        if self.err:
            raise self.err
        return self._info

    def history(self, period, interval):
        if self.err:
            raise self.err
        return self._hist if self._hist is not None else pd.DataFrame(
            {"Close": [10.0] * 49 + [12.0], "Volume": [100.0] * 20 + [300.0] * 1 + [100.0] * 0 + [100.0] * 29})


def hist(n=60, last_vol=300.0):
    return pd.DataFrame({"Close": [10 + i * 0.1 for i in range(n)], "Volume": [100.0] * (n - 1) + [last_vol]})


def yahoo(**kw):
    return Yahoo(lambda t: FakeTicker(**kw))


def test_snapshot_has_fetched_at_and_shape():
    s = yahoo(hist=hist()).snapshot("AAPL")
    assert s["source"] == "yahoo" and abs(s["fetched_at"] - time.time()) < 5
    assert s["fundamentals"] == {"pe": 21.5, "beta": 1.2}  # None and non-numeric dropped
    assert s["technicals"]["volume_ratio"] == 3.0 and s["technicals"]["rsi"] == 100.0


def test_empty_history_is_source_error():
    with pytest.raises(SourceError):
        yahoo(hist=pd.DataFrame({"Close": [], "Volume": []})).technicals("AAPL")


def test_empty_info_is_source_error():
    with pytest.raises(SourceError):
        yahoo(info={}).fundamentals("AAPL")


def test_scrape_exception_wrapped():
    with pytest.raises(SourceError):
        yahoo(err=RuntimeError("429")).snapshot("AAPL")
