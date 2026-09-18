"""Behavioral checks for the independent end-to-end mapping simulator."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from attain_sampling.gp.exact import ExactGP
from attain_sampling.sim.mapping import (
    MappingConfig,
    evaluate_field,
    run_mapping,
    safe_displacement,
    segment_min_separation,
)


@pytest.fixture
def small_config() -> MappingConfig:
    return MappingConfig(
        duration_s=10.0,
        dt=0.5,
        sample_period_s=5.0,
        grid_shape=(8, 6),
        robot_count=3,
    )


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive"])
def test_complete_mapping_artifact(small_config: MappingConfig, method: str) -> None:
    result = run_mapping(small_config, method)
    json.dumps(result, allow_nan=False)
    assert result["schema_version"] == 1
    assert len(result["motion"]) == 21
    assert [frame["time_s"] for frame in result["frames"]] == [0.0, 5.0, 10.0]
    assert result["summary"]["samples_attempted"] == 9
    assert result["summary"]["samples_received"] == 9
    assert result["summary"]["path_length"] > 0
    assert result["summary"]["mean_variance"] < result["frames"][0]["mean_variance"]
    assert result["summary"]["runtime_s"] >= result["summary"]["planning_s"]


def test_metrics_recomputed_from_raw_records(small_config: MappingConfig) -> None:
    config = replace(small_config, dropout_prob=0.3, drift_strength=0.35)
    result = run_mapping(config, "adaptive")
    final = result["frames"][-1]
    truth = np.asarray(result["field"]["truth"])
    mean = np.asarray(final["mean"])
    np.testing.assert_allclose(final["error"], mean - truth)
    assert result["summary"]["rmse"] == pytest.approx(np.sqrt(np.mean((mean - truth) ** 2)))
    assert result["summary"]["mean_variance"] == pytest.approx(np.mean(np.square(final["std"])))
    assert result["summary"]["max_variance"] == pytest.approx(np.max(np.square(final["std"])))
    path = np.array([state["positions"] for state in result["motion"]])
    assert result["summary"]["path_length"] == pytest.approx(
        np.sum(np.linalg.norm(np.diff(path, axis=0), axis=2))
    )
    assert result["summary"]["samples_received"] == sum(
        sample["received"] for sample in result["samples"]
    )
    # Rebuild the exact belief from only the successful actual measurement records.
    gp = ExactGP(
        length_scale=config.length_scale,
        signal_variance=config.signal_variance,
        noise_variance=config.noise_std**2,
    )
    received = [sample for sample in result["samples"] if sample["received"]]
    gp.update(
        np.array([sample["actual_position"] for sample in received]),
        np.array([sample["value"] for sample in received]),
    )
    xx, yy = np.meshgrid(result["field"]["x"], result["field"]["y"])
    prediction = gp.predict(np.column_stack((xx.ravel(), yy.ravel())), variance="latent")
    np.testing.assert_allclose(mean.ravel(), prediction.mean, atol=1e-8)
    np.testing.assert_allclose(np.square(final["std"]).ravel(), prediction.variance, atol=1e-8)


def test_paired_noise_dropout_and_initial_state(small_config: MappingConfig) -> None:
    config = replace(small_config, dropout_prob=0.4, drift_strength=0.35)
    runs = [run_mapping(config, method) for method in ("sweep", "greedy", "adaptive")]
    for run in runs[1:]:
        assert run["initial_positions"] == runs[0]["initial_positions"]
        assert run["field"] == runs[0]["field"]
        for baseline, sample in zip(runs[0]["samples"], run["samples"], strict=True):
            for key in ("time_s", "robot_id", "noise_innovation", "dropout_uniform", "received"):
                assert baseline[key] == sample[key]
    assert runs[0]["motion"][-1]["positions"] != runs[1]["motion"][-1]["positions"]


@pytest.mark.parametrize("controller", ["filter", "qp"])
def test_deterministic_except_timing(small_config: MappingConfig, controller: str) -> None:
    config = replace(small_config, drift_strength=0.35, dropout_prob=0.3, controller=controller)
    first, second = run_mapping(config, "adaptive"), run_mapping(config, "adaptive")
    for result in (first, second):
        for key in (
            "runtime_s",
            "planning_s",
            "gp_s",
            "control_s",
            "control_preview_s",
            "control_median_s",
            "control_p95_s",
            "control_max_s",
        ):
            result["summary"].pop(key)
        for event in result["controls"]:
            for key in (
                "wall_s",
                "setup_s",
                "solve_s",
                "setup_wall_s",
                "solve_wall_s",
                "control_s",
            ):
                event.pop(key, None)
    assert first == second


@pytest.mark.parametrize("model", ["holonomic", "usv"])
@pytest.mark.parametrize("robot_count", [2, 4])
def test_motion_constraints_under_disturbance(
    small_config: MappingConfig, model: str, robot_count: int
) -> None:
    config = replace(
        small_config,
        model=model,
        robot_count=robot_count,
        drift_strength=2.0,
        domain=(15.0, 12.0),
        min_separation=2.0,
    )
    result = run_mapping(config, "adaptive")
    path = np.array([state["positions"] for state in result["motion"]])
    assert np.all(path >= 0)
    assert np.all(path <= np.asarray(config.domain))
    assert (
        np.max(np.linalg.norm(np.diff(path, axis=0), axis=2)) <= config.max_speed * config.dt + 1e-9
    )
    for start, end in zip(path[:-1], path[1:], strict=True):
        assert segment_min_separation(start, end) >= config.min_separation - 1e-9
    if model == "usv":
        assert result["summary"]["max_turn_rate_observed"] <= config.max_turn_rate + 1e-9
        for state in result["motion"][1:]:
            assert max(np.abs(state["turn_rates"])) <= config.max_turn_rate + 1e-9


def test_collision_check_catches_crossing_paths(small_config: MappingConfig) -> None:
    start = np.array([[2.0, 5.0], [8.0, 5.0]])
    desired = np.array([[8.0, 5.0], [2.0, 5.0]])
    assert np.linalg.norm(desired[0] - desired[1]) > small_config.min_separation
    assert segment_min_separation(start, desired) == pytest.approx(0)
    result, intervention, separation = safe_displacement(start, desired - start, small_config)
    assert intervention
    assert separation >= small_config.min_separation
    assert segment_min_separation(start, result) >= small_config.min_separation


def test_backtracking_preserves_bounds(small_config: MappingConfig) -> None:
    positions = np.array([[59.0, 5.0], [20.0, 20.0]])
    displacement = np.array([[4.0, 0.0], [2.0, 0.0]])
    result, intervention, _ = safe_displacement(positions, displacement, small_config)
    assert intervention
    assert np.all(result <= np.asarray(small_config.domain))


def test_invalid_start_rejected(small_config: MappingConfig) -> None:
    with pytest.raises(ValueError, match="separation"):
        safe_displacement(np.array([[1.0, 1.0], [1.0, 1.0]]), np.zeros((2, 2)), small_config)
    with pytest.raises(ValueError, match="outside"):
        safe_displacement(np.array([[-1.0, 1.0], [10.0, 1.0]]), np.zeros((2, 2)), small_config)


def test_all_measurements_lost_keeps_prior(small_config: MappingConfig) -> None:
    result = run_mapping(replace(small_config, dropout_prob=1.0), "adaptive")
    assert result["summary"]["samples_received"] == 0
    assert result["summary"]["mean_variance"] == pytest.approx(small_config.signal_variance)
    assert all(sample["value"] is None for sample in result["samples"])
    assert all(np.allclose(frame["mean"], 0) for frame in result["frames"])


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive"])
def test_nominal_execution_matches_preview(small_config: MappingConfig, method: str) -> None:
    result = run_mapping(small_config, method)
    for state in result["motion"]:
        np.testing.assert_allclose(state["positions"], state["planned_positions"], atol=1e-12)
    for frame in result["frames"]:
        assert frame["mean_variance"] == pytest.approx(frame["planned_mean_variance"], abs=1e-8)


def test_partial_final_interval_does_not_invent_measurements(small_config: MappingConfig) -> None:
    result = run_mapping(replace(small_config, duration_s=7.0), "adaptive")
    assert result["frames"][-1]["time_s"] == 7.0
    assert result["summary"]["samples_attempted"] == 6
    assert [sample["time_s"] for sample in result["samples"]] == [0.0] * 3 + [5.0] * 3


def test_truth_is_seeded_and_spatially_nonconstant(small_config: MappingConfig) -> None:
    points = np.array([[5.0, 5.0], [15.0, 12.0], [45.0, 25.0]])
    first = evaluate_field(points, small_config)
    np.testing.assert_array_equal(first, evaluate_field(points, small_config))
    assert np.ptp(first) > 0.1
    assert not np.allclose(first, evaluate_field(points, replace(small_config, seed=8)))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"robot_count": 1},
        {"robot_count": True},
        {"robot_count": 3.0},
        {"duration_s": 0},
        {"duration_s": 1e-12},
        {"dt": float("nan")},
        {"sample_period_s": 0.3},
        {"duration_s": 1.1},
        {"noise_std": -1},
        {"dropout_prob": 1.1},
        {"drift_strength": -1},
        {"domain": (0, 10)},
        {"domain": (10, 1)},
        {"grid_shape": (1, 2)},
        {"grid_shape": (2.5, 3)},
        {"model": "unknown"},
        {"controller": "unknown"},
        {"controller": "qp", "model": "usv"},
        {"qp_alpha": 0},
        {"qp_max_iter": 0},
        {"qp_polygon_sides": 5},
        {"qp_acceptance_tol": float("nan")},
        {"seed": -1},
        {"seed": True},
    ],
)
def test_invalid_configuration(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        MappingConfig(**kwargs)


def test_unknown_method(small_config: MappingConfig) -> None:
    with pytest.raises(ValueError, match="method"):
        run_mapping(small_config, "unknown")
