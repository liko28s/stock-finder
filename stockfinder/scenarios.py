"""Sample-trade scenarios: what a 10 USD position might return after 1w..6m. The AI shades the numbers; volatility
(vol20, daily % stdev) sets the plausible band so the table can't drift into fantasy. Illustration, not a forecast."""
import math

USD = 10
HORIZONS = {"1w": 5, "2w": 10, "3w": 15, "4w": 20, "2m": 42, "6m": 126}  # trading days
KEYS = ("worst", "expected", "best")
MAX_SIGMA = 3  # validator: anything beyond this band is fantasy


def side(signal):
    return "short" if signal == "pre-bear" else "long"


def sigma_usd(vol20, days):
    """One-sigma P&L in USD for a USD-sized position held `days` trading days."""
    return USD * vol20 * math.sqrt(days) / 100


def prompt_block(pick):
    t = pick["snapshot"]["technicals"]
    vol = t.get("vol20")
    if not vol:
        return ""
    band = ", ".join(f"{h} ±{sigma_usd(vol, d):.2f}" for h, d in HORIZONS.items())
    return f"""

Sample trade: simulate a {USD} USD position opened at the close ({side(pick['signal'])}: long for pre-bull, short for pre-bear).
Add "scenarios": an object keyed by horizon ("1w","2w","3w","4w","2m","6m"), each {{"worst": n, "expected": n, "best": n}}
= profit/loss in USD from the position's point of view (losses negative), worst <= expected <= best.
Daily volatility is {vol:.2f}%, so one standard deviation of P&L per horizon is (USD): {band}.
Keep worst/best within about 2 sigma. Shade "expected" with the signal, confidence, trend (adx, macd, ret20d) and mean-reversion
(zscore20, rsi) evidence: for a weak setup expected stays near 0; a long can lose at most {USD} USD. The receiver uses this to
gauge best and worst cases, so be realistic, not optimistic. Illustration only, not a forecast."""


def clean(scn, snapshot, signal):
    """Validated scenarios dict, or None (never raises: a bad table must not kill a good verdict)."""
    vol = snapshot["technicals"].get("vol20")
    if not vol or not isinstance(scn, dict):
        return None
    out = {}
    for h, d in HORIZONS.items():
        row = scn.get(h)
        if not isinstance(row, dict) or not all(isinstance(row.get(k), (int, float)) and not isinstance(row.get(k), bool)
                                                for k in KEYS):
            return None
        w, e, b = (float(row[k]) for k in KEYS)
        cap = MAX_SIGMA * sigma_usd(vol, d)
        if not w <= e <= b or max(abs(w), abs(b)) > cap or (side(signal) == "long" and w < -USD):
            return None
        out[h] = {"worst": w, "expected": e, "best": b}
    return out


def lines(scn, signal):
    rows = "\n".join(f"{h:>2}  {r['worst']:+.2f} / {r['expected']:+.2f} / {r['best']:+.2f}" for h, r in scn.items())
    return f"💵 {USD} USD sample trade ({side(signal)}), worst / expected / best:\n{rows}\nSimulated, not a forecast."
