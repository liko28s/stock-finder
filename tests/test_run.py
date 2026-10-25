import logging
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from stockfinder.ai import AIError
from stockfinder.data import SourceError
from stockfinder.run import fetch_with_fallback, run

TH = {"rsi_oversold": 30, "rsi_overbought": 70, "volume_ratio": 1.5, "ttl_seconds": 900}
CFG = SimpleNamespace(universe={"tickers": ["A", "B"]}, thresholds=TH)


def snap(src="finnhub", rsi=25):
    return {"ticker": "X", "source": src, "fetched_at": time.time(), "fundamentals": {"pe": 20.0},
            "technicals": {"rsi": rsi, "volume_ratio": 2.0, "sma20": 1, "sma50": 2, "sma20_prev": 1,
                           "sma50_prev": 2, "close": 1}}


class Src:
    def __init__(self, fail=(), src="finnhub", discovered=()):
        self.fail, self.src, self.discovered = set(fail), src, list(discovered)

    def discover(self, screens):
        return self.discovered

    def snapshot(self, t):
        if t in self.fail or "*" in self.fail:
            raise SourceError(f"{self.src} down")
        return snap(self.src)


class Analyzer:
    def __init__(self, verdict=None, err=None):
        self.verdict, self.err = verdict, err

    def analyze(self, pick):
        if self.err:
            raise self.err
        return self.verdict


class Notifier:
    def __init__(self):
        self.sent = []

    def send_pick(self, pick, verdict):
        self.sent.append(pick["ticker"])
        return 100 + len(self.sent)


GOOD = {"signal": "pre-bull", "confidence": 0.8, "reasoning": "RSI 25 oversold, PE 20", "cited_metrics": {"rsi": 25}}


def test_primary_failure_falls_back_to_alphavantage_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        s = fetch_with_fallback("A", Src(fail={"A"}, src="yahoo"), Src(src="alphavantage"))
    assert s["source"] == "alphavantage"
    assert "primary source failed" in caplog.text


def test_both_sources_down_raises():
    with pytest.raises(SourceError):
        fetch_with_fallback("A", Src(fail={"*"}), Src(fail={"*"}, src="alphavantage"))


def test_no_fallback_configured_raises():
    with pytest.raises(SourceError):
        fetch_with_fallback("A", Src(fail={"*"}), None)


def test_end_to_end_alerts_validated_picks():
    n = Notifier()
    assert run(CFG, Src(), None, Analyzer(GOOD), n) == 2
    assert n.sent == ["A", "B"]


def test_sent_alerts_recorded_for_reaction_matching():
    fb = {"offset": None, "alerts": []}
    run(CFG, Src(), None, Analyzer(GOOD), Notifier(), None, fb)
    assert [(a["id"], a["ticker"], a["signal"]) for a in fb["alerts"]] == [(101, "A", "pre-bull"), (102, "B", "pre-bull")]


def test_only_top_n_picks_reach_the_ai_and_alerted_ones_are_skipped():
    calls = []

    class Counting(Analyzer):
        def analyze(self, pick):
            calls.append(pick["ticker"])
            return super().analyze(pick)

    cfg = SimpleNamespace(universe={"tickers": ["A", "B", "C"]}, thresholds={**TH, "max_picks": 2})
    assert run(cfg, Src(), None, Counting(GOOD), Notifier(), {"A": "pre-bull"}) == 1
    assert len(calls) == 1  # 3 screened, cut to 2, one of those already alerted -> 1 AI call


def test_ai_failure_or_invalid_citation_sends_nothing(caplog):
    n = Notifier()
    with caplog.at_level(logging.WARNING):
        assert run(CFG, Src(), None, Analyzer(err=AIError("boom")), n) == 0
        bad = {**GOOD, "cited_metrics": {"rsi": 99}, "reasoning": "RSI 99"}
        assert run(CFG, Src(), None, Analyzer(bad), n) == 0
    assert n.sent == [] and "verdict unusable" in caplog.text


def test_empty_universe_raises():
    with pytest.raises(ValueError):
        run(SimpleNamespace(universe={"tickers": []}, thresholds=TH), Src(), None, Analyzer(GOOD), Notifier())


def test_universe_unions_discovered():
    from stockfinder.run import build_universe
    cfg = SimpleNamespace(universe={"tickers": ["A", "B"], "screens": ["most_actives"], "max_tickers": 60})
    # B duplicated by discovery, C new, order preserved
    assert build_universe(cfg, Src(discovered=["B", "C"])) == ["A", "B", "C"]


def test_universe_cap_applies():
    from stockfinder.run import build_universe
    cfg = SimpleNamespace(universe={"tickers": ["A"], "screens": ["s"], "max_tickers": 2})
    assert build_universe(cfg, Src(discovered=["B", "C", "D"])) == ["A", "B"]


def test_duplicate_signal_not_resent_across_runs():
    n = Notifier()
    seen = {}
    assert run(CFG, Src(), None, Analyzer(GOOD), n, seen) == 2  # first scan alerts both
    assert run(CFG, Src(), None, Analyzer(GOOD), n, seen) == 0  # same signals: silent
    assert n.sent == ["A", "B"] and seen == {"A": "pre-bull", "B": "pre-bull"}


def test_changed_signal_resends():
    n = Notifier()
    seen = {"A": "pre-bear", "B": "pre-bull"}  # A flipped since last run
    assert run(CFG, Src(), None, Analyzer(GOOD), n, seen) == 1
    assert n.sent == ["A"]


def test_ai_disagreement_sends_nothing():
    n = Notifier()
    assert run(CFG, Src(), None, Analyzer({**GOOD, "signal": "neutral"}), n) == 0


def test_no_trade_api_imported():
    """V5: advisory only. No broker libs or order endpoints anywhere in the package."""
    src = "\n".join(p.read_text() for p in Path("stockfinder").glob("*.py"))
    assert not re.search(r"alpaca|ib_insync|ccxt|robin_hood|place_order|submit_order|/orders", src, re.I)
