import json

import pytest

from stockfinder import scenarios as sc
from stockfinder.ai import build_prompt, parse_verdict
from stockfinder.data import technicals
from stockfinder.telegram import format_pick
from stockfinder.validate import validate

VOL = 2.0  # daily % stdev
SNAP = {"source": "yahoo", "fundamentals": {"pe": 20.0}, "technicals": {"close": 100.0, "rsi": 27.4, "vol20": VOL}}
PICK = {"ticker": "AAPL", "signal": "pre-bull", "snapshot": SNAP}


def table(scale=0.5, bear=False):
    return {h: {"worst": -scale * sc.sigma_usd(VOL, d), "expected": 0.1 * sc.sigma_usd(VOL, d),
                "best": scale * sc.sigma_usd(VOL, d)} for h, d in sc.HORIZONS.items()}


def verdict(**kw):
    return {"signal": "pre-bull", "confidence": 0.7, "reasoning": "RSI 27.4", "cited_metrics": {"rsi": 27.4}, **kw}


def test_vol20_in_technicals_and_prompt_has_bands():
    c = [100 + (i % 2) * 2 for i in range(60)]
    assert technicals(c, [1.0] * 60, 50.0)["vol20"] > 0
    p = build_prompt(PICK)
    assert "10 USD" in p and "6m" in p and "long for pre-bull" in p and f"{sc.sigma_usd(VOL, 5):.2f}" in p
    assert "Sample trade" not in build_prompt({**PICK, "snapshot": {**SNAP, "technicals": {"rsi": 27.4}}})  # no vol: no block


def test_parse_keeps_scenarios_and_validate_accepts_in_band():
    v = parse_verdict(json.dumps(verdict(scenarios=table())))
    assert validate(v, SNAP)["scenarios"]["6m"]["best"] > 0


@pytest.mark.parametrize("mutate", [
    lambda t: t["1w"].update(best=99),                 # beyond 3 sigma
    lambda t: t["2m"].update(expected=t["2m"]["best"] + 1),  # not ordered
    lambda t: t.pop("6m"),                             # missing horizon
    lambda t: t["1w"].update(worst="bad"),
])
def test_bad_table_dropped_but_verdict_kept(mutate):
    t = table()
    mutate(t)
    out = validate(verdict(scenarios=t), SNAP)
    assert out["scenarios"] is None and out["signal"] == "pre-bull"


def test_long_cannot_lose_more_than_stake():
    hot = {**SNAP, "technicals": {**SNAP["technicals"], "vol20": 6.0}}
    t = {h: {"worst": -1.9 * sc.sigma_usd(6.0, d), "expected": 0.0, "best": 1.9 * sc.sigma_usd(6.0, d)}
         for h, d in sc.HORIZONS.items()}  # 6m loss ~12.7 USD: inside the 3 sigma band, beyond the stake
    assert sc.clean(t, hot, "pre-bull") is None and sc.clean(t, hot, "pre-bear") is not None


def test_message_shows_table():
    t = sc.clean(table(), SNAP, "pre-bear")
    m = format_pick("AAPL", "pre-bear", "RSI 78", scn=t)
    assert "10 USD sample trade (short)" in m and "\n6m  " in m and "not a forecast" in m
