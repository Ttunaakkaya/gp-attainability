"""The one sampling clock: a plan horizon and a mission budget must never disagree."""

from __future__ import annotations

import math

import pytest

from attain_sampling.planning.clock import remaining_sample_times
from attain_sampling.planning.timed_dp import _sample_times


@pytest.mark.parametrize(
    ("now", "end", "period", "limit", "expected"),
    [
        (0.0, 20.0, 5.0, 4, [5.0, 10.0, 15.0, 20.0]),
        (0.0, 20.0, 5.0, 2, [5.0, 10.0]),
        (5.0, 20.0, 5.0, 4, [10.0, 15.0, 20.0]),
        (7.5, 20.0, 5.0, 4, [10.0, 15.0, 20.0]),
        (20.0, 20.0, 5.0, 4, []),
        # An off-grid deadline ends the mission without adding a measurement there.
        (0.0, 17.0, 5.0, 4, [5.0, 10.0, 15.0]),
    ],
)
def test_epochs_follow_the_global_clock(now, end, period, limit, expected):
    assert remaining_sample_times(now, end, period, limit=limit) == pytest.approx(expected)


def test_a_deadline_that_only_rounds_onto_an_epoch_still_yields_that_epoch():
    # 0.1 * 3 is 0.30000000000000004; the final epoch is clamped to the deadline
    # rather than dropped, but an epoch genuinely past the end is never invented.
    end = 0.1 * 3
    assert end != 0.3
    times = remaining_sample_times(0.0, end, 0.1, limit=5)
    assert len(times) == 3
    assert times[-1] == pytest.approx(end)
    assert times[-1] <= end


def test_unbounded_enumeration_matches_the_bounded_horizon_prefix():
    unbounded = remaining_sample_times(3.0, 90.0, 5.0)
    for limit in range(0, 8):
        assert remaining_sample_times(3.0, 90.0, 5.0, limit=limit) == unbounded[:limit]


def test_planner_horizon_delegates_to_the_shared_clock():
    for now in (0.0, 2.5, 5.0, 12.5, 84.5):
        assert _sample_times(now, 90.0, 5.0, 4) == remaining_sample_times(now, 90.0, 5.0, limit=4)


def test_accumulated_float_time_is_not_read_as_an_extra_epoch():
    # 3 * 0.7 is 2.0999999999999996 while the period is exactly 2.1.
    now = 0.7 * 3
    assert now != 2.1
    assert remaining_sample_times(now, 10.5, 2.1, limit=2) == pytest.approx([4.2, 6.3])


def test_budget_view_counts_every_remaining_epoch_of_a_full_mission():
    times = remaining_sample_times(0.0, 90.0, 5.0)
    assert len(times) == 18
    assert times[0] == pytest.approx(5.0)
    assert times[-1] == pytest.approx(90.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"now_s": -1.0, "end_s": 10.0, "period_s": 5.0},
        {"now_s": 11.0, "end_s": 10.0, "period_s": 5.0},
        {"now_s": 0.0, "end_s": 10.0, "period_s": 0.0},
        {"now_s": 0.0, "end_s": 10.0, "period_s": -5.0},
        {"now_s": math.nan, "end_s": 10.0, "period_s": 5.0},
        {"now_s": 0.0, "end_s": math.inf, "period_s": 5.0},
        {"now_s": True, "end_s": 10.0, "period_s": 5.0},
    ],
)
def test_invalid_clocks_are_rejected(kwargs):
    with pytest.raises(ValueError):
        remaining_sample_times(**kwargs)


@pytest.mark.parametrize("limit", [-1, 1.5, True])
def test_invalid_limits_are_rejected(limit):
    with pytest.raises(ValueError):
        remaining_sample_times(0.0, 10.0, 5.0, limit=limit)
