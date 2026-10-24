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


def relevance(snap):
    """Ranking score: volume ratio x the bigger of the 1-day move (%) and RSI distance from 50 (/4, so RSI 22 ~ 7).
    ponytail: hand-picked blend, tune against 👍/👎 hit rates once there is feedback data."""
    t = snap["technicals"]
    return t["volume_ratio"] * max(abs(t.get("ret1d") or 0.0), abs(t["rsi"] - 50) / 4)


def top_picks(picks, n):
    """Most relevant n picks (n unset = all). Only these get an AI call."""
    ranked = sorted(picks, key=lambda p: p["score"], reverse=True)
    if n and len(ranked) > n:
        log.info("keeping top %d of %d picks, dropped: %s", n, len(ranked), ", ".join(p["ticker"] for p in ranked[n:]))
    return ranked[:n] if n else ranked


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
            picks.append({"ticker": tk, "signal": signal, "trigger": trigger, "score": relevance(snap), "snapshot": snap})
    return picks
