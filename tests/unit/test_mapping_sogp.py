"""M3 received-only bounded online belief integration and honest failure records."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from attain_sampling.demo.runner import run_comparison, save_comparison
from attain_sampling.gp.exact import ExactGP
from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sim.mapping import MappingConfig, run_mapping


def config(**changes: Any) -> MappingConfig:
    return replace(
        MappingConfig(
            gp_backend="sogp",
            sogp_max_basis=3,
            robot_count=2,
            duration_s=10,
            grid_shape=(6, 4),
            controller="qp",
            dp_grid_shape=(4, 3),
            dp_horizon_steps=2,
        ),
        **changes,
    )


def query(run: dict[str, Any]) -> np.ndarray:
    xx, yy = np.meshgrid(run["field"]["x"], run["field"]["y"])
    return np.column_stack((xx.ravel(), yy.ravel()))


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive", "dp"])
@pytest.mark.parametrize("robots", [2, 4])
def test_sogp_all_policies_assimilate_every_received_actual_sample(method, robots):
    settings = config(robot_count=robots, drift_strength=0.35, dropout_prob=0.3)
    run = run_mapping(settings, method)
    assert run["status"] == "completed", run["failure"]
    json.dumps(run, allow_nan=False)
    received = [sample for sample in run["samples"] if sample["received"]]
    assert all(sample["received"] == sample["assimilated"] for sample in run["samples"])
    assert len(run["gp_updates"]) == len(received) == run["gp_telemetry"]["observation_count"]
    assert [event["observation_index"] for event in run["gp_updates"]] == list(range(len(received)))
    assert [(event["time_s"], event["robot_id"]) for event in run["gp_updates"]] == [
        (sample["time_s"], sample["robot_id"]) for sample in received
    ]
    gp = SparseOnlineGP(
        length_scale=settings.length_scale,
        signal_variance=settings.signal_variance,
        noise_variance=settings.noise_std**2,
        max_basis=settings.sogp_max_basis,
        novelty_tolerance=settings.sogp_novelty_tolerance,
    )
    gp.update(
        np.asarray([s["actual_position"] for s in received]),
        np.asarray([s["value"] for s in received]),
    )
    prediction = gp.predict(query(run), variance="latent")
    np.testing.assert_allclose(
        np.asarray(run["frames"][-1]["mean"]).ravel(), prediction.mean, atol=1e-8
    )
    np.testing.assert_allclose(
        np.square(run["frames"][-1]["std"]).ravel(), prediction.variance, atol=1e-8
    )
    assert run["gp_telemetry"]["dictionary_size"] == gp.dictionary_size <= 3
    assert run["gp_telemetry"]["pruned_count"] == gp.pruned_count > 0
    for frame in run["frames"]:
        telemetry = frame["gp_telemetry"]
        count = sum(sample["time_s"] <= frame["time_s"] for sample in received)
        assert telemetry["observation_count"] == count
        assert telemetry["admitted_count"] + telemetry["projected_count"] == count
        assert (
            telemetry["admitted_count"] - telemetry["pruned_count"] == telemetry["dictionary_size"]
        )


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive", "dp"])
def test_all_missing_has_no_fantasy_assimilation_or_dictionary(method):
    run = run_mapping(config(dropout_prob=1), method)
    assert run["status"] == "completed"
    assert run["gp_updates"] == []
    assert run["gp_telemetry"]["observation_count"] == run["gp_telemetry"]["dictionary_size"] == 0
    assert run["summary"]["mean_variance"] == pytest.approx(1)
    assert all(not sample["assimilated"] for sample in run["samples"])
    assert all(plan["belief_observation_count"] == 0 for plan in run["plans"])


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive", "dp"])
def test_no_approximation_matches_exact_backend_small_nominal_run(method):
    settings = config(sogp_max_basis=64, sogp_novelty_tolerance=1e-10)
    sparse = run_mapping(settings, method)
    exact = run_mapping(replace(settings, gp_backend="exact"), method)
    assert sparse["status"] == exact["status"] == "completed"
    assert sparse["gp_telemetry"]["pruned_count"] == 0
    np.testing.assert_allclose(
        [row["positions"] for row in sparse["motion"]],
        [row["positions"] for row in exact["motion"]],
        atol=1e-7,
    )
    np.testing.assert_allclose(sparse["frames"][-1]["mean"], exact["frames"][-1]["mean"], atol=1e-8)
    np.testing.assert_allclose(sparse["frames"][-1]["std"], exact["frames"][-1]["std"], atol=1e-8)


def test_dp_forecast_conditions_current_approximate_posterior_without_future_pruning():
    settings = config(sogp_max_basis=2, duration_s=15, robot_count=4)
    run = run_mapping(settings, "dp")
    assert run["status"] == "completed"
    for plan in run["plans"]:
        assert "sogp" in plan["forecast_scope"] and "no_future_pruning" in plan["forecast_scope"]
        assert "exact_gp" not in plan["forecast_scope"]
        assert plan["belief_telemetry"]["dictionary_size"] <= 2
        received = [
            sample
            for sample in run["samples"]
            if sample["received"] and sample["time_s"] <= plan["generated_at_s"]
        ]
        gp = SparseOnlineGP(max_basis=2, noise_variance=settings.noise_std**2)
        gp.update(
            np.asarray([s["actual_position"] for s in received]),
            np.asarray([s["value"] for s in received]),
        )
        before_events = gp.last_update_events
        before_dictionary = gp.dictionary_points
        for epoch, forecast in enumerate(plan["forecast"]):
            sites = np.asarray(plan["targets_by_epoch"][:epoch]).reshape(-1, 2)
            variance = gp.fantasy_variance(query(run), sites)
            assert forecast["mean_variance"] == pytest.approx(float(np.mean(variance)), abs=1e-8)
        assert gp.last_update_events == before_events
        np.testing.assert_array_equal(gp.dictionary_points, before_dictionary)
        assert gp.observation_count == len(received)


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive", "dp"])
def test_failed_second_batch_keeps_committed_gp_and_unassimilated_real_receipts(
    monkeypatch, tmp_path, method
):
    original = SparseOnlineGP.update

    def fail_second_batch(self, x, y):
        if self.observation_count >= 2:
            raise FloatingPointError("injected transactional GP update failure")
        return original(self, x, y)

    monkeypatch.setattr(SparseOnlineGP, "update", fail_second_batch)
    comparison = run_comparison(config(), scenario="nominal", methods=(method,))
    run = comparison["runs"][0]
    assert comparison["status"] == "completed_with_failures"
    assert run["status"] == "failed"
    assert run["failure"]["phase"] == "gp_update"
    assert run["summary"]["completion_time_s"] == 5
    assert run["gp_telemetry"]["observation_count"] == 2
    assert run["summary"]["samples_received"] == 4
    assert run["summary"]["samples_assimilated"] == 2
    assert len(run["gp_updates"]) == 2
    assert len(run["gp_failures"]) == 1
    assert [sample["assimilated"] for sample in run["samples"]] == [True, True, False, False]
    initial_gp = ExactGP(noise_variance=config().noise_std ** 2)
    initial_gp.update(
        np.asarray([s["actual_position"] for s in run["samples"][:2]]),
        np.asarray([s["value"] for s in run["samples"][:2]]),
    )
    initial = initial_gp.predict(query(run), variance="latent")
    np.testing.assert_allclose(
        np.asarray(run["frames"][-1]["mean"]).ravel(), initial.mean, atol=1e-8
    )
    np.testing.assert_allclose(
        np.square(run["frames"][-1]["std"]).ravel(), initial.variance, atol=1e-8
    )
    bundle = save_comparison(comparison, tmp_path)
    restored = json.loads((bundle / "comparison.json").read_text(encoding="utf-8"))
    assert restored["runs"][0]["samples"] == run["samples"]
    assert restored["status"] == "completed_with_failures"


@pytest.mark.parametrize(
    "changes",
    [
        {"gp_backend": "variational"},
        {"sogp_max_basis": 0},
        {"sogp_max_basis": True},
        {"sogp_max_basis": 513},
        {"sogp_novelty_tolerance": -1},
        {"sogp_novelty_tolerance": True},
        {"sogp_novelty_tolerance": float("nan")},
    ],
)
def test_invalid_sogp_configuration_rejected(changes):
    with pytest.raises(ValueError):
        config(**changes)
