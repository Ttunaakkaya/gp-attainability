"""M1 control/sensing loop, independent motion checks and fail-closed recording."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from attain_sampling.sim import mapping
from attain_sampling.sim.mapping import MappingConfig, run_mapping, segment_min_separation


@pytest.mark.parametrize("robots", [2, 3, 4])
@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive"])
@pytest.mark.parametrize("disturbed", [False, True])
def test_qp_sensor_loop_and_independent_geometry(robots: int, method: str, disturbed: bool) -> None:
    config = MappingConfig(
        controller="qp",
        robot_count=robots,
        duration_s=10.0,
        grid_shape=(8, 6),
        drift_strength=0.35 if disturbed else 0.0,
        dropout_prob=0.3 if disturbed else 0.0,
    )
    result = run_mapping(config, method)
    json.dumps(result, allow_nan=False)
    assert result["status"] == "completed", result["failure"]
    assert result["summary"]["completion_time_s"] == config.duration_s
    assert result["summary"]["qp_solves"] == 20
    assert result["summary"]["preview_qp_solves"] == 20
    assert result["summary"]["qp_failures"] == 0
    assert result["summary"]["samples_attempted"] == 3 * robots
    assert result["summary"]["mean_variance"] < config.signal_variance
    path = np.array([state["positions"] for state in result["motion"]])
    tolerance = config.qp_acceptance_tol
    assert np.all(path >= -tolerance)
    assert np.all(path <= np.asarray(config.domain) + tolerance)
    assert (
        np.max(np.linalg.norm(np.diff(path, axis=0), axis=2))
        <= (config.max_speed + tolerance) * config.dt
    )
    assert result["motion"][0]["control_event_index"] is None
    for start, state in zip(path[:-1], result["motion"][1:], strict=True):
        event = result["controls"][state["control_event_index"]]
        assert event["phase"] == "execution" and event["success"]
        assert event["time_s"] == state["time_s"]
        np.testing.assert_allclose(event["positions_before"], start, atol=1e-12)
        np.testing.assert_allclose(
            start + config.dt * np.asarray(event["applied_velocity"]),
            state["positions"],
            atol=1e-12,
        )
        assert segment_min_separation(start, np.asarray(state["positions"])) >= (
            config.min_separation - tolerance
        )
    if not disturbed:
        for state in result["motion"]:
            np.testing.assert_allclose(state["positions"], state["planned_positions"], atol=1e-10)
        for frame in result["frames"]:
            assert frame["mean_variance"] == pytest.approx(frame["planned_mean_variance"], abs=1e-8)


def test_qp_does_not_call_reference_backtracking(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("QP must apply its verified command without the legacy filter")

    monkeypatch.setattr(mapping, "safe_displacement", forbidden)
    result = run_mapping(
        MappingConfig(controller="qp", duration_s=5, grid_shape=(4, 4)), "adaptive"
    )
    assert result["status"] == "completed"


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive"])
def test_qp_preview_failure_is_not_a_completed_mission(method: str) -> None:
    config = MappingConfig(controller="qp", qp_max_iter=1, duration_s=10, grid_shape=(4, 4))
    result = run_mapping(config, method)
    json.dumps(result, allow_nan=False)
    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "preview"
    assert result["failure"]["last_executed_time_s"] == 0
    assert result["summary"]["completion_time_s"] == 0
    assert result["summary"]["path_length"] == 0
    assert result["summary"]["qp_solves"] == 0
    assert result["summary"]["preview_qp_failures"] == 1
    assert result["summary"]["control_median_s"] is None
    assert len(result["motion"]) == len(result["frames"]) == 1
    assert result["frames"][-1]["planned_mean_variance"] is None
    assert result["controls"][-1]["applied_velocity"] is None
    assert result["summary"]["planning_s"] >= result["summary"]["control_preview_s"]


def test_execution_failure_keeps_last_reached_state_and_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    advance = mapping._advance

    def limited_advance(
        positions: Any,
        headings: Any,
        targets: Any,
        config: MappingConfig,
        tick: int,
        **kwargs: Any,
    ) -> Any:
        if kwargs.get("phase") == "execution" and tick == 13:
            config = replace(config, qp_max_iter=1)
        return advance(positions, headings, targets, config, tick, **kwargs)

    monkeypatch.setattr(mapping, "_advance", limited_advance)
    config = MappingConfig(controller="qp", duration_s=10, grid_shape=(8, 6))
    result = run_mapping(config, "adaptive")
    json.dumps(result, allow_nan=False)
    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "execution"
    assert result["failure"]["tick"] == 13
    assert result["failure"]["last_executed_time_s"] == 6.0
    assert result["summary"]["completion_time_s"] == 6.0
    assert [frame["time_s"] for frame in result["frames"]] == [0.0, 5.0, 6.0]
    assert [sample["time_s"] for sample in result["samples"]] == [0.0] * 3 + [5.0] * 3
    assert len(result["motion"]) == 13
    assert result["summary"]["qp_failures"] == 1
    rejected = result["controls"][-1]
    assert rejected["applied_velocity"] is None
    assert rejected["positions_before"] == result["motion"][-1]["positions"]
    assert result["summary"]["path_length"] > 0
    assert result["summary"]["samples_received"] == 6
    assert result["summary"]["runtime_s"] >= sum(
        result["summary"][name] for name in ("planning_s", "control_s", "gp_s")
    )


def test_partial_horizon_with_no_receipts_does_not_invent_data() -> None:
    config = MappingConfig(controller="qp", duration_s=7, dropout_prob=1, grid_shape=(4, 4))
    result = run_mapping(config, "adaptive")
    assert result["status"] == "completed"
    assert result["summary"]["samples_received"] == 0
    assert result["summary"]["samples_attempted"] == 6
    assert result["summary"]["mean_variance"] == pytest.approx(config.signal_variance)
    assert [frame["time_s"] for frame in result["frames"]] == [0.0, 5.0, 7.0]
