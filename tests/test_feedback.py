from stockfinder import feedback as fb
from stockfinder.telegram import NotifyError, Telegram

from test_finnhub import Resp

DAY = 86400


def react(uid, mid, *emojis, chat=42):
    return {"update_id": uid, "message_reaction": {"chat": {"id": chat}, "message_id": mid,
                                                   "new_reaction": [{"type": "emoji", "emoji": e} for e in emojis]}}


def state():
    s = {"offset": None, "alerts": []}
    fb.record(s, 10, "AAPL", "pre-bull", now=0)
    fb.record(s, 11, "TSLA", "pre-bear", now=0)
    fb.record(s, None, "X", "pre-bull")  # send gave no id: nothing to track
    return s


def test_thumbs_map_to_tp_sl_and_offset_advances():
    s = state()
    fb.apply_reactions(s, [react(5, 10, "👍"), react(6, 11, "👎"), react(7, 99, "👍")])
    assert [a["outcome"] for a in s["alerts"]] == ["tp", "sl"] and s["offset"] == 8


def test_last_reaction_wins_removal_clears_other_emoji_ignored():
    s = state()
    fb.apply_reactions(s, [react(1, 10, "👍"), react(2, 10, "🔥")])
    assert s["alerts"][0]["outcome"] == "tp"
    fb.apply_reactions(s, [react(3, 10, "👎")])
    assert s["alerts"][0]["outcome"] == "sl"
    fb.apply_reactions(s, [react(4, 10)])
    assert s["alerts"][0]["outcome"] is None


class Tg:
    def __init__(self):
        self.replies = []

    def reply(self, mid, text):
        self.replies.append((mid, text))
        return 100 + mid


def test_reminder_once_after_days_and_reaction_on_reminder_counts():
    s, tg = state(), Tg()
    assert fb.remind_due(s, tg, 5, now=4 * DAY) == 0
    assert fb.remind_due(s, tg, 5, now=6 * DAY) == 2 and fb.remind_due(s, tg, 5, now=7 * DAY) == 0
    fb.apply_reactions(s, [react(1, 110, "👍")])  # reacted on the reminder, not the alert
    assert s["alerts"][0]["outcome"] == "tp"
    assert fb.remind_due(s, tg, 5, now=9 * DAY) == 0  # resolved + already reminded


def test_summary_hit_rate():
    s = state()
    fb.apply_reactions(s, [react(1, 10, "👍")])
    r = fb.summary(s)
    assert r["pre-bull"] == {"tp": 1, "sl": 0, "pending": 0, "hit_rate": 1.0}
    assert r["pre-bear"]["hit_rate"] is None and r["pre-bear"]["pending"] == 1


class Http:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        return self.resp


def test_reaction_updates_filters_chat_and_requests_reactions():
    http = Http(Resp({"ok": True, "result": [react(1, 10, "👍"), react(2, 10, "👎", chat=999)]}))
    out = Telegram("TOKEN", "42", http).reaction_updates(3)
    assert [u["update_id"] for u in out] == [1]
    assert http.calls[0][1]["allowed_updates"] == ["message_reaction"] and http.calls[0][1]["offset"] == 3


def test_sync_survives_poll_failure():
    class Bad(Tg):
        def reaction_updates(self, offset):
            raise NotifyError("down")

    s = state()
    assert fb.sync(s, Bad(), 5, now=6 * DAY) == 2
