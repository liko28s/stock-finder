import re

import requests

LIMIT = 4096  # Bot API max text length
SIGNALS = {"pre-bull", "pre-bear"}


class NotifyError(Exception):
    """Message refused (V3) or delivery failed."""


ICON = {"pre-bull": "🟢", "pre-bear": "🔴"}


def tag(text):
    """Telegram hashtag: letters/digits/underscore only (BRK-B -> #BRK_B), searchable in chat."""
    return "#" + re.sub(r"\W", "_", text)


def format_pick(ticker, signal, reasoning, confidence=None, source=None, model=None):
    head = f"{ICON.get(signal, '')} {tag(ticker)} {tag(signal)}\n{signal.upper()}"
    if confidence is not None:
        head += f" · confidence {confidence:.0%}"
    text = f"{head}\n\n{reasoning.strip()}"
    if source:
        text += f"\n\nData: {source}" + (f" · AI: {model}" if model else "") + ". Advisory only, not a trade order."
    text += "\n\nReact to this message: 👍 target hit · 👎 stop hit"
    return text[:LIMIT]


class Telegram:
    def __init__(self, token, chat_id, http=requests):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"  # token in URL: never log/raise it
        self.chat_id, self.http = chat_id, http

    def send(self, ticker, signal, reasoning, confidence=None, source=None, model=None):
        """V3: refuses without a pre-bull/pre-bear classification and non-empty reasoning. Returns message_id."""
        if signal not in SIGNALS:
            raise NotifyError(f"refusing to send {ticker}: signal {signal!r} is not pre-bull/pre-bear")
        if not (reasoning or "").strip():
            raise NotifyError(f"refusing to send {ticker}: no reasoning")
        try:
            r = self.http.post(self.url, json={"chat_id": self.chat_id, "text": format_pick(
                ticker, signal, reasoning, confidence, source, model)}, timeout=15)
            r.raise_for_status()
            body = r.json()
            ok = body.get("ok")
        except (requests.RequestException, ValueError) as e:
            raise NotifyError(f"telegram send failed for {ticker}: {type(e).__name__}") from e
        if not ok:
            raise NotifyError(f"telegram rejected message for {ticker}")
        return (body.get("result") or {}).get("message_id")

    def send_pick(self, pick, verdict):
        return self.send(pick["ticker"], verdict["signal"], verdict["reasoning"], verdict["confidence"],
                         pick["snapshot"]["source"], verdict.get("model"))
