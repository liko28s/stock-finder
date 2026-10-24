import json
import logging
import re

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
MAX_TRIES = 5  # models attempted per pick before giving up
SIGNALS = {"pre-bull", "pre-bear", "neutral"}

log = logging.getLogger(__name__)

PROMPT = """You are an equity analyst advising a fund. A screener flagged {ticker} as {signal} ({why}).
Data (fetched live from {source}):
{data}

Indicator notes: adx = trend strength (>25 trending), plus_di/minus_di = up/down pressure, atr_pct = daily range as % of price, macd_hist = macd - macd_signal, obv_slope20 = volume-flow direction (-1..1), ker10 = trend efficiency (1 = clean trend, 0 = noise), zscore20 = stretch from the 20d mean (mean-reversion; |z|>2 stretched). ret1d/ret5d/ret20d = price change in % over 1/5/20 trading days. Some may be absent.

Decide whether the setup is real. Use ONLY the data above. Every claim in "reasoning" must quote a number from it.
Reply with a single JSON object, no prose, with exactly these keys:
  "signal": "pre-bull" | "pre-bear" | "neutral"
  "confidence": number 0..1
  "reasoning": short string citing the numbers
  "cited_metrics": object mapping metric name -> value copied from the data (e.g. {{"rsi": 27.4, "pe": 18.2}})"""


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
    return PROMPT.format(ticker=pick["ticker"], signal=pick["signal"], why=why, source=s["source"], data=data)


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

    def _free_models(self):
        """Free OpenRouter models that accept response_format, fetched once per Analyzer. Failure -> []."""
        if not hasattr(self, "_free"):
            try:
                r = self.http.get(OPENROUTER_MODELS_URL, timeout=30)
                r.raise_for_status()
                self._free = [m["id"] for m in r.json()["data"]
                              if all(float(m["pricing"].get(k) or 1) == 0 for k in ("prompt", "completion"))
                              and "response_format" in (m.get("supported_parameters") or [])]
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
        return list(dict.fromkeys(ordered))[:c.get("max_model_tries", MAX_TRIES)]

    def _call(self, prompt, model=None):
        backend = self.cfg["backend"]
        msgs = [{"role": "user", "content": prompt}]
        if backend == "openrouter":
            r = self.http.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {self.keys['openrouter']}"},
                               json={"model": model or self.cfg["openrouter_model"], "messages": msgs,
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

    def _roll(self, prompt, parse, label):
        """OpenRouter: roll over to the next model on call failure, rate limit or unparsable reply. Result is
        tagged with the model that produced it. Ollama: single model."""
        if self.cfg["backend"] != "openrouter":
            return parse(self._call(prompt))
        errors = []
        for model in self._models():
            try:
                return {**parse(self._call(prompt, model)), "model": model}
            except AIError as e:
                log.warning("%s: model %s failed (%s), trying next", label, model, e)
                errors.append(f"{model}: {e}")
        raise AIError("all models failed: " + "; ".join(errors))

    def analyze(self, pick):
        return self._roll(build_prompt(pick), parse_verdict, pick["ticker"])

    def postmortem(self, prompt, label):
        """Same rollover, different reply schema (see parse_postmortem)."""
        return self._roll(prompt, parse_postmortem, label)
