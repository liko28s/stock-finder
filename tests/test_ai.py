import json

import pytest
import requests

from stockfinder.ai import AIError, Analyzer, build_prompt, parse_verdict

from test_finnhub import Resp

VERDICT = {"signal": "pre-bull", "confidence": 0.7, "reasoning": "RSI 27.4 oversold",
           "cited_metrics": {"rsi": 27.4}}
PICK = {"ticker": "AAPL", "signal": "pre-bull",
        "snapshot": {"source": "finnhub", "fundamentals": {"pe": 20}, "technicals": {"rsi": 27.4}}}
CFG = {"backend": "openrouter", "openrouter_model": "m", "auto_free_models": False, "ollama_model": "l", "ollama_url": "http://localhost:11434"}


class FakeHttp:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout, headers=None):
        self.calls.append((url, json))
        body = globals()["json"].dumps(VERDICT)
        if "openrouter" in url:
            return Resp({"choices": [{"message": {"content": body}}]})
        return Resp({"message": {"content": "```json\n" + body + "\n```"}})


def test_both_backends_return_same_schema():
    out = {}
    for b in ("openrouter", "ollama"):
        http = FakeHttp()
        out[b] = Analyzer({**CFG, "backend": b}, {"openrouter": "k"}, http).analyze(PICK)
        prompts = [c[1]["messages"][0]["content"] for c in http.calls]
        assert prompts == [build_prompt(PICK)]  # same prompt both paths
    out["openrouter"].pop("model")  # openrouter tags which model answered
    assert out["openrouter"] == out["ollama"] == VERDICT


def test_prompt_contains_data():
    p = build_prompt(PICK)
    assert "27.4" in p and "AAPL" in p and "pre-bull" in p


@pytest.mark.parametrize("bad", [
    "not json", "[1]", json.dumps({**VERDICT, "signal": "buy"}), json.dumps({**VERDICT, "confidence": 2}),
    json.dumps({**VERDICT, "confidence": True}), json.dumps({k: v for k, v in VERDICT.items() if k != "reasoning"}),
    json.dumps({**VERDICT, "cited_metrics": [1]}),
])
def test_bad_reply_rejected(bad):
    with pytest.raises(AIError):
        parse_verdict(bad)


def test_unknown_backend():
    with pytest.raises(AIError):
        Analyzer({**CFG, "backend": "x"}, {}, FakeHttp()).analyze(PICK)


class RollHttp:
    """Models listed by id in `bad` answer 429; the rest answer with VERDICT."""

    def __init__(self, bad=(), listing=None):
        self.bad, self.listing, self.used = set(bad), listing, []

    def get(self, url, timeout):
        if self.listing is None:
            raise requests.ConnectionError("down")
        return Resp({"data": self.listing})

    def post(self, url, json, timeout, headers=None):
        self.used.append(json["model"])
        if json["model"] in self.bad:
            return Resp({}, err=requests.HTTPError("429"))
        return Resp({"choices": [{"message": {"content": globals()["json"].dumps(VERDICT)}}]})


def free(i, price="0", params=("response_format",)):
    return {"id": i, "pricing": {"prompt": price, "completion": price}, "supported_parameters": list(params)}


def test_rolls_to_next_free_model_on_failure():
    listing = [free("paid", "0.5"), free("nojson", params=()), free("f1"), free("f2")]
    http = RollHttp(bad={"m", "f1"}, listing=listing)
    v = Analyzer({**CFG, "auto_free_models": True}, {"openrouter": "k"}, http).analyze(PICK)
    assert http.used == ["m", "f1", "f2"] and v["model"] == "f2"  # paid skipped; response_format models ranked before nojson


def test_listing_failure_uses_configured_only():
    http = RollHttp(bad={"m"})
    with pytest.raises(AIError, match="all models failed"):
        Analyzer({**CFG, "auto_free_models": True}, {"openrouter": "k"}, http).analyze(PICK)
    assert http.used == ["m"]


def test_unparsable_reply_also_rolls_over():
    class Junk(RollHttp):
        def post(self, url, json, timeout, headers=None):
            if json["model"] == "m":
                self.used.append("m")
                return Resp({"choices": [{"message": {"content": "sure! here you go"}}]})
            return super().post(url, json, timeout, headers)

    http = Junk(listing=[])
    v = Analyzer({**CFG, "openrouter_fallbacks": ["b"]}, {"openrouter": "k"}, http).analyze(PICK)
    assert http.used == ["m", "b"] and v["model"] == "b"


def test_postmortem_schema_and_rollover():
    from stockfinder.ai import parse_postmortem
    ok = json.dumps({"assessment": "lucky", "what_happened": "RSI 27 then +8%", "adjustments": ["raise volume_ratio"]})
    assert parse_postmortem(ok)["assessment"] == "lucky"
    for bad in ("nope", json.dumps({"assessment": "great", "what_happened": "x"}),
                json.dumps({"assessment": "lucky", "what_happened": " "}),
                json.dumps({"assessment": "lucky", "what_happened": "x", "adjustments": [1]})):
        with pytest.raises(AIError):
            parse_postmortem(bad)


def test_sticks_to_last_winner_and_reports_stats():
    http = RollHttp(bad={"m"}, listing=[])
    a = Analyzer({**CFG, "openrouter_fallbacks": ["good"]}, {"openrouter": "k"}, http)
    a.analyze(PICK)
    a.analyze(PICK)
    assert http.used == ["m", "good", "good"]  # 2nd pick doesn't retry the dead model
    assert a.stats["m"]["ok"] == 0 and a.stats["good"]["ok"] == 2 and "good: 2/2 ok" in a.summary()


def test_listing_ranks_response_format_first_then_context():
    listing = [{**free("small", params=()), "context_length": 10}, {**free("big", params=()), "context_length": 99},
               {**free("rf"), "context_length": 5}]
    assert Analyzer(CFG, {}, RollHttp(listing=listing))._free_models() == ["rf", "big", "small"]
