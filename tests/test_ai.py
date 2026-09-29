import json

import pytest

from stockfinder.ai import AIError, Analyzer, build_prompt, parse_verdict

from test_finnhub import Resp

VERDICT = {"signal": "pre-bull", "confidence": 0.7, "reasoning": "RSI 27.4 oversold",
           "cited_metrics": {"rsi": 27.4}}
PICK = {"ticker": "AAPL", "signal": "pre-bull",
        "snapshot": {"source": "finnhub", "fundamentals": {"pe": 20}, "technicals": {"rsi": 27.4}}}
CFG = {"backend": "openrouter", "openrouter_model": "m", "ollama_model": "l", "ollama_url": "http://localhost:11434"}


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
