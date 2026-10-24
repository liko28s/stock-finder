import pytest

from stockfinder import feedback as fb, postmortem as pm
from stockfinder.ai import AIError
from stockfinder.data import SourceError

SNAP = {"fundamentals": {"pe": 20.0}, "technicals": {"close": 100.0, "rsi": 27.4, "volume_ratio": 2.0}}
BARS = [{"date": "2026-10-20", "open": 100, "high": 104, "low": 97, "close": 103},
        {"date": "2026-10-21", "open": 103, "high": 110, "low": 102, "close": 108}]
PM = {"assessment": "good_call", "what_happened": "RSI 27.4 bounced to 110", "adjustments": ["x"], "model": "m"}


def test_excursions_bull_and_bear():
    e = pm.excursions("pre-bull", 100, BARS)
    assert (e["mfe"], e["mfe_day"], e["mae"], e["mae_day"], e["last"]) == (10, "2026-10-21", -3, "2026-10-20", 8)
    e = pm.excursions("pre-bear", 100, BARS)  # falling price is favourable for a bear call
    assert (e["mfe"], e["mae"], e["last"]) == (3, -10, -8)


class Yahoo:
    def path(self, t, ts):
        return BARS

    def technicals(self, t):
        return {"rsi": 55.0}


class An:
    def __init__(self, err=None):
        self.err, self.prompts = err, []

    def postmortem(self, prompt, label):
        if self.err:
            raise self.err
        self.prompts.append(prompt)
        return PM


class Tg:
    def __init__(self):
        self.replies = []

    def reply(self, mid, text):
        self.replies.append((mid, text))
        return 1


def resolved(outcome="tp"):
    s = {"offset": None, "alerts": []}
    fb.record(s, 10, "AAPL", "pre-bull", now=1.8e9, pick={"snapshot": SNAP},
              verdict={"reasoning": "RSI 27.4 oversold", "confidence": 0.8, "model": "m"})
    s["alerts"][0]["outcome"] = outcome
    return s


def test_review_replies_under_alert_with_data_in_prompt_once():
    s, tg, an = resolved(), Tg(), An()
    assert fb.review_resolved(s, tg, Yahoo(), an) == 1
    p = an.prompts[0]
    assert all(x in p for x in ("27.4", "RSI 27.4 oversold", "target hit", "+10.0%", "2026-10-21", '"rsi": 55.0'))
    mid, text = tg.replies[0]
    assert mid == 10 and "#AAPL post-mortem" in text and "good call" in text and "bounced" in text
    assert fb.review_resolved(s, tg, Yahoo(), an) == 0  # already reviewed


@pytest.mark.parametrize("err", [AIError("x"), SourceError("x")])
def test_failure_is_retried_not_lost(err):
    s, tg = resolved("sl"), Tg()
    assert fb.review_resolved(s, tg, Yahoo(), An(err)) == 0 and s["alerts"][0]["postmortem"] is None
    assert fb.review_resolved(s, tg, Yahoo(), An()) == 1


def test_changed_reaction_triggers_new_review():
    s = resolved()
    fb.review_resolved(s, Tg(), Yahoo(), An())
    fb.apply_reactions(s, [{"update_id": 1, "message_reaction": {"chat": {"id": 1}, "message_id": 10,
                                                                 "new_reaction": [{"emoji": "👎"}]}}])
    assert s["alerts"][0]["outcome"] == "sl" and s["alerts"][0]["postmortem"] is None


def test_alert_without_stored_snapshot_skipped():
    s = {"offset": None, "alerts": []}
    fb.record(s, 10, "AAPL", "pre-bull", now=1.0)
    s["alerts"][0]["outcome"] = "tp"
    assert fb.review_resolved(s, Tg(), Yahoo(), An()) == 0
