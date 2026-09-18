"""M5 batch validation keeps rejected controllers without abandoning later pairs."""

from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from attain_sampling.control.ecc_qp import EccQPResult
from attain_sampling.sim import ecc2025


@pytest.fixture(scope="module")
def validation_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "validate_m5.py"
    spec = importlib.util.spec_from_file_location("validate_m5_failure_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed_pair():
    e0 = {
        "status": "completed",
        "failure": None,
        "summary": {
            "path_first_360s_m": [10.0, 10.0, 10.0],
            "path_last_360s_m": [1.0, 10.0, 10.0],
            "uncovered_fraction": 0.6,
            "first_eq5_violation_epoch": 2,
            "final_J": 10.0,
            "final_mse": 3.0,
            "initial_mse": 100.0,
        },
        "epochs": [
            {"l": 0, "J": 20.0, "meets_eq5": True},
            {"l": 1, "J": 15.0, "meets_eq5": True},
            {"l": 2, "J": 10.0, "meets_eq5": False},
        ],
    }
    e1 = copy.deepcopy(e0)
    e1["summary"].update(
        path_last_360s_m=[10.0, 10.0, 10.0],
        uncovered_fraction=0.2,
        final_J=5.0,
        final_mse=1.0,
    )
    e1["epochs"][-1]["J"] = 5.0
    return e0, e1


@pytest.mark.parametrize("failed_indices", [(0,), (1,), (0, 1)])
def test_failure_before_first_sample_does_not_read_a_missing_epoch(
    validation_script, failed_indices
):
    runs = completed_pair()
    for index in failed_indices:
        runs[index]["status"] = "failed"
        runs[index]["failure"] = {"time_s": 0.0, "status": "injected rejection"}
        runs[index]["epochs"] = runs[index]["epochs"][:1]
    before = copy.deepcopy(runs)
    assert validation_script.evaluate(*runs) == dict.fromkeys(validation_script.CRITERIA, False)
    assert runs == before


def test_a_later_failure_also_invalidates_every_criterion(validation_script):
    e0, e1 = completed_pair()
    e1["status"] = "failed"
    e1["failure"] = {"time_s": 20.0, "status": "injected rejection"}
    assert validation_script.evaluate(e0, e1) == dict.fromkeys(validation_script.CRITERIA, False)


def test_completed_criteria_are_unchanged(validation_script):
    assert validation_script.evaluate(*completed_pair()) == dict.fromkeys(
        validation_script.CRITERIA, True
    )


def test_completed_run_without_a_sample_cannot_establish_initial_decay(validation_script):
    e0, e1 = completed_pair()
    e0["epochs"] = e0["epochs"][:1]
    result = validation_script.evaluate(e0, e1)
    assert result["C3_both_initially_meet_the_decay"] is False


def sampled_run(count, shift=0.0):
    truth = ecc2025.ground_truth(7, 1)
    positions = np.array([[float(index) + shift, 0.0] for index in range(count)])
    values = ecc2025._field(positions, truth) if count else []
    return {
        "config": {"field_components": 1},
        "samples": [
            {
                "l": index // 3 + 1,
                "robot": index % 3,
                "position": positions[index].tolist(),
                "value": float(values[index] + 0.1 * (index + 1)),
            }
            for index in range(count)
        ],
    }


@pytest.mark.parametrize("counts", [(0, 0), (0, 3), (3, 0), (3, 6), (6, 3), (6, 6)])
def test_innovations_compare_only_a_shared_received_prefix(validation_script, counts):
    e0, e1 = sampled_run(counts[0]), sampled_run(counts[1], shift=2.0)
    before = copy.deepcopy((e0, e1))
    assert validation_script.paired_innovations(e0, e1, 7) == pytest.approx(0.0, abs=1e-12)
    assert (e0, e1) == before


def test_empty_innovations_do_not_evaluate_the_field(validation_script, monkeypatch):
    e0, e1 = sampled_run(0), sampled_run(3)

    def unexpected_field(*args):
        pytest.fail("an empty shared prefix must not call the field evaluator")

    monkeypatch.setattr(ecc2025, "_field", unexpected_field)
    assert validation_script.paired_innovations(e0, e1, 7) == 0.0


def test_innovation_difference_in_shared_prefix_is_not_hidden(validation_script):
    e0, e1 = sampled_run(3), sampled_run(6, shift=2.0)
    e1["samples"][1]["value"] += 0.25
    assert validation_script.paired_innovations(e0, e1, 7) == pytest.approx(0.25)


def test_innovation_prefix_must_pair_the_same_epoch_and_robot(validation_script):
    e0, e1 = sampled_run(3), sampled_run(6)
    e1["samples"][1]["robot"] = 2
    with pytest.raises(ValueError, match=r"same \(l, robot\) keys"):
        validation_script.paired_innovations(e0, e1, 7)


@pytest.mark.parametrize("rejection_violation", [0.0, float("inf"), float("nan")])
def test_batch_retains_first_step_failure_audits_prefix_and_continues(
    validation_script, tmp_path, monkeypatch, rejection_violation
):
    """Real sampling/auditing and batch I/O, with a cheap deterministic QP double."""
    active = {}
    calls = []

    def solve(**kwargs):
        rejected = active["seed"] == 7 and active["controller"] == "constraint_only"
        return EccQPResult(
            success=not rejected,
            velocity=None if rejected else np.zeros(2),
            slack=None if rejected else -1.0,
            status="injected rejection" if rejected else "test accepted",
            max_violation=rejection_violation if rejected else 0.0,
            rate_satisfied_without_slack=False,
            wall_s=0.0,
        )

    def run_small(config):
        assert list(tmp_path.rglob("criteria_declared.json"))
        active.update(seed=config.seed, controller=config.controller)
        calls.append((config.seed, config.controller))
        return ecc2025.run_ecc_profile(
            replace(config, grid_count=4, field_components=3, dt=1.0, max_waypoints=1)
        )

    monkeypatch.setattr(ecc2025, "solve_robot_qp", solve)
    monkeypatch.setattr(validation_script, "run_ecc_profile", run_small)
    monkeypatch.setattr(
        validation_script,
        "CONFIGURATIONS",
        {"A_test": {"signal_variance": 1.0, "start_center": (0.0, 75.0)}},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_m5.py", "--output", str(tmp_path), "--seeds", "7,19", "--duration", "20"],
    )
    validation_script.main()

    assert calls == [
        (7, "constraint_only"),
        (7, "hierarchical"),
        (19, "constraint_only"),
        (19, "hierarchical"),
    ]
    report_path = next(tmp_path.rglob("validation.json"))
    report = json.loads(report_path.read_bytes())
    assert report["pairs_with_a_failed_run"] == {"A_test": 1}
    failed, completed = report["results"]
    assert failed["criteria"] == dict.fromkeys(validation_script.CRITERIA, False)
    assert list(failed["failed_runs"]) == ["E0"]
    assert failed["failed_runs"]["E0"]["status"] == "injected rejection"
    assert failed["audit"]["E0"] == {"max_J_recompute_error": 0.0, "epochs": 0}
    assert failed["audit"]["E1"]["epochs"] == 2
    assert failed["max_paired_innovation_gap"] == 0.0
    assert completed["seed"] == 19 and completed["failed_runs"] == {}
    assert completed["audit"]["E0"]["epochs"] == 2
    assert completed["audit"]["E1"]["epochs"] == 2
    assert completed["max_paired_innovation_gap"] <= 1e-9

    directory = report_path.parent
    manifest = json.loads((directory / "manifest.json").read_bytes())
    assert len(list((directory / "runs").glob("*.json.gz"))) == 4
    for filename, digest in manifest.items():
        path = directory / filename
        payload = (
            gzip.decompress(path.read_bytes()) if filename.endswith(".gz") else path.read_bytes()
        )
        assert hashlib.sha256(payload).hexdigest() == digest
    failed_raw = json.loads(gzip.decompress((directory / "runs" / "A_s7_e0.json.gz").read_bytes()))
    assert failed_raw["status"] == "failed"
    assert failed_raw["failure"] == failed["failed_runs"]["E0"]
    json.dumps(failed_raw, allow_nan=False)
    if np.isfinite(rejection_violation):
        assert failed_raw["failure"]["max_violation"] == rejection_violation
        assert "max_violation_note" not in failed_raw["failure"]
    else:
        assert failed_raw["failure"]["max_violation"] is None
        assert "non-finite solver diagnostic" in failed_raw["failure"]["max_violation_note"]
        assert "null does not mean zero" in failed_raw["failure"]["max_violation_note"]
    assert failed_raw["completed_time_s"] == 0.0
    assert failed_raw["samples"] == [] and len(failed_raw["epochs"]) == 1
