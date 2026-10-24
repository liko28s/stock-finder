import logging
import time

from .data import SourceError

log = logging.getLogger(__name__)


def classify_ex(snap, th):
    """(signal, trigger) or (None, None). Needs volume confirmation. trigger 'extreme' = RSI extreme or fresh MA
    cross (takes priority); 'momentum' = |1-day move| >= move_pct, only when nothing else fires (so a
    capitulation day with RSI 22 stays an oversold call, not a conflict). move_pct unset disables momentum."""
    t = snap["technicals"]
    if t["volume_ratio"] < th["volume_ratio"]:
        return None, None
    golden = t["sma20_prev"] <= t["sma50_prev"] and t["sma20"] > t["sma50"]
    death = t["sma20_prev"] >= t["sma50_prev"] and t["sma20"] < t["sma50"]
    bull = t["rsi"] <= th["rsi_oversold"] or golden
    bear = t["rsi"] >= th["rsi_overbought"] or death
    if bull != bear:
        return ("pre-bull" if bull else "pre-bear"), "extreme"
    move, r1 = th.get("move_pct"), t.get("ret1d")
    if bull or not move or r1 is None or abs(r1) < move:  # bull and bear both true = conflicting: no call
        return None, None
    return ("pre-bull" if r1 > 0 else "pre-bear"), "momentum"


def classify(snap, th):
    """pre-bull / pre-bear / None."""
    return classify_ex(snap, th)[0]


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
        signal, trigger = classify_ex(snap, th)
        if signal:
            picks.append({"ticker": tk, "signal": signal, "trigger": trigger, "snapshot": snap})
    return picks
