import re

import requests

from . import scenarios

LIMIT = 4096  # Bot API max text length
SIGNALS = {"pre-bull", "pre-bear"}


class NotifyError(Exception):
    """Message refused (V3) or delivery failed."""


ICON = {"pre-bull": "🟢", "pre-bear": "🔴"}


def tag(text):
    """Telegram hashtag: letters/digits/underscore only (BRK-B -> #BRK_B), searchable in chat."""
    return "#" + re.sub(r"\W", "_", text)


def format_pick(ticker, signal, reasoning, confidence=None, source=None, model=None, links=None, scn=None):
    head = f"{ICON.get(signal, '')} {tag(ticker)} {tag(signal)}\n{signal.upper()}"
    if confidence is not None:
        head += f" · confidence {confidence:.0%}"
    text = f"{head}\n\n{reasoning.strip()}"
    if source:
        text += f"\n\nData: {source}" + (f" · AI: {model}" if model else "") + ". Advisory only, not a trade order."
    if scn:
        text += "\n\n" + scenarios.lines(scn, signal)
    if links:
        text += f"\n\n🕒 Alerted {links['when']} @ {links['price']:.2f}"
        text += "".join(f"\n{label}: {links[k]}" for k, label in (("chart", "📈 Chart"), ("tradingview", "🔗 TradingView"))
                        if links.get(k))
    text += "\n\nReact to this message: 👍 target hit · 👎 stop hit"
    return text[:LIMIT]


class Telegram:
    def __init__(self, token, chat_id, http=requests):
        self.api = f"https://api.telegram.org/bot{token}/"  # token in URL: never log/raise it
        self.url = self.api + "sendMessage"
        self.chat_id, self.http = chat_id, http

    def send(self, ticker, signal, reasoning, confidence=None, source=None, model=None, links=None, scn=None):
        """V3: refuses without a pre-bull/pre-bear classification and non-empty reasoning. Returns message_id."""
        if signal not in SIGNALS:
            raise NotifyError(f"refusing to send {ticker}: signal {signal!r} is not pre-bull/pre-bear")
        if not (reasoning or "").strip():
            raise NotifyError(f"refusing to send {ticker}: no reasoning")
        try:
            r = self.http.post(self.url, json={"chat_id": self.chat_id, "text": format_pick(
                ticker, signal, reasoning, confidence, source, model, links, scn)}, timeout=15)
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
                         pick["snapshot"]["source"], verdict.get("model"), pick.get("links"), verdict.get("scenarios"))

    def _post(self, method, payload, what):
        try:
            r = self.http.post(self.api + method, json=payload, timeout=40)
            r.raise_for_status()
            body = r.json()
        except (requests.RequestException, ValueError) as e:
            raise NotifyError(f"telegram {what} failed: {type(e).__name__}") from e
        if not body.get("ok"):
            raise NotifyError(f"telegram rejected {what}")
        return body["result"]

    def reply(self, message_id, text):
        """Plain follow-up under an earlier alert (not a pick, so V3 doesn't apply). Returns message_id."""
        res = self._post("sendMessage", {"chat_id": self.chat_id, "text": text[:LIMIT],
                                         "reply_to_message_id": message_id}, "reply")
        return res.get("message_id")

    def reaction_updates(self, offset=None):
        """Emoji reactions on our messages since offset, from this chat only."""
        res = self._post("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message_reaction"]},
                         "getUpdates")
        return [u for u in res if str(u.get("message_reaction", {}).get("chat", {}).get("id")) == str(self.chat_id)
                or "message_reaction" not in u]
