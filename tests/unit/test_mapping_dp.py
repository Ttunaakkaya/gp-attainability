"""M2 periodic DP: actual posterior, common clock, QP execution and plan evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from attain_sampling.gp.exact import ExactGP
from attain_sampling.sim import mapping
from attain_sampling.sim.mapping import MappingConfig, run_mapping, segment_min_separation


def _config(**kwargs: Any) -> MappingConfig:
    return replace(MappingConfig(controller="qp", duration_s=20, grid_shape=(8, 6)), **kwargs)


@pytest.mark.parametrize("robots", [2, 3, 4])
@pytest.mark.parametrize("disturbed", [False, True])
@pytest.mark.parametrize("seed", [2, 7])
def test_dp_qp_loop_preserves_actual_measurements_and_geometry(
    robots: int, disturbed: bool, seed: int
) -> None:
    config = _config(
        seed=seed,
        robot_count=robots,
        dropout_prob=0.3 if disturbed else 0,
        drift_strength=0.35 if disturbed else 0,
    )
    result = run_mapping(config, "dp")
    json.dumps(result, allow_nan=False)
    assert result["status"] == "completed", result["failure"]
    assert len(result["plans"]) == 4
    assert result["summary"]["qp_solves"] == 40
    assert result["summary"]["preview_qp_solves"] == 0  # no M4 candidate rollout
    assert result["summary"]["samples_attempted"] == 5 * robots
    assert result["summary"]["planning_s"] >= result["summary"]["dp_planning_s"] > 0
    lookup = {p["plan_id"]: p for p in result["plans"]}
    for previous, state in zip(result["motion"][:-1], result["motion"][1:], strict=True):
        before, after = np.asarray(previous["positions"]), np.asarray(state["positions"])
        event = result["controls"][state["control_event_index"]]
        assert event["phase"] == "execution" and event["success"]
        assert event["plan_id"] == state["plan_id"]
        plan = lookup[state["plan_id"]]
        assert plan["generated_at_s"] < state["time_s"]
        assert event["tracking_time_s"] == pytest.approx(
            plan["sample_times_s"][0] - previous["time_s"]
        )
        np.testing.assert_allclose(
            before + config.dt * np.asarray(event["applied_velocity"]), after, atol=1e-12
        )
        assert segment_min_separation(before, after) >= config.min_separation - 1e-7
        assert np.all(after >= -1e-7)
        assert np.all(after <= np.asarray(config.domain) + 1e-7)
        assert np.max(np.linalg.norm(after - before, axis=1)) <= config.dt * (
            config.max_speed + 1e-7
        )
    for sample in result["samples"]:
        if sample["time_s"] == 0:
            assert sample["plan_id"] is None
        else:
            plan = lookup[sample["plan_id"]]
            assert sample["time_s"] == plan["sample_times_s"][0]
            # The geometric reference interpolates to this target; its arithmetic
            # can leave a sub-picometre residual on different BLAS/platform builds.
            np.testing.assert_allclose(
                sample["planned_position"],
                plan["targets_by_epoch"][0][sample["robot_id"]],
                rtol=0,
                atol=1e-12,
            )


def test_every_forecast_uses_received_actual_belief_and_one_joint_plan_prefix() -> None:
    config = _config(dropout_prob=0.45, drift_strength=0.6, robot_count=2)
    result = run_mapping(config, "dp")
    xx, yy = np.meshgrid(result["field"]["x"], result["field"]["y"])
    query = np.column_stack((xx.ravel(), yy.ravel()))
    assert any(not s["received"] for s in result["samples"])
    assert any(
        not np.allclose(s["actual_position"], s["planned_position"]) for s in result["samples"]
    )
    previous_id = None
    for version, plan in enumerate(result["plans"]):
        received = [
            s for s in result["samples"] if s["received"] and s["time_s"] <= plan["generated_at_s"]
        ]
        assert plan["plan_version"] == version
        assert plan["previous_plan_id"] == previous_id
        previous_id = plan["plan_id"]
        assert plan["received_sample_keys"] == [[s["time_s"], s["robot_id"]] for s in received]
        assert plan["belief_observation_count"] == len(received)
        gp = ExactGP(
            length_scale=config.length_scale,
            signal_variance=config.signal_variance,
            noise_variance=config.noise_std**2,
        )
        if received:
            gp.update(
                np.asarray([s["actual_position"] for s in received]),
                np.asarray([s["value"] for s in received]),
            )
        for epoch, forecast in enumerate(plan["forecast"]):
            sites = np.asarray(plan["targets_by_epoch"][:epoch]).reshape(-1, 2)
            variance = gp.fantasy_variance(query, sites)
            assert forecast["mean_variance"] == pytest.approx(np.mean(variance), abs=1e-9)
            assert forecast["max_variance"] == pytest.approx(np.max(variance), abs=1e-9)
        # The incoming forecast and the newly generated outgoing plan are not confused.
        arrival = next(f for f in result["frames"] if f["time_s"] == plan["sample_times_s"][0])
        assert arrival["forecast_plan_id"] == plan["plan_id"]
        assert arrival["planned_mean_variance"] == plan["forecast"][1]["mean_variance"]


@pytest.mark.parametrize("duration", [2.0, 7.0, 17.0])
def test_common_deadline_and_partial_tail_never_create_a_measurement(duration: float) -> None:
    result = run_mapping(_config(duration_s=duration, robot_count=2), "dp")
    expected_times = list(np.arange(0, duration + 1e-9, 5.0))
    assert [s["time_s"] for s in result["samples"]] == [t for t in expected_times for _ in range(2)]
    assert result["summary"]["completion_time_s"] == duration
    for plan in result["plans"]:
        assert plan["mission_end_s"] == duration
        assert (
            plan["sample_times_s"] == [t for t in expected_times if t > plan["generated_at_s"]][:4]
        )
    tail = result["plans"][-1]
    assert tail["sample_times_s"] == tail["targets_by_epoch"] == []
    assert len(tail["forecast"]) == 1
    assert result["frames"][-1]["forecast_plan_id"] is None


def test_field_values_are_not_a_planner_input(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(duration_s=10, robot_count=2)
    first = run_mapping(config, "dp")
    field = mapping.evaluate_field
    monkeypatch.setattr(mapping, "evaluate_field", lambda p, c: field(p, c) + 100.0)
    second = run_mapping(config, "dp")
    assert first["field"] != second["field"]
    assert first["samples"][0]["value"] != second["samples"][0]["value"]
    for a, b in zip(first["plans"], second["plans"], strict=True):
        assert a["targets_by_epoch"] == b["targets_by_epoch"]
        assert a["forecast"] == b["forecast"]


def test_filter_nominal_timed_motion_and_first_epoch_forecast_match() -> None:
    result = run_mapping(_config(controller="filter", robot_count=2), "dp")
    assert result["status"] == "completed"
    for state in result["motion"]:
        np.testing.assert_allclose(state["positions"], state["planned_positions"], atol=1e-10)
    for frame in result["frames"]:
        assert frame["mean_variance"] == pytest.approx(frame["planned_mean_variance"], abs=1e-8)


def test_nonbinary_clock_has_no_near_zero_duplicate_sampling_interval() -> None:
    config = _config(dt=0.7, sample_period_s=2.1, duration_s=8.4, robot_count=2)
    result = run_mapping(config, "dp")
    assert result["status"] == "completed", result["failure"]
    assert len(result["samples"]) == 10
    assert [len(p["sample_times_s"]) for p in result["plans"]] == [4, 3, 2, 1]
    for plan in result["plans"]:
        assert plan["sample_times_s"][0] - plan["generated_at_s"] == pytest.approx(2.1)
        assert plan["sample_times_s"][-1] == pytest.approx(config.duration_s)
    assert result["motion"][-1]["time_s"] == pytest.approx(config.duration_s)


def test_failed_dp_qp_keeps_plan_and_initial_received_epoch() -> None:
    config = _config(qp_max_iter=1, robot_count=2)
    result = run_mapping(config, "dp")
    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "execution"
    assert result["summary"]["completion_time_s"] == 0
    assert len(result["plans"]) == 1
    assert len(result["samples"]) == 2
    assert result["plans"][0]["belief_observation_count"] == 2
    assert result["controls"][-1]["applied_velocity"] is None
    assert result["controls"][-1]["plan_id"] == result["plans"][0]["plan_id"]
    assert result["frames"][-1]["forecast_plan_id"] is None
    assert result["frames"][-1]["planned_mean_variance"] is None
    json.dumps(result, allow_nan=False)


def test_all_lost_dp_does_not_assimilate_fantasy_measurements() -> None:
    config = _config(dropout_prob=1, robot_count=2, duration_s=10)
    result = run_mapping(config, "dp")
    assert result["status"] == "completed"
    assert result["summary"]["samples_received"] == 0
    assert result["summary"]["mean_variance"] == pytest.approx(config.signal_variance)
    assert all(p["belief_observation_count"] == 0 for p in result["plans"])


def test_dp_usv_is_explicitly_unsupported() -> None:
    with pytest.raises(ValueError, match="holonomic"):
        run_mapping(_config(model="usv", controller="filter"), "dp")


@pytest.mark.parametrize("failure_time", [0.0, 5.0])
def test_planner_numerical_failure_preserves_real_prefix(
    monkeypatch: pytest.MonkeyPatch, failure_time: float
) -> None:
    original = mapping.plan_timed_dp

    def failing_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["now_s"] == failure_time:
            raise FloatingPointError("injected covariance failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(mapping, "plan_timed_dp", failing_plan)
    result = run_mapping(_config(robot_count=2, duration_s=10), "dp")
    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "planning"
    assert result["failure"]["last_executed_time_s"] == failure_time
    assert result["summary"]["completion_time_s"] == failure_time
    assert len(result["plans"]) == int(failure_time / 5)
    assert len(result["samples"]) == 2 * (int(failure_time / 5) + 1)
    assert result["planning_failures"][0]["time_s"] == failure_time
    assert result["summary"]["planning_failures"] == 1
    assert result["summary"]["dp_failed_planning_s"] > 0
    assert result["frames"][-1]["forecast_plan_id"] is None
    assert result["summary"]["qp_failures"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dp_horizon_steps": 0},
        {"dp_horizon_steps": True},
        {"dp_grid_shape": (1, 3)},
        {"dp_grid_shape": (2.5, 4)},
        {"dp_travel_weight": -0.1},
        {"dp_travel_weight": float("nan")},
    ],
)
def test_invalid_dp_configuration(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _config(**kwargs)
