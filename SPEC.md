# SPEC — stock-finder

## §G goal
Python fund tool: screen stock universe (index/sector), detect pre-bull/pre-bear setups, AI-analyze fundamentals+technicals (OpenRouter or local Ollama), push Telegram alert w/ pick + reasoning. Precision/correctness mandatory — fund capital at stake.

## §C constraints
- python 3.11+
- data: Finnhub (primary — fundamentals, technicals, index/sector constituents) + Alpha Vantage (fallback/cross-check). NOT Binance — no live equities API (tokenized stocks discontinued 2021, crypto-only).
- AI: OpenRouter (cloud, configurable model) OR local Ollama, switchable via config, same prompt/output contract both paths
- notify: Telegram Bot API, one message per pick, must include ticker + signal type (pre-bull/pre-bear) + reasoning summary
- no auto-trade execution — advisory only, human confirms trades
- all AI verdicts must cite the numeric data (fundamentals/indicators) that drove them — no unsupported claims
- config-driven: API keys, model choice, universe (index/sector), thresholds — no hardcoded secrets

## §I interfaces
- I.finnhub — REST, fundamentals + technical indicators + index/sector constituents, needs API key
- I.alphavantage — REST, fallback historical/fundamental data, needs API key
- I.openrouter — REST chat completion, needs API key, model configurable
- I.ollama — local HTTP API (localhost), model configurable
- I.telegram — Bot API sendMessage, needs bot token + chat id
- I.config — local config file (env or yaml), holds keys, universe def, thresholds, AI backend choice

## §V invariants
V1 | no ticker enters AI analysis w/o data validated from ≥1 live source fetch this run — no stale/cached silent reuse past config TTL
V2 | AI output must reference specific fetched metrics (e.g. RSI value, P/E, earnings trend) in reasoning — reject/flag outputs w/ no data citation
V3 | Telegram message never sent w/o both: (a) signal classification (pre-bull/pre-bear) and (b) reasoning text
V4 | on data source failure (Finnhub down), fallback to Alpha Vantage before skipping ticker — never silently drop w/o logging
V5 | tool never places/executes trades — output is advisory notification only
V6 | API keys/secrets loaded from config/env only — never hardcoded, never logged
V7 | AI backend (OpenRouter vs Ollama) swappable via config without code change — same output schema from both

## §T tasks
id|status|desc|cites
T1|x|project scaffold (pyproject, config loader, .env template)|V6
T2|x|Finnhub client — fundamentals, technicals, index/sector constituents|I.finnhub,V1
T3|.|Alpha Vantage client — fallback fetch|I.alphavantage,V4
T4|.|universe screener — pull index/sector constituents, apply pre-bull/pre-bear technical filter (volume, RSI, MA crossover etc)|T2,V1
T5|.|AI analysis module — build prompt from fundamentals+technicals, call OpenRouter or Ollama per config, parse structured verdict (signal, confidence, reasoning, cited metrics)|I.openrouter,I.ollama,V2,V7
T6|.|output schema/validator — reject AI verdicts missing data citations|V2
T7|.|Telegram notifier — format + send pick summary|I.telegram,V3
T8|.|run orchestrator — screen → analyze → validate → notify, w/ fallback + logging on source failure|T2,T3,T4,T5,T6,T7,V4
T9|.|scheduling (cron or internal loop) for periodic scans|T8

## §B bugs
id|date|cause|fix
