"""Explain what happened after an alert once the human reports the outcome (👍 TP / 👎 SL). The model sees the
data at signal time, the original reasoning, and the price path since; excursions are computed here, not by the model."""
import json
from datetime import datetime, timezone

from .ai import AIError, rounded
from .data import SourceError
from .prompts import load as load_prompt

PROMPT = load_prompt("postmortem")  # stockfinder/prompts/postmortem.md

ICON = {"tp": "👍 target hit", "sl": "👎 stop hit"}


def excursions(signal, entry, bars):
    """Percent moves vs entry in the call's direction (bear: price falling is positive). Returns best/worst/last."""
    sign = 1 if signal == "pre-bull" else -1
    pct = lambda px: sign * (px - entry) / entry * 100
    best = max(bars, key=lambda b: pct(b["high"] if sign > 0 else b["low"]))
    worst = min(bars, key=lambda b: pct(b["low"] if sign > 0 else b["high"]))
    return {"mfe": pct(best["high"] if sign > 0 else best["low"]), "mfe_day": best["date"],
            "mae": pct(worst["low"] if sign > 0 else worst["high"]), "mae_day": worst["date"],
            "last": pct(bars[-1]["close"])}


def build_prompt(alert, bars, now_tech):
    snap = alert["snapshot"]
    entry = snap["technicals"]["close"]
    return PROMPT.format(
        ticker=alert["ticker"], signal=alert["signal"], confidence=alert.get("confidence"),
        sent=datetime.fromtimestamp(alert["ts"], timezone.utc).date(), entry=round(entry, 2),
        reasoning=alert.get("reasoning", "n/a"),
        signal_data=json.dumps({"fundamentals": rounded(snap["fundamentals"]), "technicals": rounded(snap["technicals"])}, indent=1),
        outcome=ICON[alert["outcome"]], bars=json.dumps(bars), now_data=json.dumps(rounded(now_tech), indent=1),
        **excursions(alert["signal"], entry, bars))


def analyze(alert, yahoo, analyzer):
    """Raises SourceError/AIError; caller retries next scan."""
    bars = yahoo.path(alert["ticker"], alert["ts"])
    return analyzer.postmortem(build_prompt(alert, bars, yahoo.technicals(alert["ticker"])), alert["ticker"])


def format_message(alert, pm):
    adj = "".join(f"\n• {a}" for a in pm["adjustments"])
    return (f"📊 #{alert['ticker']} post-mortem — {ICON[alert['outcome']]}\n"
            f"Assessment: {pm['assessment'].replace('_', ' ')} (AI: {pm.get('model', 'n/a')})\n\n{pm['what_happened']}"
            + (f"\n\nWorth testing:{adj}" if adj else "") + "\n\nAdvisory only.")
