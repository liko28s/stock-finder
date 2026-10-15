import json
import logging
from pathlib import Path

from .ai import Analyzer, AIError
from .alphavantage import AlphaVantage
from .config import load
from .data import SourceError
from .screener import screen
from .telegram import NotifyError, Telegram
from .validate import ValidationError, validate
from .yahoo import Yahoo

log = logging.getLogger(__name__)


def fetch_with_fallback(ticker, primary, fallback):
    """V4: primary (Yahoo) first, then Alpha Vantage; every failure logged, never silently dropped."""
    try:
        return primary.snapshot(ticker)
    except SourceError as e:
        log.warning("%s: primary source failed (%s), trying fallback", ticker, e)
    if fallback is None:
        raise SourceError(f"{ticker}: primary failed and no fallback configured")
    return fallback.snapshot(ticker)


def build_universe(cfg, primary):
    """Config tickers plus discovered (Yahoo screens), order-preserving dedupe, capped. V1: discovery adds
    candidates only; each still gets a live validated fetch in screen()."""
    u = cfg.universe
    discovered = primary.discover(u["screens"]) if u.get("screens") else []
    seen, out = set(), []
    for t in [*u["tickers"], *discovered]:
        if t not in seen:
            seen.add(t)
            out.append(t)
    if not out:
        raise ValueError("universe is empty: no config tickers and nothing discovered")
    cap = u.get("max_tickers")
    return out[:cap] if cap else out


def run(cfg, primary, fallback, analyzer, notifier, last_signals=None):
    """last_signals: ticker -> last alerted signal, mutated in place. T12: skip re-notifying the same
    ticker+signal across repeated monitor runs."""
    seen = last_signals if last_signals is not None else {}
    tickers = build_universe(cfg, primary)
    picks = screen(tickers, lambda t: fetch_with_fallback(t, primary, fallback), cfg.thresholds)
    sent = 0
    for pick in picks:
        tk = pick["ticker"]
        try:
            verdict = validate(analyzer.analyze(pick), pick["snapshot"])
        except (AIError, ValidationError) as e:
            log.warning("%s: no alert, AI verdict unusable: %s", tk, e)
            continue
        if verdict["signal"] != pick["signal"]:
            log.info("%s: AI verdict %s disagrees with screener %s, no alert", tk, verdict["signal"], pick["signal"])
            continue
        if seen.get(tk) == verdict["signal"]:
            log.info("%s: %s already alerted, skipping duplicate", tk, verdict["signal"])
            continue
        try:
            notifier.send_pick(pick, verdict)
            seen[tk] = verdict["signal"]
            sent += 1
        except NotifyError as e:
            log.error("%s: alert failed: %s", tk, e)
    log.info("scanned %d, screened %d, alerted %d", len(tickers), len(picks), sent)
    return sent


def main(config_path="config.toml", state_path="alerts_state.json"):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load(config_path)
    av = AlphaVantage(cfg.keys["alphavantage"]) if "alphavantage" in cfg.keys else None
    state = Path(state_path)
    seen = json.loads(state.read_text()) if state.exists() else {}
    try:
        return run(cfg, Yahoo(), av, Analyzer(cfg.ai, cfg.keys),
                   Telegram(cfg.keys["tg_token"], cfg.keys["tg_chat"]), seen)
    finally:
        state.write_text(json.dumps(seen))  # persist even if a later ticker raises


if __name__ == "__main__":
    main()
