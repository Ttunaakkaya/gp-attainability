"""M7 protocol freeze, USV metrics and the pre-declared USV analysis."""

from __future__ import annotations

import copy

import pytest
import yaml

from attain_sampling.eval import m6, m7
from attain_sampling.eval.m6 import ProtocolError, enumerate_jobs, protocol_digest


@pytest.fixture(scope="module")
def protocol():
    return m7.load_protocol()


def test_the_frozen_m7_protocol_loads_and_is_pinned(protocol):
    text = m7.PROTOCOL_PATH.read_text(encoding="utf-8")
    assert protocol_digest(text) == m7.FROZEN_PROTOCOL_SHA256
    assert protocol["tasks"]["model"] == "usv_curvature"
    assert protocol["target"]["value"] == protocol["settings"]["target_mean_variance"]


def test_m7_tasks_are_new_and_the_job_list_is_complete(protocol):
    jobs = enumerate_jobs(protocol)
    seeds = {job.seed for job in jobs}
    assert seeds == set(range(9101, 9141))
    assert not seeds & set(range(9001, 9041))
    counts = {}
    for job in jobs:
        counts[(job.block, job.variant)] = counts.get((job.block, job.variant), 0) + 1
    assert counts == {
        ("main", "default"): 200,
        ("ablation", "p_no_rollout"): 40,
        ("ablation", "p_no_retain"): 40,
        ("ablation", "p_periodic_only"): 40,
        ("straight_line", "straight"): 40,
        ("straight_line", "straight_no_rollout"): 40,
    }
    straight = next(job for job in jobs if job.variant == "straight_no_rollout")
    config = m7.job_config(straight, protocol)
    assert config.model == "usv_curvature" and config.controller == "filter"
    assert not config.dp_motion_primitives and not config.p_controller_rollout
    assert config.target_mean_variance == 0.156


def _write(tmp_path, edit):
    data = yaml.safe_load(m7.PROTOCOL_PATH.read_text(encoding="utf-8"))
    edit(data)
    path = tmp_path / "m7.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_changed_or_malformed_m7_protocols_are_refused(tmp_path):
    with pytest.raises(ProtocolError, match="differs from the frozen protocol"):
        m7.load_protocol(_write(tmp_path, lambda d: d["tasks"].update(seed_count=39)))
    overlapping = _write(tmp_path, lambda d: d["tasks"].update(seed_start=9020))
    with pytest.raises(ProtocolError, match="overlap"):
        m7.load_protocol(overlapping, require_frozen=False)
    holonomic = _write(tmp_path, lambda d: d["tasks"].update(model="holonomic"))
    with pytest.raises(ProtocolError, match="usv_curvature"):
        m7.load_protocol(holonomic, require_frozen=False)
    m6_blocks = _write(tmp_path, lambda d: d["blocks"].pop("straight_line"))
    with pytest.raises(ProtocolError, match="blocks must be exactly"):
        m7.load_protocol(m6_blocks, require_frozen=False)


def test_the_m6_protocol_is_still_refused_as_m7():
    with pytest.raises(ProtocolError):
        m7.load_protocol(m6.PROTOCOL_PATH, require_frozen=False)


def test_usv_metrics_count_arrival_error_and_filter_interventions():
    run = {
        "method": "sweep",
        "status": "completed",
        "config": {"sample_period_s": 5.0},
        "frames": [
            {"time_s": 0.0, "mean_variance": 1.0, "planned_mean_variance": 1.0},
            {"time_s": 5.0, "mean_variance": 0.1, "planned_mean_variance": 0.1},
        ],
        "plans": [],
        "plan_events": [],
        "controls": [
            {"phase": "execution", "status": "modified", "loitering": [False, True]},
            {"phase": "execution", "status": "accepted", "loitering": [False, False]},
            {"phase": "candidate_rollout", "status": "modified", "loitering": [True, True]},
        ],
        "summary": {
            key: 0.0
            for key in (
                "rmse",
                "mean_variance",
                "max_variance",
                "path_length",
                "runtime_s",
                "planning_s",
                "gp_s",
                "control_s",
                "control_rollout_s",
                "min_separation",
                "max_speed_observed",
            )
        }
        | {
            "samples_received": 8,
            "samples_attempted": 8,
            "control_interventions": 1,
            "qp_failures": 0,
            "planning_failures": 0,
            "gp_failures": 0,
            "plans_generated": 0,
            "mean_sample_position_error": 1.25,
        },
    }
    metrics = m7.run_metrics(run, target=0.5)
    assert metrics["mean_arrival_error_m"] == 1.25
    assert metrics["loiter_steps"] == 1
    assert metrics["filter_modified_steps"] == 1
    assert metrics["target_reached"] is True


def _metrics(rmse, status="completed"):
    base = {name: 0.0 for name in m6.DESCRIBE_METRICS}
    return {
        **base,
        "status": status,
        "rmse": rmse,
        "mean_variance": rmse / 2,
        "max_variance": rmse,
        "target_reached": rmse < 0.15,
        "first_reach_time_s": 50.0 if rmse < 0.15 else None,
        "min_separation": 2.5,
        "qp_failures": 0,
        "planning_failures": 0,
        "one_step_forecast_error_mean": None,
        "mean_arrival_error_m": 1.0 + rmse,
        "loiter_steps": 3,
        "filter_modified_steps": 4,
    }


def test_the_usv_analysis_reports_rollout_effects_under_both_planners(protocol):
    small = copy.deepcopy(protocol)
    small["tasks"]["seed_override"] = [7, 19]
    records = []
    for job in enumerate_jobs(small):
        overrides = dict(job.overrides)
        runs = {}
        for method in job.methods:
            rmse = {"sweep": 0.3, "greedy": 0.25, "adaptive": 0.2, "dp": 0.16}.get(method, 0.14)
            if job.block == "straight_line" and method == "p":
                rmse = 0.18 if overrides.get("p_controller_rollout") is False else 0.15
            if job.block == "straight_line" and method == "dp":
                rmse = 0.2
            runs[method] = _metrics(rmse + 0.001 * (job.seed == 19))
            if job.block == "main" and method in {"dp", "p"}:
                runs[method]["warnings"] = [
                    {
                        "time_s": 0.0,
                        "remaining_sample_epochs": 1,
                        "warning": rmse >= 0.15,
                        "warning_selected": rmse >= 0.15,
                    }
                ]
        records.append(
            {
                "block": job.block,
                "variant": job.variant,
                "scenario": job.scenario,
                "seed": job.seed,
                "runs": runs,
            }
        )
    result = m7.analyze(records, small)
    assert result["main"]["combined"]["primary"]["mean"] == pytest.approx(-0.02)
    assert result["main"]["nominal"]["methods"]["dp"]["loiter_steps"]["mean"] == 3
    arrival = result["main"]["nominal"]["pairs"]["p-dp"]["mean_arrival_error_m"]
    assert arrival["mean"] == pytest.approx(-0.02)
    effect = result["straight_line"]["rollout_effect"]
    assert effect["no_rollout_minus_rollout_p"]["rmse"]["mean"] == pytest.approx(0.03)
    assert effect["dp_identical_across_variants"] is True
    minus = result["straight_line"]["straight"]["minus_primitives"]
    assert minus["dp"]["rmse"]["mean"] == pytest.approx(0.04)
    assert result["ablation"]["p_no_rollout"]["identical_to_full_p"] == 2
    with pytest.raises(ValueError, match="job list"):
        m7.analyze([row for row in records if row["block"] != "straight_line"], small)
