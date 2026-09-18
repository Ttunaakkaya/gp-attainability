from __future__ import annotations

import math

import pytest

from attain_sampling.config import ClockConfig, ConfigError
from attain_sampling.sim.scheduler import Event, EventSchedule


@pytest.fixture
def schedule() -> EventSchedule:
    return EventSchedule.from_clocks(
        ClockConfig(control_s=0.2, sampling_s=1.0, planning_s=2.0, logging_s=0.4)
    )


def test_schedule_converts_periods_to_integer_ticks(schedule: EventSchedule) -> None:
    assert schedule.control_s == 0.2
    assert schedule.sample_every == 5
    assert schedule.plan_every == 10
    assert schedule.log_every == 2


@pytest.mark.parametrize(
    ("tick", "expected"),
    [
        (0, (Event.SAMPLE, Event.PLAN, Event.CONTROL, Event.LOG)),
        (1, (Event.CONTROL,)),
        (2, (Event.CONTROL, Event.LOG)),
        (5, (Event.SAMPLE, Event.CONTROL)),
        (10, (Event.SAMPLE, Event.PLAN, Event.CONTROL, Event.LOG)),
    ],
)
def test_events_follow_sample_plan_control_log_order(
    schedule: EventSchedule,
    tick: int,
    expected: tuple[Event, ...],
) -> None:
    assert schedule.events_at(tick) == expected


def test_schedule_rejects_non_integral_clock_ratios() -> None:
    clocks = ClockConfig(control_s=0.2, sampling_s=0.3, planning_s=2.0, logging_s=0.4)

    with pytest.raises(ConfigError, match="sampling_s must be an integer multiple"):
        EventSchedule.from_clocks(clocks)


def test_schedule_rejects_period_shorter_than_control_tick() -> None:
    clocks = ClockConfig(
        control_s=1.0,
        sampling_s=1e-12,
        planning_s=2.0,
        logging_s=1.0,
    )

    with pytest.raises(ConfigError):
        EventSchedule.from_clocks(clocks)


@pytest.mark.parametrize("tick", [-1, -100])
def test_tick_operations_reject_negative_ticks(schedule: EventSchedule, tick: int) -> None:
    with pytest.raises(ValueError, match="tick must be non-negative"):
        schedule.events_at(tick)
    with pytest.raises(ValueError, match="tick must be non-negative"):
        schedule.time_s(tick)


def test_time_uses_integer_tick_as_source_of_truth(schedule: EventSchedule) -> None:
    assert schedule.time_s(0) == 0.0
    assert schedule.time_s(7) == pytest.approx(1.4)


@pytest.mark.parametrize(
    ("duration_s", "expected_ticks"),
    [(0.0, 0), (0.2, 1), (0.21, 2), (1.0, 5), (1.01, 6)],
)
def test_ticks_for_duration_rounds_up(
    schedule: EventSchedule,
    duration_s: float,
    expected_ticks: int,
) -> None:
    assert schedule.ticks_for_duration(duration_s) == expected_ticks


@pytest.mark.parametrize("duration_s", [-0.1, math.inf, -math.inf, math.nan])
def test_ticks_for_duration_requires_finite_non_negative_duration(
    schedule: EventSchedule,
    duration_s: float,
) -> None:
    with pytest.raises(ValueError, match="duration_s must be finite and non-negative"):
        schedule.ticks_for_duration(duration_s)
