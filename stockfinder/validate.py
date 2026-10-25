import math
import logging
import re

from . import scenarios

log = logging.getLogger(__name__)
NUM = re.compile(r"-?\d+(?:\.\d+)?")


class ValidationError(Exception):
    """AI verdict cites no data, or cites data that doesn't match the fetched snapshot (V2)."""


def _close(a, b):
    return math.isclose(a, b, rel_tol=0.01, abs_tol=0.05)


def validate(verdict, snapshot):
    """Return verdict if every cited metric matches the snapshot and reasoning quotes at least one."""
    data = {**snapshot["fundamentals"], **snapshot["technicals"]}
    cited = verdict["cited_metrics"]
    if not cited:
        raise ValidationError("no cited metrics")
    for name, val in cited.items():
        if name not in data:
            raise ValidationError(f"cited metric not in fetched data: {name}")
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not _close(val, data[name]):
            raise ValidationError(f"cited {name}={val!r} != fetched {data[name]}")
    quoted = [float(n) for n in NUM.findall(verdict["reasoning"])]
    if not any(_close(q, v) for q in quoted for v in cited.values()):
        raise ValidationError("reasoning quotes none of the cited values")
    if "scenarios" in verdict:  # optional extra: a bad table is dropped, the verdict stays
        clean = scenarios.clean(verdict["scenarios"], snapshot, verdict["signal"])
        if clean is None:
            log.warning("dropping scenarios: malformed or outside the volatility band")
        verdict = {**verdict, "scenarios": clean}
    return verdict
