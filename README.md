# stock-finder

Advisory-only screener: index constituents, pre-bull/pre-bear filter, AI check, Telegram alert.

Setup: `pip install -e .`, copy `.env.example` to `.env` and fill in keys, edit `config.toml`.

Run once: `python -m stockfinder.run`

Schedule (T9): cron does the loop. Weekdays at 21:30 UTC, after US close:

```
30 21 * * 1-5  cd /path/to/stock-finder && .venv/bin/python -m stockfinder.run >> scan.log 2>&1
```

Keep the interval above `ttl_seconds` in `config.toml`; every run refetches, so nothing stale is reused (V1).
