import pytest

from datetime import date, datetime

from stockfinder.data import NY, atr_adx, extras, session_fraction, technicals


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


def test_session_fraction_scales_only_todays_open_bar():
    at = lambda h, m: datetime(2026, 10, 26, h, m, tzinfo=NY)  # a Monday
    today = date(2026, 10, 26)
    assert session_fraction(today, at(12, 45)) == pytest.approx(0.5)  # 3h15 of 6h30
    assert session_fraction(today, at(9, 35)) == 0.1  # floor right after the open
    assert session_fraction(today, at(17, 0)) == 1.0  # closed: full day
    assert session_fraction(today, at(8, 0)) == 1.0  # pre-open
    assert session_fraction(date(2026, 10, 23), at(12, 45)) == 1.0  # last bar is Friday's (complete)
    assert session_fraction(None, at(12, 45)) == 1.0  # unknown date


def test_half_day_volume_at_half_session_is_normal():
    c, h, l, v = trend(60)
    v[-1] = 500.0  # half the usual 1000 by mid-session
    assert technicals(c, v, 55.0, h, l)["volume_ratio"] == pytest.approx(0.5)
    assert technicals(c, v, 55.0, h, l, day_fraction=0.5)["volume_ratio"] == pytest.approx(1.0)
