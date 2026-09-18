"""ECC profile figures are drawn from recorded runs and refuse mismatched pairs."""

from __future__ import annotations

import copy

import pytest

from attain_sampling.sim.ecc2025 import EccProfileConfig, run_ecc_profile
from attain_sampling.sim.ecc2025_figures import render_ecc_pair, render_ecc_summary

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def pair():
    runs = [
        run_ecc_profile(
            EccProfileConfig(controller=controller, duration_s=20.0, start_center=(0.0, 58.0))
        )
        for controller in ("constraint_only", "hierarchical")
    ]
    # A 20 s run reaches no snapshot time; give one run a recorded-shape snapshot so both
    # the drawn and the "not reached" panels are exercised.
    last = runs[1]["trajectory"][-1]["positions"]
    runs[1]["snapshots"]["320"] = {
        "variance": [0.5] * len(runs[1]["field"]["values"]),
        "mean": [0.0] * len(runs[1]["field"]["values"]),
        "positions": last,
        "basis": [sample["position"] for sample in runs[1]["samples"]],
    }
    return runs


def test_a_pair_renders_three_png_figures(pair, tmp_path):
    paths = render_ecc_pair(pair[0], pair[1], tmp_path / "figures", "B_s7")
    assert [path.name for path in paths] == [
        "B_s7_trajectories.png",
        "B_s7_objective_error.png",
        "B_s7_variance.png",
    ]
    for path in paths:
        assert path.read_bytes().startswith(PNG)


def test_a_failed_run_is_still_drawn(pair, tmp_path):
    failed = copy.deepcopy(pair[0])
    failed["status"] = "failed"
    paths = render_ecc_pair(failed, pair[1], tmp_path, "failed")
    assert all(path.stat().st_size > 0 for path in paths)


def test_pairs_must_be_ordered_and_matched(pair, tmp_path):
    with pytest.raises(ValueError, match="constraint-only run first"):
        render_ecc_pair(pair[1], pair[0], tmp_path, "swapped")
    other = copy.deepcopy(pair[1])
    other["config"]["seed"] = 19
    with pytest.raises(ValueError, match="share seed"):
        render_ecc_pair(pair[0], other, tmp_path, "mismatch")
    foreign = copy.deepcopy(pair[0])
    foreign["profile"] = "independent"
    with pytest.raises(ValueError, match="ecc2025"):
        render_ecc_pair(foreign, pair[1], tmp_path, "foreign")


def test_summary_draws_every_configuration_including_failures(tmp_path):
    def row(name, seed, failed):
        return {
            "configuration": name,
            "seed": seed,
            "failed_runs": {"E0": {"time_s": 5.0}} if failed else {},
            "E0": {"final_J": 900.0, "final_mse": 3000.0},
            "E1": {"final_J": 400.0, "final_mse": 200.0},
        }

    validation = {
        "results": [row("A_theorem", 7, False), row("A_theorem", 19, True), row("B_edge", 7, False)]
    }
    path = render_ecc_summary(validation, tmp_path)
    assert path.read_bytes().startswith(PNG)
    with pytest.raises(ValueError, match="results"):
        render_ecc_summary({"results": []}, tmp_path)
