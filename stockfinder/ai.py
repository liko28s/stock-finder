import json
import re

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SIGNALS = {"pre-bull", "pre-bear", "neutral"}

PROMPT = """You are an equity analyst advising a fund. A screener flagged {ticker} as {signal}.
Data (fetched live from {source}):
{data}

Decide whether the setup is real. Use ONLY the data above. Every claim in "reasoning" must quote a number from it.
Reply with a single JSON object, no prose, with exactly these keys:
  "signal": "pre-bull" | "pre-bear" | "neutral"
  "confidence": number 0..1
  "reasoning": short string citing the numbers
  "cited_metrics": object mapping metric name -> value copied from the data (e.g. {{"rsi": 27.4, "pe": 18.2}})"""


class AIError(Exception):
    """Backend call failed or reply didn't match the verdict schema."""


def build_prompt(pick):
    s = pick["snapshot"]
    data = json.dumps({"fundamentals": s["fundamentals"], "technicals": s["technicals"]}, indent=1)
    return PROMPT.format(ticker=pick["ticker"], signal=pick["signal"], source=s["source"], data=data)


def parse_verdict(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        v = json.loads(text)
    except ValueError as e:
        raise AIError("reply is not JSON") from e
    if not isinstance(v, dict):
        raise AIError("reply is not an object")
    if v.get("signal") not in SIGNALS:
        raise AIError(f"bad signal: {v.get('signal')!r}")
    if not isinstance(v.get("confidence"), (int, float)) or isinstance(v["confidence"], bool) or not 0 <= v["confidence"] <= 1:
        raise AIError("bad confidence")
    if not isinstance(v.get("reasoning"), str) or not isinstance(v.get("cited_metrics"), dict):
        raise AIError("missing reasoning or cited_metrics")
    return {k: v[k] for k in ("signal", "confidence", "reasoning", "cited_metrics")}


class Analyzer:
    """V7: backend picked by ai.backend; both paths share prompt and parse_verdict."""

    def __init__(self, ai_cfg, keys, http=requests):
        self.cfg, self.keys, self.http = ai_cfg, keys, http

    def _call(self, prompt):
        backend = self.cfg["backend"]
        msgs = [{"role": "user", "content": prompt}]
        if backend == "openrouter":
            r = self.http.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {self.keys['openrouter']}"},
                               json={"model": self.cfg["openrouter_model"], "messages": msgs,
                                     "temperature": 0, "response_format": {"type": "json_object"}}, timeout=120)
            extract = lambda d: d["choices"][0]["message"]["content"]
        elif backend == "ollama":
            r = self.http.post(self.cfg["ollama_url"] + "/api/chat",
                               json={"model": self.cfg["ollama_model"], "messages": msgs, "stream": False,
                                     "format": "json", "options": {"temperature": 0}}, timeout=300)
            extract = lambda d: d["message"]["content"]
        else:
            raise AIError(f"unknown backend: {backend}")
        try:
            r.raise_for_status()
            return extract(r.json())
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            raise AIError(f"{backend} call failed: {type(e).__name__}") from e

    def analyze(self, pick):
        return parse_verdict(self._call(build_prompt(pick)))
