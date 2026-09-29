import requests

LIMIT = 4096  # Bot API max text length
SIGNALS = {"pre-bull", "pre-bear"}


class NotifyError(Exception):
    """Message refused (V3) or delivery failed."""


def format_pick(ticker, signal, reasoning, confidence=None, source=None):
    head = f"{ticker}: {signal.upper()}"
    if confidence is not None:
        head += f" (confidence {confidence:.0%})"
    text = f"{head}\n\n{reasoning.strip()}"
    if source:
        text += f"\n\nData: {source}. Advisory only, not a trade order."
    return text[:LIMIT]


class Telegram:
    def __init__(self, token, chat_id, http=requests):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"  # token in URL: never log/raise it
        self.chat_id, self.http = chat_id, http

    def send(self, ticker, signal, reasoning, confidence=None, source=None):
        """V3: refuses without a pre-bull/pre-bear classification and non-empty reasoning."""
        if signal not in SIGNALS:
            raise NotifyError(f"refusing to send {ticker}: signal {signal!r} is not pre-bull/pre-bear")
        if not (reasoning or "").strip():
            raise NotifyError(f"refusing to send {ticker}: no reasoning")
        try:
            r = self.http.post(self.url, json={"chat_id": self.chat_id, "text": format_pick(
                ticker, signal, reasoning, confidence, source)}, timeout=15)
            r.raise_for_status()
            ok = r.json().get("ok")
        except (requests.RequestException, ValueError) as e:
            raise NotifyError(f"telegram send failed for {ticker}: {type(e).__name__}") from e
        if not ok:
            raise NotifyError(f"telegram rejected message for {ticker}")

    def send_pick(self, pick, verdict):
        self.send(pick["ticker"], verdict["signal"], verdict["reasoning"], verdict["confidence"],
                  pick["snapshot"]["source"])
