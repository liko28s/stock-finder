"""Shared snapshot shape + helpers for all data sources."""
import time


class SourceError(Exception):
    """Data source failed or returned unusable data."""


def sma(xs, n):
    if len(xs) < n:
        raise SourceError(f"need {n} points, got {len(xs)}")
    return sum(xs[-n:]) / n


def technicals(closes, volumes, rsi):
    """Derive the indicator set from raw series. Volume ratio = last / avg of prior 20."""
    if len(volumes) < 21:
        raise SourceError("need 21 volume points")
    avg = sum(volumes[-21:-1]) / 20
    return {
        "rsi": rsi,
        "close": closes[-1],
        "sma20": sma(closes, 20),
        "sma50": sma(closes, 50),
        "sma20_prev": sum(closes[-21:-1]) / 20,
        "sma50_prev": sum(closes[-51:-1]) / 50,
        "volume_ratio": volumes[-1] / avg if avg else 0.0,
    }


def snapshot(ticker, source, fundamentals, tech):
    return {"ticker": ticker, "source": source, "fetched_at": time.time(),
            "fundamentals": fundamentals, "technicals": tech}
