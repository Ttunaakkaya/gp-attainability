"""The single physical sampling clock shared by plan horizons and mission budgets.

M2 bounded its plan horizon with a private copy of this enumeration. M4 needs the
same epochs to compute a remaining-mission budget that outlives any one plan, so
both read them here: a horizon and a budget can never disagree about which sensing
epochs still exist. Epochs are global-clock multiples of the sampling period, never
offsets from a plan's own generation time, so replanning cannot reset the budget.

An off-grid mission end is clamped to the deadline; it never becomes an extra
measurement. Times are returned only when they are representably later than now.
"""

from __future__ import annotations

import math

__all__ = ["remaining_sample_times"]


def remaining_sample_times(
    now_s: float,
    end_s: float,
    period_s: float,
    *,
    limit: int | None = None,
) -> list[float]:
    """Return future global sampling epochs in ``(now_s, end_s]``.

    ``limit`` bounds the count for a planning horizon; ``None`` enumerates every
    remaining epoch for budget accounting. Returning fewer epochs than ``limit``
    means the mission ends first, not that sampling became infeasible.
    """
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in (now_s, end_s, period_s)
    ):
        raise ValueError("clock arguments must be finite real numbers")
    now, end, period = float(now_s), float(end_s), float(period_s)
    if period <= 0:
        raise ValueError("period_s must be positive")
    if now < 0 or end < now:
        raise ValueError("end_s must not precede a non-negative now_s")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0):
        raise ValueError("limit must be a non-negative integer or None")
    if now == end:
        return []
    ratio = now / period
    if not math.isfinite(ratio):
        raise ValueError("sample period is too small for the current time")
    # The simulator clock may form e.g. 3 * 0.7 = 2.0999999999999996 while the
    # period is 2.1. Treat only ULP-scale discrepancies as the same scheduled
    # epoch, not as an almost-zero-time extra future measurement.
    nearest_epoch = round(ratio)
    aligned = abs(ratio - nearest_epoch) <= 8 * math.ulp(ratio)
    next_epoch = (nearest_epoch if aligned else math.floor(ratio)) + 1
    if limit is None:
        span = (end - now) / period
        # A termination cap only; the deadline break below decides the result.
        limit = max(0, int(math.floor(span)) + 2) if math.isfinite(span) else 0
    result: list[float] = []
    tolerance = max(math.ulp(end), math.ulp(now), math.ulp(period)) * 8
    for epoch in range(next_epoch, next_epoch + limit):
        sample_time = epoch * period
        if not math.isfinite(sample_time) or sample_time <= now:
            raise ValueError("sample times must be representably later than now_s")
        if sample_time > end + tolerance:
            break
        result.append(float(min(sample_time, end)))
    if any(second <= first for first, second in zip(result, result[1:], strict=False)):
        raise ValueError("sample period is too small to represent distinct epochs")
    return result
