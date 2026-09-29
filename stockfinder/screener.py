import logging
import time

from .data import SourceError

log = logging.getLogger(__name__)


def classify(snap, th):
    """pre-bull / pre-bear / None. Needs volume confirmation plus RSI extreme or fresh MA cross."""
    t = snap["technicals"]
    if t["volume_ratio"] < th["volume_ratio"]:
        return None
    golden = t["sma20_prev"] <= t["sma50_prev"] and t["sma20"] > t["sma50"]
    death = t["sma20_prev"] >= t["sma50_prev"] and t["sma20"] < t["sma50"]
    bull = t["rsi"] <= th["rsi_oversold"] or golden
    bear = t["rsi"] >= th["rsi_overbought"] or death
    if bull == bear:  # neither, or conflicting signals: no call
        return None
    return "pre-bull" if bull else "pre-bear"


def screen(tickers, fetch, th, now=time.time):
    """fetch(ticker) -> snapshot. V1: snapshots older than ttl_seconds are dropped, never reused."""
    picks = []
    for tk in tickers:
        try:
            snap = fetch(tk)
        except SourceError as e:
            log.warning("skip %s: %s", tk, e)
            continue
        age = now() - snap["fetched_at"]
        if age > th["ttl_seconds"]:
            log.warning("skip %s: stale data (%.0fs > ttl)", tk, age)
            continue
        signal = classify(snap, th)
        if signal:
            picks.append({"ticker": tk, "signal": signal, "snapshot": snap})
    return picks
