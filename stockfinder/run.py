import logging

from .ai import Analyzer, AIError
from .alphavantage import AlphaVantage
from .config import load
from .data import SourceError
from .finnhub import Finnhub
from .screener import screen
from .telegram import NotifyError, Telegram
from .validate import ValidationError, validate

log = logging.getLogger(__name__)


def fetch_with_fallback(ticker, primary, fallback):
    """V4: Finnhub first, then Alpha Vantage; every failure logged, never silently dropped."""
    try:
        return primary.snapshot(ticker)
    except SourceError as e:
        log.warning("%s: primary source failed (%s), trying fallback", ticker, e)
    if fallback is None:
        raise SourceError(f"{ticker}: primary failed and no fallback configured")
    return fallback.snapshot(ticker)


def run(cfg, primary, fallback, analyzer, notifier):
    tickers = primary.constituents(cfg.universe["index"])
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
        try:
            notifier.send_pick(pick, verdict)
            sent += 1
        except NotifyError as e:
            log.error("%s: alert failed: %s", tk, e)
    log.info("scanned %d, screened %d, alerted %d", len(tickers), len(picks), sent)
    return sent


def main(config_path="config.toml"):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load(config_path)
    av = AlphaVantage(cfg.keys["alphavantage"]) if "alphavantage" in cfg.keys else None
    return run(cfg, Finnhub(cfg.keys["finnhub"]), av, Analyzer(cfg.ai, cfg.keys),
               Telegram(cfg.keys["tg_token"], cfg.keys["tg_chat"]))


if __name__ == "__main__":
    main()
