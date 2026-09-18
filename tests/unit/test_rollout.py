"""Candidate rollout: where the controller would really sample, and when it cannot."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from attain_sampling.attainability.rollout import StepOutcome, rollout_plan


def ideal_stepper(reached_fraction: float = 1.0, log: list | None = None):
    """Move a fixed fraction of the way to the target each control interval."""

    def step(positions, headings, targets, *, tick, tracking_time_s):
        if log is not None:
            log.append((tick, tracking_time_s))
        moved = positions + reached_fraction * (targets - positions)
        return StepOutcome(
            accepted=True,
            positions=moved,
            headings=headings,
            intervention=False,
            min_separation=5.0,
        )

    return step


def rejecting_stepper(reject_at_tick: int):
    def step(positions, headings, targets, *, tick, tracking_time_s):
        if tick >= reject_at_tick:
            return StepOutcome(
                accepted=False,
                positions=positions,
                headings=headings,
                intervention=False,
                min_separation=math.nan,
                failure_reason="solver_rejected",
            )
        return StepOutcome(
            accepted=True,
            positions=positions + 1.0,
            headings=headings,
            intervention=True,
            min_separation=3.0,
        )

    return step


START = np.asarray([[0.0, 0.0], [0.0, 10.0]])
HEADINGS = np.zeros(2)
TARGETS = np.asarray([[[4.0, 0.0], [4.0, 10.0]], [[8.0, 0.0], [8.0, 10.0]]])


def test_rollout_reports_reached_positions_not_commanded_targets():
    result = rollout_plan(
        ideal_stepper(0.5),
        START,
        HEADINGS,
        TARGETS,
        start_tick=0,
        epoch_ticks=[2, 4],
        dt=0.5,
    )
    assert result.feasible
    assert result.completed_epochs == 2
    assert result.sample_positions.shape == (2, 2, 2)
    # Halving the gap twice leaves the fleet short of each commanded cell.
    assert result.sample_positions[0][0][0] == pytest.approx(3.0)
    assert result.max_target_error_m > 0.5
    assert result.control_calls == 4


def test_an_exact_tracker_lands_on_its_commanded_cells():
    result = rollout_plan(
        ideal_stepper(1.0), START, HEADINGS, TARGETS, start_tick=0, epoch_ticks=[2, 4], dt=0.5
    )
    assert result.sample_positions == pytest.approx(TARGETS)
    assert result.max_target_error_m == pytest.approx(0.0)


def test_each_interval_requests_arrival_at_its_own_deadline():
    log: list = []
    rollout_plan(
        ideal_stepper(1.0, log),
        START,
        HEADINGS,
        TARGETS,
        start_tick=10,
        epoch_ticks=[13, 16],
        dt=0.5,
    )
    # Time-to-deadline counts down inside an interval and restarts at the next one.
    assert [entry[0] for entry in log] == [11, 12, 13, 14, 15, 16]
    assert [entry[1] for entry in log] == pytest.approx([1.5, 1.0, 0.5, 1.5, 1.0, 0.5])


def test_a_rejected_command_stops_the_candidate_and_keeps_its_prefix():
    result = rollout_plan(
        rejecting_stepper(reject_at_tick=3),
        START,
        HEADINGS,
        TARGETS,
        start_tick=0,
        epoch_ticks=[2, 4],
        dt=0.5,
    )
    assert not result.feasible
    assert result.failure_reason == "solver_rejected"
    assert result.failed_epoch == 1
    # The first epoch completed, so its site is retained rather than discarded.
    assert result.completed_epochs == 1
    assert result.interventions == 2
    assert result.min_separation == pytest.approx(3.0)
    json.dumps(result.as_dict(), allow_nan=False)


def test_rejection_at_the_first_step_leaves_no_sample_sites():
    result = rollout_plan(
        rejecting_stepper(reject_at_tick=1),
        START,
        HEADINGS,
        TARGETS,
        start_tick=0,
        epoch_ticks=[2, 4],
        dt=0.5,
    )
    assert not result.feasible
    assert result.completed_epochs == 0
    assert result.sample_positions.shape == (0, 2, 2)
    assert result.min_separation is None
    assert result.as_dict()["min_separation_m"] is None
    json.dumps(result.as_dict(), allow_nan=False)


def test_an_empty_rollout_has_no_measured_separation_and_is_json_safe():
    result = rollout_plan(
        ideal_stepper(),
        START,
        HEADINGS,
        np.empty((0, 2, 2)),
        start_tick=0,
        epoch_ticks=[],
        dt=0.5,
    )
    assert result.feasible
    assert result.control_calls == 0
    assert result.completed_epochs == 0
    assert result.min_separation is None
    json.dumps(result.as_dict(), allow_nan=False)


def test_record_is_json_safe_and_declares_its_nominal_scope():
    record = rollout_plan(
        ideal_stepper(1.0), START, HEADINGS, TARGETS, start_tick=0, epoch_ticks=[2, 4], dt=0.5
    ).as_dict()
    assert "no future disturbance" in record["scope"]
    assert isinstance(record["sample_positions"], list)
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize(
    "overrides",
    [
        {"epoch_ticks": [4, 2]},
        {"epoch_ticks": [0, 4]},
        {"epoch_ticks": [2]},
        {"epoch_ticks": [2.5, 4]},
        {"dt": 0.0},
        {"start_tick": -1},
        {"targets_by_epoch": np.zeros((2, 3, 2))},
        {"headings": np.zeros(3)},
    ],
)
def test_inconsistent_rollout_requests_are_rejected(overrides):
    options = {
        "positions": START,
        "headings": HEADINGS,
        "targets_by_epoch": TARGETS,
        "start_tick": 0,
        "epoch_ticks": [2, 4],
        "dt": 0.5,
    }
    options.update(overrides)
    with pytest.raises(ValueError):
        rollout_plan(ideal_stepper(1.0), **options)
