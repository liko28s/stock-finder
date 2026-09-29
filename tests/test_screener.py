import logging
import time

from stockfinder.data import SourceError
from stockfinder.screener import classify, screen

TH = {"rsi_oversold": 30, "rsi_overbought": 70, "volume_ratio": 1.5, "ttl_seconds": 900}


def snap(rsi=50, vol=2.0, s20=10, s50=11, p20=10, p50=11, age=0):
    return {"ticker": "X", "source": "finnhub", "fetched_at": time.time() - age, "fundamentals": {},
            "technicals": {"rsi": rsi, "volume_ratio": vol, "sma20": s20, "sma50": s50,
                           "sma20_prev": p20, "sma50_prev": p50, "close": 1}}


def test_oversold_with_volume_is_pre_bull():
    assert classify(snap(rsi=25), TH) == "pre-bull"


def test_overbought_with_volume_is_pre_bear():
    assert classify(snap(rsi=75), TH) == "pre-bear"


def test_golden_cross_is_pre_bull():
    assert classify(snap(s20=12, s50=11, p20=10.5, p50=11), TH) == "pre-bull"


def test_death_cross_is_pre_bear():
    assert classify(snap(s20=10, s50=11, p20=11.5, p50=11), TH) == "pre-bear"


def test_low_volume_no_signal():
    assert classify(snap(rsi=25, vol=1.0), TH) is None


def test_conflicting_signals_no_call():
    assert classify(snap(rsi=25, s20=10, s50=11, p20=11.5, p50=11), TH) is None


def test_stale_cache_rejected(caplog):
    with caplog.at_level(logging.WARNING):
        assert screen(["X"], lambda t: snap(rsi=25, age=901), TH) == []
    assert "stale" in caplog.text


def test_fresh_data_passes_and_source_failure_logged(caplog):
    def fetch(t):
        if t == "BAD":
            raise SourceError("down")
        return snap(rsi=25)

    with caplog.at_level(logging.WARNING):
        picks = screen(["OK", "BAD"], fetch, TH)
    assert [p["ticker"] for p in picks] == ["OK"] and picks[0]["signal"] == "pre-bull"
    assert "skip BAD" in caplog.text
