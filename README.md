# stock-finder

Advisory-only screener: discovers candidates (your tickers + Yahoo `most_actives`),
pre-bull/pre-bear filter, AI check, Telegram alert.

Setup: `pip install -e .`, copy `.env.example` to `.env` and fill in keys, edit `config.toml`.

Run once: `.venv/bin/python -m stockfinder.run`

## Monitor (recurring)

cron runs the scan repeatedly. `alerts_state.json` records the last signal per ticker,
so a pick is alerted once, not re-sent every scan (until its signal changes).

Every 30 min, weekdays, US market hours (13:00-21:00 UTC ≈ 9-5 ET):

```
*/30 13-21 * * 1-5  cd /Users/sumapaz/Code/stock-finder && .venv/bin/python -m stockfinder.run >> scan.log 2>&1
```

Install it:

```
(crontab -l 2>/dev/null; echo '*/30 13-21 * * 1-5  cd /Users/sumapaz/Code/stock-finder && .venv/bin/python -m stockfinder.run >> scan.log 2>&1') | crontab -
```

Keep the interval above `ttl_seconds` in `config.toml`; every run refetches, so nothing stale is reused (V1).

## Alerts and feedback

Each alert carries `#TICKER` and `#pre_bull`/`#pre_bear` hashtags: tap one in Telegram to list every alert for it.

React to an alert: 👍 = target hit, 👎 = stop hit. Each scan polls reactions (`feedback.json`) and, after
`feedback.review_after_days`, replies under unresolved alerts asking how it went. Reacting on the reminder works too.
Hit rate per signal: `.venv/bin/python -m stockfinder.feedback`.

Don't set a Telegram webhook on the bot; reactions are read with `getUpdates`.

## AI model rollover

With `ai.backend = "openrouter"`, a failing model (error, rate limit, unparsable reply) rolls over to
`openrouter_fallbacks`, then to any other free OpenRouter model, up to `max_model_tries`. `auto_free_models = false`
disables discovery. The alert footer names the model that answered.

## Config

- `universe.tickers` — always scanned.
- `universe.screens` — Yahoo predefined screens for discovery (`[]` disables).
- `universe.max_tickers` — cap on total scanned.
- `ai.backend` — `openrouter` or `ollama`, same output contract either way.
