"""Human feedback loop: 👍 on an alert = target (TP) hit, 👎 = stop (SL) hit. Reactions are polled from
Telegram, stored per alert, and summarised as a hit rate. Advisory only (V5): nothing here trades."""
import json
import logging
import time
from pathlib import Path

from .telegram import NotifyError

log = logging.getLogger(__name__)
OUTCOME = {"👍": "tp", "👎": "sl"}
DAY = 86400


def load(path="feedback.json"):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {"offset": None, "alerts": []}


def save(state, path="feedback.json"):
    Path(path).write_text(json.dumps(state, indent=1))


def record(state, message_id, ticker, signal, now=None):
    if message_id is not None:
        state["alerts"].append({"id": message_id, "ticker": ticker, "signal": signal, "ts": time.time() if now is None else now,
                                "outcome": None, "reminder_id": None})


def apply_reactions(state, updates):
    """Update outcomes from message_reaction updates; reactions on the alert or its reminder both count.
    Last reaction wins; removing it clears the outcome; unrelated emoji are ignored. Returns changes made."""
    changed = 0
    for u in updates:
        if "update_id" in u:
            state["offset"] = u["update_id"] + 1
        mr = u.get("message_reaction")
        if not mr:
            continue
        alert = next((a for a in state["alerts"] if mr["message_id"] in (a["id"], a["reminder_id"])), None)
        if alert is None:
            continue
        emojis = [r.get("emoji") for r in mr.get("new_reaction", [])]
        new = next((OUTCOME[e] for e in emojis if e in OUTCOME), None)
        if new is None and emojis:
            continue
        if alert["outcome"] != new:
            alert["outcome"], changed = new, changed + 1
    return changed


def remind_due(state, tg, days, now=None):
    """One reminder reply per unresolved alert older than `days`. Returns how many sent."""
    now, sent = (time.time() if now is None else now), 0
    for a in state["alerts"]:
        if a["outcome"] or a["reminder_id"] or now - a["ts"] < days * DAY:
            continue
        try:
            a["reminder_id"] = tg.reply(a["id"], f"#{a['ticker']} {days}d since the {a['signal']} alert. "
                                                 "Did it play out? 👍 target hit · 👎 stop hit")
            sent += 1
        except NotifyError as e:
            log.error("%s: reminder failed: %s", a["ticker"], e)
    return sent


def sync(state, tg, review_after_days, now=None):
    """Poll reactions, then nudge for overdue alerts. Reaction polling failure is logged, never fatal."""
    try:
        apply_reactions(state, tg.reaction_updates(state["offset"]))
    except NotifyError as e:
        log.error("reaction poll failed: %s", e)
    return remind_due(state, tg, review_after_days, now)


def summary(state):
    """Per signal: tp / sl / pending counts and hit rate = tp / (tp + sl) over resolved alerts."""
    rows = {}
    for a in state["alerts"]:
        r = rows.setdefault(a["signal"], {"tp": 0, "sl": 0, "pending": 0})
        r[a["outcome"] or "pending"] += 1
    for r in rows.values():
        done = r["tp"] + r["sl"]
        r["hit_rate"] = r["tp"] / done if done else None
    return rows


def main(path="feedback.json"):
    for sig, r in sorted(summary(load(path)).items()):
        rate = "n/a" if r["hit_rate"] is None else f"{r['hit_rate']:.0%}"
        print(f"{sig}: 👍 {r['tp']}  👎 {r['sl']}  pending {r['pending']}  hit rate {rate}")


if __name__ == "__main__":
    main()
