"""Shared snapshot shape + helpers for all data sources."""
import time


class SourceError(Exception):
    """Data source failed or returned unusable data."""


def sma(xs, n):
    if len(xs) < n:
        raise SourceError(f"need {n} points, got {len(xs)}")
    return sum(xs[-n:]) / n


def rsi(closes, n=14):
    """Wilder RSI."""
    if len(closes) <= n:
        raise SourceError(f"need {n + 1} closes, got {len(closes)}")
    d = [b - a for a, b in zip(closes, closes[1:])]
    up = sum(max(x, 0) for x in d[:n]) / n
    dn = sum(max(-x, 0) for x in d[:n]) / n
    for x in d[n:]:
        up = (up * (n - 1) + max(x, 0)) / n
        dn = (dn * (n - 1) + max(-x, 0)) / n
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


def ema(xs, n):
    """Series of EMAs seeded with the first value."""
    k, out = 2 / (n + 1), [xs[0]]
    for x in xs[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def _wilder(xs, n):
    """Wilder smoothing: running sum seeded with the first n values."""
    out = [sum(xs[:n])]
    for x in xs[n:]:
        out.append(out[-1] - out[-1] / n + x)
    return out


def atr_adx(highs, lows, closes, n=14):
    """(atr, adx, +di, -di), Wilder. Needs 2n+1 bars."""
    if min(len(highs), len(lows), len(closes)) < 2 * n + 1:
        raise SourceError(f"need {2 * n + 1} bars for ATR/ADX")
    tr, pdm, mdm = [], [], []
    for i in range(1, len(closes)):
        up, dn = highs[i] - highs[i - 1], lows[i - 1] - lows[i]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    t, p, m = _wilder(tr, n), _wilder(pdm, n), _wilder(mdm, n)
    pdi = [100 * a / b if b else 0.0 for a, b in zip(p, t)]
    mdi = [100 * a / b if b else 0.0 for a, b in zip(m, t)]
    dx = [100 * abs(a - b) / (a + b) if a + b else 0.0 for a, b in zip(pdi, mdi)]
    adx = sum(dx[:n]) / n
    for x in dx[n:]:
        adx = (adx * (n - 1) + x) / n
    return t[-1] / n, adx, pdi[-1], mdi[-1]


def extras(closes, volumes, highs=None, lows=None):
    """Optional indicators; each is skipped (not an error) when there is too little history.
    macd*: 12/26/9. obv_slope20: 20-bar OBV change / 20-bar volume, -1..1. ker10: Kaufman efficiency ratio,
    1 = straight-line trend, 0 = noise. zscore20: (close - sma20) / stdev20, the mean-reversion stretch."""
    out, c = {}, closes
    if len(c) >= 35:
        line = [a - b for a, b in zip(ema(c, 12), ema(c, 26))]
        sig = ema(line, 9)
        out.update(macd=line[-1], macd_signal=sig[-1], macd_hist=line[-1] - sig[-1])
    if highs and lows and len(c) >= 29:
        atr, adx, pdi, mdi = atr_adx(highs, lows, c)
        out.update(atr=atr, atr_pct=atr / c[-1] * 100, adx=adx, plus_di=pdi, minus_di=mdi)
    if len(c) >= 21 and len(volumes) == len(c):
        obv = [0.0]
        for i in range(1, len(c)):
            obv.append(obv[-1] + volumes[i] * ((c[i] > c[i - 1]) - (c[i] < c[i - 1])))
        vol = sum(volumes[-20:])
        out["obv_slope20"] = (obv[-1] - obv[-21]) / vol if vol else 0.0
    if len(c) >= 11:
        path = sum(abs(b - a) for a, b in zip(c[-11:], c[-10:]))
        out["ker10"] = abs(c[-1] - c[-11]) / path if path else 0.0
    if len(c) >= 20:
        w = c[-20:]
        m = sum(w) / 20
        sd = (sum((x - m) ** 2 for x in w) / 20) ** 0.5
        out["zscore20"] = (c[-1] - m) / sd if sd else 0.0
    return out


def technicals(closes, volumes, rsi, highs=None, lows=None):
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
        **{f"ret{n}d": (closes[-1] / closes[-1 - n] - 1) * 100 for n in (1, 5, 20)},
        **extras(closes, volumes, highs, lows),
    }


def snapshot(ticker, source, fundamentals, tech):
    return {"ticker": ticker, "source": source, "fetched_at": time.time(),
            "fundamentals": fundamentals, "technicals": tech}
