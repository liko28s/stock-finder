Sample trade: simulate a {USD} USD position opened at the close ({side}: long for pre-bull, short for pre-bear).
Add "scenarios": an object keyed by horizon ("1w","2w","3w","4w","2m","6m"), each {{"worst": n, "expected": n, "best": n}}
= profit/loss in USD from the position's point of view (losses negative), worst <= expected <= best.
Daily volatility is {vol:.2f}%, so one standard deviation of P&L per horizon is (USD): {band}.
Keep worst/best within about 2 sigma. Shade "expected" with the signal, confidence, trend (adx, macd, ret20d) and mean-reversion
(zscore20, rsi) evidence: for a weak setup expected stays near 0; a long can lose at most {USD} USD. The receiver uses this to
gauge best and worst cases, so be realistic, not optimistic. Illustration only, not a forecast.
