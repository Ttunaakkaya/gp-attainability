"""The remaining-mission budget must run down and must survive replanning."""

from __future__ import annotations

import pytest

from attain_sampling.attainability.budget import mission_budget


def budget(now: float, **overrides):
    options = {
        "now_s": now,
        "mission_end_s": 90.0,
        "sample_period_s": 5.0,
        "robot_count": 3,
        "max_speed": 2.0,
    }
    options.update(overrides)
    return mission_budget(**options)


def test_elapsed_and_remaining_partition_the_mission():
    for now in (0.0, 5.0, 7.5, 45.0, 89.5, 90.0):
        value = budget(now)
        assert value.elapsed_sample_epochs + value.remaining_sample_epochs == (
            value.total_sample_epochs
        )
        assert value.total_sample_epochs == 19


def test_epoch_zero_counts_as_elapsed_because_every_mission_samples_there():
    start = budget(0.0)
    assert start.elapsed_sample_epochs == 1
    assert start.remaining_sample_epochs == 18


def test_an_early_event_triggered_decision_neither_gains_nor_loses_an_epoch():
    on_epoch = budget(45.0)
    mid_interval = budget(47.5)
    assert mid_interval.remaining_sample_epochs == on_epoch.remaining_sample_epochs
    assert mid_interval.remaining_time_s < on_epoch.remaining_time_s
    assert mid_interval.is_successor_of(on_epoch)


def test_budget_runs_down_monotonically():
    previous = budget(0.0)
    for tick in range(1, 181):
        current = budget(tick * 0.5)
        assert current.is_successor_of(previous)
        previous = current
    assert previous.remaining_sample_epochs == 0
    assert previous.remaining_time_s == pytest.approx(0.0)


def test_a_replanned_deadline_or_rewound_clock_is_not_a_successor():
    reference = budget(45.0)
    # Restarting the horizon from the new plan would buy back budget.
    assert not budget(45.0, mission_end_s=135.0).is_successor_of(reference)
    assert not budget(40.0).is_successor_of(reference)
    assert not budget(45.0, sample_period_s=2.5).is_successor_of(reference)
    assert not budget(45.0, robot_count=4).is_successor_of(reference)


def test_travel_bound_scales_with_fleet_and_remaining_time():
    value = budget(45.0)
    assert value.fleet_travel_budget_m == pytest.approx(3 * 2.0 * 45.0)
    assert budget(90.0).fleet_travel_budget_m == pytest.approx(0.0)


def test_protocol_view_matches_the_recorded_budget():
    value = budget(45.0)
    narrow = value.as_protocol_budget()
    assert narrow.remaining_samples == value.remaining_sample_epochs
    assert narrow.remaining_time_s == pytest.approx(value.remaining_time_s)


def test_record_is_json_safe_and_states_its_scope():
    record = budget(45.0).as_dict()
    assert isinstance(record["remaining_sample_times_s"], list)
    assert "not energy or executability" in record["scope"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"now_s": -1.0},
        {"mission_end_s": 10.0, "now_s": 20.0},
        {"sample_period_s": 0.0},
        {"max_speed": 0.0},
        {"robot_count": 0},
        {"robot_count": True},
        {"robot_count": 2.5},
    ],
)
def test_invalid_budget_inputs_are_rejected(overrides):
    with pytest.raises(ValueError):
        budget(overrides.pop("now_s", 10.0), **overrides)
