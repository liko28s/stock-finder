import pytest

from stockfinder.data import atr_adx, extras, technicals


def trend(n=60, step=1.0):
    c = [100 + i * step for i in range(n)]
    return c, [x + 0.5 for x in c], [x - 0.5 for x in c], [1000.0] * n


def test_uptrend_reads_as_strong_efficient_and_accumulated():
    c, h, l, v = trend()
    e = extras(c, v, h, l)
    assert e["adx"] > 90 and e["plus_di"] > e["minus_di"] == 0  # pure uptrend: no downward movement at all
    assert e["ker10"] == pytest.approx(1.0) and e["obv_slope20"] == pytest.approx(1.0)
    assert e["macd"] > 0 and e["macd_hist"] == pytest.approx(e["macd"] - e["macd_signal"])
    assert e["atr"] == pytest.approx(1.5, abs=0.2) and e["atr_pct"] == pytest.approx(e["atr"] / c[-1] * 100)


def test_downtrend_mirrors():
    c, h, l, v = trend(step=-1.0)
    e = extras(c, v, h, l)
    assert e["minus_di"] > e["plus_di"] == 0 and e["macd"] < 0 and e["obv_slope20"] == pytest.approx(-1.0)


def test_mean_reversion_zscore():
    c = [100.0] * 19 + [90.0]
    assert extras(c, [1.0] * 20)["zscore20"] < -3  # sharp drop below the 20d mean
    assert extras([100.0] * 20, [1.0] * 20)["zscore20"] == 0  # flat: no divide by zero


def test_choppy_has_low_ker():
    c = [100 + (i % 2) for i in range(30)]
    assert extras(c, [1.0] * 30)["ker10"] < 0.2


def test_short_history_skips_not_fails():
    assert extras([1.0] * 5, [1.0] * 5) == {}
    with pytest.raises(Exception):
        atr_adx([1] * 10, [1] * 10, [1] * 10)


def test_technicals_includes_new_keys_and_still_validates_cleanly():
    c, h, l, v = trend(60)
    t = technicals(c, v, 55.0, h, l)
    assert {"adx", "atr", "macd", "obv_slope20", "ker10", "zscore20"} <= set(t)
