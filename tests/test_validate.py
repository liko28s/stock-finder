import pytest

from stockfinder.validate import ValidationError, validate

SNAP = {"fundamentals": {"pe": 18.2}, "technicals": {"rsi": 27.4, "volume_ratio": 2.0}}


def v(**kw):
    return {"signal": "pre-bull", "confidence": 0.7, "reasoning": "RSI 27.4 is oversold on 2.0x volume",
            "cited_metrics": {"rsi": 27.4}, **kw}


def test_valid_verdict_passes():
    assert validate(v(), SNAP)["signal"] == "pre-bull"


def test_rounded_citation_passes():
    validate(v(reasoning="RSI 27.43 oversold", cited_metrics={"rsi": 27.43}), SNAP)


def test_rejects_verdict_without_cited_metrics():
    with pytest.raises(ValidationError, match="no cited"):
        validate(v(cited_metrics={}), SNAP)


def test_rejects_unknown_metric():
    with pytest.raises(ValidationError, match="not in fetched"):
        validate(v(cited_metrics={"macd": 1.0}), SNAP)


def test_rejects_fabricated_value():
    with pytest.raises(ValidationError, match="!= fetched"):
        validate(v(reasoning="RSI 12.0", cited_metrics={"rsi": 12.0}), SNAP)


def test_rejects_reasoning_without_numbers():
    with pytest.raises(ValidationError, match="reasoning"):
        validate(v(reasoning="looks oversold"), SNAP)


def test_rejects_non_numeric_citation():
    with pytest.raises(ValidationError):
        validate(v(cited_metrics={"rsi": "low"}), SNAP)
