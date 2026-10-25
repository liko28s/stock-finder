# SPEC — stock-finder

## §G goal
Python fund tool: screen stock universe (index/sector), detect pre-bull/pre-bear setups, AI-analyze fundamentals+technicals (OpenRouter or local Ollama), push Telegram alert w/ pick + reasoning. Precision/correctness mandatory — fund capital at stake.

## §C constraints
- python 3.11+
- data: Yahoo Finance (primary — unofficial, yfinance lib, no key; fundamentals + OHLCV; no constituents endpoint → universe = config ticker list ∪ discovered via Yahoo predefined screens e.g. most_actives) + Alpha Vantage (fallback/cross-check). Finnhub dropped: /indicator premium. NOT Binance — no live equities API (tokenized stocks discontinued 2021, crypto-only).
- AI: OpenRouter (cloud, configurable model) OR local Ollama, switchable via config, same prompt/output contract both paths
- notify: Telegram Bot API, one message per pick, must include ticker + signal type (pre-bull/pre-bear) + reasoning summary
- no auto-trade execution — advisory only, human confirms trades
- all AI verdicts must cite the numeric data (fundamentals/indicators) that drove them — no unsupported claims
- config-driven: API keys, model choice, universe (index/sector), thresholds — no hardcoded secrets

## §I interfaces
- I.yahoo — yfinance lib (unofficial Yahoo endpoints), fundamentals + daily OHLCV + yf.screen predefined screens (most_actives etc) for discovery, no key, may break/rate-limit without notice
- I.alphavantage — REST, fallback historical/fundamental data, needs API key
- I.openrouter — REST chat completion, needs API key, model configurable
- I.ollama — local HTTP API (localhost), model configurable
- I.telegram — Bot API sendMessage, needs bot token + chat id
- I.config — local config file (env or yaml), holds keys, universe def, thresholds, AI backend choice

## §V invariants
V1 | no ticker enters AI analysis w/o data validated from ≥1 live source fetch this run — no stale/cached silent reuse past config TTL
V2 | AI output must reference specific fetched metrics (e.g. RSI value, P/E, earnings trend) in reasoning — reject/flag outputs w/ no data citation
V3 | Telegram message never sent w/o both: (a) signal classification (pre-bull/pre-bear) and (b) reasoning text
V4 | on data source failure (primary source down), fallback to Alpha Vantage before skipping ticker — never silently drop w/o logging
V5 | tool never places/executes trades — output is advisory notification only
V6 | API keys/secrets loaded from config/env only — never hardcoded, never logged
V7 | AI backend (OpenRouter vs Ollama) swappable via config without code change — same output schema from both

## §T tasks
id|status|desc|cites
T1|x|project scaffold (pyproject, config loader, .env template)|V6
T2|x|Finnhub client — fundamentals, technicals, index/sector constituents|I.finnhub,V1
T3|x|Alpha Vantage client — fallback fetch|I.alphavantage,V4
T4|x|universe screener — pull index/sector constituents, apply pre-bull/pre-bear technical filter (volume, RSI, MA crossover etc)|T2,V1
T5|x|AI analysis module — build prompt from fundamentals+technicals, call OpenRouter or Ollama per config, parse structured verdict (signal, confidence, reasoning, cited metrics)|I.openrouter,I.ollama,V2,V7
T6|x|output schema/validator — reject AI verdicts missing data citations|V2
T7|x|Telegram notifier — format + send pick summary|I.telegram,V3
T8|x|run orchestrator — screen → analyze → validate → notify, w/ fallback + logging on source failure|T2,T3,T4,T5,T6,T7,V4
T9|x|scheduling (cron or internal loop) for periodic scans|T8
T10|x|Yahoo client (yfinance) — fundamentals, technicals, universe from config ticker list; replace Finnhub as primary in orchestrator|I.yahoo,V1,V4
T11|x|ticker discovery — yf.screen predefined screens (config list), union w/ config tickers, dedupe, cap count; orchestrator scans the union|I.yahoo,V1
T12|x|alert dedupe — persist last signal per ticker, skip re-notify same ticker+signal on consecutive scans (monitor runs repeatedly)|V3
T13|x|OpenRouter model rollover — configured model, explicit fallbacks, then any free model listing response_format; roll on call failure/429/unparsable reply|I.openrouter,V7
T14|x|Telegram messages: #TICKER + #signal hashtags, model/source footer, return message_id|V3
T15|x|human feedback — 👍=TP hit, 👎=SL hit via message_reaction updates; reminder after N days; hit-rate summary|I.telegram,V5
T16|x|post-mortem on reaction — replay signal-time data+reasoning, price path since alert, AI explains outcome + suggests adjustments, reply under alert|T15,V2,V5
T17|x|more indicators in snapshot + prompt: MACD(12/26/9), ATR14, ADX14 (+DI/-DI), OBV slope, KER10, 20d z-score (mean reversion); skipped when history too short|V1,V2
T18|x|catch movers: discovery adds day_gainers/day_losers (round-robin under cap), ret1d/5d/20d indicators, momentum trigger (|1d move| >= move_pct w/ volume, lower priority than RSI/MA extremes)|T11,V1
T19|x|alert links: exact alert time/price, QuickChart candlestick marked at alert, TradingView link; failure never blocks alert|V3

## §B bugs
id|date|cause|fix
