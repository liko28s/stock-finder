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


TM = {**TH, "move_pct": 5.0}


def mv(r1, **kw):
    s = snap(**kw)
    s["technicals"]["ret1d"] = r1
    return s


def test_big_move_with_volume_is_momentum_pick():
    from stockfinder.screener import classify_ex
    assert classify_ex(mv(8.2), TM) == ("pre-bull", "momentum")
    assert classify_ex(mv(-11.2), TM) == ("pre-bear", "momentum")


def test_momentum_needs_size_volume_and_threshold_set():
    assert classify(mv(4.9), TM) is None  # too small
    assert classify(mv(8.2, vol=1.0), TM) is None  # unconfirmed by volume
    assert classify(mv(8.2), TH) is None  # move_pct unset: feature off


def test_extreme_takes_priority_over_move():
    from stockfinder.screener import classify_ex
    assert classify_ex(mv(-11.0, rsi=22), TM) == ("pre-bull", "extreme")  # capitulation stays an oversold call
    assert classify(mv(8.0, rsi=25, s20=10, s50=11, p20=11.5, p50=11), TM) is None  # conflict still no call


def test_pick_carries_trigger():
    assert screen(["X"], lambda t: mv(8.2), TM)[0]["trigger"] == "momentum"


def test_top_picks_ranks_by_relevance_and_caps(caplog):
    from stockfinder.screener import top_picks
    ps = [{"ticker": t, "score": sc} for t, sc in (("A", 3), ("B", 9), ("C", 5))]
    with caplog.at_level(logging.INFO):
        assert [p["ticker"] for p in top_picks(ps, 2)] == ["B", "C"]
    assert "dropped: A" in caplog.text
    assert len(top_picks(ps, None)) == 3


def test_relevance_prefers_big_volume_backed_moves():
    from stockfinder.screener import relevance
    assert relevance(mv(8.2, vol=3.0)) > relevance(mv(8.2, vol=1.5)) > relevance(mv(5.0, vol=1.5))
    assert relevance(mv(0.5, rsi=22)) > relevance(mv(0.5, rsi=45))  # oversold extreme still ranks
