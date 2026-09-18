"""The closed-loop ECC profile: bookkeeping, pairing, constraints and recorded findings."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sim import ecc2025
from attain_sampling.sim.ecc2025 import EccProfileConfig, ground_truth, run_ecc_profile
from attain_sampling.sources.ecc2025 import SourceGateError, parameters

PAPER = parameters()
EDGE = (0.0, 58.0)


@pytest.fixture(scope="module")
def short_runs():
    return {
        (controller, start): run_ecc_profile(
            EccProfileConfig(controller=controller, duration_s=60.0, start_center=start)
        )
        for controller in ("constraint_only", "hierarchical")
        for start in ((0.0, 75.0), EDGE)
    }


def test_epoch_bookkeeping_follows_the_paper_indexing(short_runs):
    run = short_runs[("hierarchical", (0.0, 75.0))]
    epochs = run["epochs"]
    assert run["status"] == "completed"
    assert [entry["l"] for entry in epochs] == list(range(7))
    assert epochs[0]["J"] == pytest.approx(PAPER["evaluation_points"] * 1.0)
    for entry in epochs:
        assert entry["line"] == pytest.approx(epochs[0]["J"] - PAPER["gamma"] * entry["l"])
        assert entry["time_s"] == pytest.approx(entry["l"] * PAPER["t_s"])
    # The paper indexes data from l = 1: no sample at t = 0.
    assert len(run["samples"]) == 6 * PAPER["n"]
    assert min(sample["time_s"] for sample in run["samples"]) == pytest.approx(PAPER["t_s"])


def test_objective_is_recomputed_independently_from_the_recorded_samples(short_runs):
    run = short_runs[("hierarchical", EDGE)]
    queries = np.asarray(run["field"]["queries"])
    model = SparseOnlineGP(
        length_scale=PAPER["L"],
        signal_variance=1.0,
        noise_variance=PAPER["sigma_eps"] ** 2,
        max_basis=int(PAPER["n_d_max"]),
        novelty_tolerance=PAPER["omega"],
    )
    by_epoch: dict[int, list[dict]] = {}
    for sample in run["samples"]:
        by_epoch.setdefault(sample["l"], []).append(sample)
    for entry in run["epochs"][1:]:
        for sample in sorted(by_epoch[entry["l"]], key=lambda item: item["robot"]):
            model.update(np.asarray([sample["position"]]), np.asarray([sample["value"]]))
        variance = model.predict(queries, variance="latent").variance
        assert entry["J"] == pytest.approx(float(np.sum(variance)), rel=1e-12)


def test_both_controllers_share_the_same_measurement_innovations(short_runs):
    truth = ground_truth(7, 40)
    residuals = {}
    for controller in ("constraint_only", "hierarchical"):
        run = short_runs[(controller, EDGE)]
        positions = np.asarray([sample["position"] for sample in run["samples"]])
        values = ecc2025._field(positions, truth)
        residuals[controller] = (
            [(sample["l"], sample["robot"]) for sample in run["samples"]],
            np.asarray([sample["value"] for sample in run["samples"]]) - values,
        )
    keys_e0, noise_e0 = residuals["constraint_only"]
    keys_e1, noise_e1 = residuals["hierarchical"]
    assert keys_e0 == keys_e1
    # Different positions give different field values, but the same innovation per key.
    assert np.allclose(noise_e0, noise_e1, rtol=0.0, atol=1e-9)
    assert np.std(noise_e0) > 0.1


@pytest.mark.parametrize("controller", ["constraint_only", "hierarchical"])
def test_recorded_finding_paths_do_not_depend_on_the_measurements(short_runs, controller):
    """Below n_d,max nothing that moves a robot reads a label, so the seed only changes data.

    Admission, C, the decay-rate row and the planner reward depend on sample sites alone,
    and 1000 s gives at most 300 samples against n_d,max = 360.
    """
    reference = short_runs[(controller, EDGE)]
    other = run_ecc_profile(
        EccProfileConfig(controller=controller, seed=19, duration_s=60.0, start_center=EDGE)
    )
    assert other["trajectory"] == reference["trajectory"]
    assert [entry["J"] for entry in other["epochs"]] == [
        entry["J"] for entry in reference["epochs"]
    ]
    assert [sample["value"] for sample in other["samples"]] != [
        sample["value"] for sample in reference["samples"]
    ]
    assert other["summary"]["final_mse"] != reference["summary"]["final_mse"]
    assert 3 * 1000.0 / PAPER["t_s"] < PAPER["n_d_max"]


def test_recorded_finding_constraint_only_cannot_leave_a_start_outside_the_field(short_runs):
    """With L = 4 m and robots 15 m above F, eq. (12) gives no usable gradient."""
    run = short_runs[("constraint_only", (0.0, 75.0))]
    summary = run["summary"]
    assert summary["max_speed_mps"] < 1e-2
    assert all(entry["J"] == pytest.approx(run["epochs"][0]["J"]) for entry in run["epochs"])


def test_constraint_only_moves_once_it_starts_within_reach_of_the_field(short_runs):
    run = short_runs[("constraint_only", EDGE)]
    assert run["status"] == "completed"
    assert run["summary"]["max_speed_mps"] > 1.0
    assert run["epochs"][-1]["J"] < run["epochs"][0]["J"]


def test_hierarchical_controller_enters_the_field_from_the_paper_start(short_runs):
    run = short_runs[("hierarchical", (0.0, 75.0))]
    assert run["summary"]["max_speed_mps"] > 1.0
    assert run["epochs"][-1]["J"] < run["epochs"][0]["J"]
    assert run["summary"]["planner_solves"] > 0


@pytest.mark.parametrize("key", ["constraint_only", "hierarchical"])
def test_speed_and_separation_limits_hold_on_the_executed_trajectory(short_runs, key):
    run = short_runs[(key, EDGE)]
    summary = run["summary"]
    # The inscribed polygon's vertices sit on the 2 m/s circle.
    assert summary["max_speed_mps"] <= 2.0 + 1e-6
    assert summary["min_separation_m"] >= PAPER["d_ca"] - 1e-6


def test_the_record_is_json_safe_and_states_its_limits(short_runs):
    run = short_runs[("hierarchical", EDGE)]
    json.dumps(run, allow_nan=False)
    assert any("qualitative" in limit for limit in run["claim_limits"])
    assert any("not a numerical reproduction" in limit for limit in run["claim_limits"])
    assert run["paper_values"]["gamma"] == PAPER["gamma"]
    assert "start: three robots 5 m apart at (0, 58)" in run["project_choices"]


def test_a_figure_scale_run_starts_from_the_scaled_prior():
    run = run_ecc_profile(
        EccProfileConfig(
            controller="hierarchical", duration_s=20.0, start_center=EDGE, signal_variance=4.0
        )
    )
    assert run["epochs"][0]["J"] == pytest.approx(4.0 * PAPER["evaluation_points"])
    assert any("figure scale" in choice for choice in run["project_choices"])


def test_snapshots_are_only_taken_at_times_the_run_reaches(short_runs):
    assert short_runs[("hierarchical", EDGE)]["snapshots"] == {}


def test_the_profile_refuses_to_run_if_the_source_gate_is_closed(monkeypatch):
    def locked(claim: str) -> None:
        raise SourceGateError(f"{claim} locked")

    monkeypatch.setattr(ecc2025, "require_unlocked", locked)
    with pytest.raises(SourceGateError):
        run_ecc_profile(EccProfileConfig(controller="hierarchical", duration_s=10.0))


def test_ground_truth_is_seeded_and_reproducible():
    first = ground_truth(19, 40)
    second = ground_truth(19, 40)
    other = ground_truth(31, 40)
    for left, right in zip(first, second, strict=True):
        assert np.array_equal(left, right)
    assert not np.array_equal(first[0], other[0])


@pytest.mark.parametrize(
    "overrides",
    [
        {"controller": "gradient"},
        {"seed": -1},
        {"duration_s": 0.0},
        {"dt": math.nan},
        {"dt": 0.3},
        {"signal_variance": 0.0},
        {"max_waypoints": 0},
        {"grid_count": 1},
        {"start_spacing_m": 1.0},
    ],
)
def test_invalid_profile_settings_are_rejected(overrides):
    options = {"controller": "hierarchical"}
    options.update(overrides)
    with pytest.raises(ValueError):
        EccProfileConfig(**options)
