import json
import logging
import re
import time

import requests

from . import scenarios
from .prompts import load as load_prompt

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
MAX_TRIES = 5  # models attempted per pick before giving up
SIGNALS = {"pre-bull", "pre-bear", "neutral"}

log = logging.getLogger(__name__)

PROMPT = load_prompt("analysis")  # stockfinder/prompts/analysis.md


class AIError(Exception):
    """Backend call failed or reply didn't match the verdict schema."""


def rounded(d):
    """4-decimal floats in prompts: fewer tokens, well inside the validator's 1% tolerance."""
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}


def build_prompt(pick):
    s = pick["snapshot"]
    data = json.dumps({"fundamentals": rounded(s["fundamentals"]), "technicals": rounded(s["technicals"])}, indent=1)
    why = ("momentum: a large 1-day move on high volume, with no RSI/MA extreme; judge whether it is a breakout or "
           "an exhausted spike" if pick.get("trigger") == "momentum" else "RSI extreme or moving-average cross on high volume")
    return PROMPT.format(ticker=pick["ticker"], signal=pick["signal"], why=why, source=s["source"], data=data) + scenarios.prompt_block(pick)


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
    return {k: v[k] for k in ("signal", "confidence", "reasoning", "cited_metrics", "scenarios") if k in v}


ASSESSMENTS = {"good_call", "bad_call", "lucky", "unlucky", "inconclusive"}


def parse_postmortem(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        v = json.loads(text)
    except ValueError as e:
        raise AIError("reply is not JSON") from e
    if not isinstance(v, dict) or v.get("assessment") not in ASSESSMENTS:
        raise AIError("bad postmortem assessment")
    if not isinstance(v.get("what_happened"), str) or not v["what_happened"].strip():
        raise AIError("missing what_happened")
    adj = v.get("adjustments", [])
    if not isinstance(adj, list) or not all(isinstance(x, str) for x in adj):
        raise AIError("bad adjustments")
    return {"assessment": v["assessment"], "what_happened": v["what_happened"].strip(), "adjustments": adj}


class Analyzer:
    """V7: backend picked by ai.backend; both paths share prompt and parse_verdict."""

    def __init__(self, ai_cfg, keys, http=requests):
        self.cfg, self.keys, self.http = ai_cfg, keys, http
        self.i = 0  # index of the last winning model
        self.stats = {}  # model -> {calls, ok, secs, tokens}

    def _free_models(self):
        """Free OpenRouter models, fetched once per Analyzer; ones that advertise response_format first, then by
        context length (small models last). Many working models don't advertise it, so it only ranks. Failure -> []."""
        if not hasattr(self, "_free"):
            try:
                r = self.http.get(OPENROUTER_MODELS_URL, timeout=30)
                r.raise_for_status()
                free = [m for m in r.json()["data"]
                        if all(float(m["pricing"].get(k) or 1) == 0 for k in ("prompt", "completion"))]
                free.sort(key=lambda m: ("response_format" not in (m.get("supported_parameters") or []),
                                         -(m.get("context_length") or 0)))
                self._free = [m["id"] for m in free]
            except (requests.RequestException, ValueError, KeyError, TypeError):
                log.warning("could not list free OpenRouter models, using configured ones only")
                self._free = []
        return self._free

    def _models(self):
        """Configured model first, then configured fallbacks, then every free model OpenRouter lists."""
        c = self.cfg
        ordered = [c["openrouter_model"], *c.get("openrouter_fallbacks", [])]
        if c.get("auto_free_models", True):
            ordered += self._free_models()
        return list(dict.fromkeys(ordered))

    def _call(self, prompt, model=None):
        """Returns (text, total_tokens)."""
        backend = self.cfg["backend"]
        msgs = [{"role": "user", "content": prompt}]
        if backend == "openrouter":
            post = lambda: self.http.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {self.keys['openrouter']}"},
                                          json={"model": model or self.cfg["openrouter_model"], "messages": msgs,
                                                "temperature": 0, "response_format": {"type": "json_object"}}, timeout=60)
            extract = lambda d: (d["choices"][0]["message"]["content"], (d.get("usage") or {}).get("total_tokens", 0))
        elif backend == "ollama":
            post = lambda: self.http.post(self.cfg["ollama_url"] + "/api/chat",
                                          json={"model": self.cfg["ollama_model"], "messages": msgs, "stream": False,
                                                "format": "json", "options": {"temperature": 0}}, timeout=300)
            extract = lambda d: (d["message"]["content"], d.get("prompt_eval_count", 0) + d.get("eval_count", 0))
        else:
            raise AIError(f"unknown backend: {backend}")
        try:  # connection errors too: a down backend fails this pick, not the whole run
            r = post()
            r.raise_for_status()
            text, tokens = extract(r.json())
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            raise AIError(f"{backend} call failed: {type(e).__name__}") from e
        if not isinstance(text, str) or not text.strip():  # some reasoning models return content: null
            raise AIError(f"{backend} returned an empty reply")
        return text, tokens

    def _roll(self, prompt, parse, label):
        """OpenRouter: try up to max_model_tries models, rolling over on call failure, rate limit or unparsable
        reply, and sticking to the last winner so a dead model isn't retried on every pick. Result is tagged with
        the model that produced it. Ollama: single model. Per-model stats feed summary()."""
        backend = self.cfg["backend"]
        models = self._models() if backend == "openrouter" else [self.cfg.get("ollama_model", "ollama")]
        errors = []
        for n in range(min(self.cfg.get("max_model_tries", MAX_TRIES), len(models))):
            model = models[(self.i + n) % len(models)]
            st = self.stats.setdefault(model, {"calls": 0, "ok": 0, "secs": 0.0, "tokens": 0})
            st["calls"] += 1
            t0 = time.monotonic()
            try:
                text, tokens = self._call(prompt, model)
                result = parse(text)
            except AIError as e:
                st["secs"] += time.monotonic() - t0
                log.warning("%s: model %s failed (%s), trying next", label, model, e)
                errors.append(f"{model}: {e}")
                continue
            dt = time.monotonic() - t0
            st["ok"] += 1
            st["secs"] += dt
            st["tokens"] += tokens
            log.info("%s: model=%s ok %.1fs tokens=%s", label, model, dt, tokens)
            self.i = (self.i + n) % len(models)
            return {**result, "model": model} if backend == "openrouter" else result
        self.i = (self.i + 1) % len(models)  # all failed: start elsewhere next time
        raise AIError("all models failed: " + "; ".join(errors))

    def summary(self):
        """One line per model: calls/ok, total time, tokens. Empty if no queries were made."""
        return "\n".join(f"{m}: {s['ok']}/{s['calls']} ok, {s['secs']:.0f}s, {s['tokens']} tok"
                         for m, s in self.stats.items())

    def analyze(self, pick):
        return self._roll(build_prompt(pick), parse_verdict, pick["ticker"])

    def postmortem(self, prompt, label):
        """Same rollover, different reply schema (see parse_postmortem)."""
        return self._roll(prompt, parse_postmortem, label)
