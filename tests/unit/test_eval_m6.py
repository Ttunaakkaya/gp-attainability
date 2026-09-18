"""M6 protocol freeze, job list, recorded-run metrics, warnings and paired statistics."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest
import yaml

from attain_sampling.demo.runner import run_comparison
from attain_sampling.eval import m6
from attain_sampling.eval.m6 import (
    Job,
    ProtocolError,
    analyze,
    enumerate_jobs,
    hold_continued_forecast,
    job_config,
    load_protocol,
    one_step_forecast_errors,
    paired_metric,
    paired_statistics,
    protocol_digest,
    run_metrics,
    target_table,
    warning_series,
    warning_summary,
)

STATS = {"resamples": 2000, "seed": 3, "level": 0.95, "tie_tolerance": 1e-9}


@pytest.fixture(scope="module")
def protocol():
    return load_protocol()


def _unfrozen(tmp_path, protocol, edit):
    text = m6.PROTOCOL_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    edit(data)
    path = tmp_path / "protocol.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_the_frozen_protocol_loads_and_its_hash_ignores_line_endings(protocol):
    text = m6.PROTOCOL_PATH.read_text(encoding="utf-8")
    assert protocol["sha256"] == m6.FROZEN_PROTOCOL_SHA256
    assert protocol_digest(text.replace("\n", "\r\n")) == protocol_digest(text)
    assert protocol["target"]["value"] == protocol["settings"]["target_mean_variance"]


def test_a_changed_protocol_is_refused(tmp_path, protocol):
    path = tmp_path / "protocol.yaml"
    path.write_text(
        m6.PROTOCOL_PATH.read_text(encoding="utf-8").replace("seed_count: 40", "seed_count: 41"),
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError, match="differs from the frozen protocol"):
        load_protocol(path)
    assert load_protocol(path, require_frozen=False)["tasks"]["seed_count"] == 41


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["tasks"].update(seed_start=7), "overlap development seeds"),
        (lambda d: d["blocks"].pop("sogp"), "blocks must be exactly"),
        (lambda d: d["blocks"]["main"].update(methods=["dp", "oracle"]), "unknown or no methods"),
        (lambda d: d["blocks"]["mismatch"]["variants"]["x"].update(noise_std=1.0), "unsupported"),
        (
            lambda d: d["blocks"]["main"]["scenarios"].update(extra={"base": "storm"}),
            "unknown base",
        ),
        (lambda d: d["target"].update(value=0.05), "must agree"),
        (lambda d: d["tasks"].update(seed_count=0), "at least one task"),
        (lambda d: d["blocks"]["ablation"]["scenario"].pop("name"), "one named scenario"),
    ],
)
def test_malformed_protocols_are_rejected(tmp_path, protocol, edit, message):
    def apply(data):
        if "mismatch" in data["blocks"]:
            data["blocks"]["mismatch"]["variants"]["x"] = {}
        edit(data)

    path = _unfrozen(tmp_path, protocol, apply)
    with pytest.raises(ProtocolError, match=message):
        load_protocol(path, require_frozen=False)


def test_the_job_list_covers_every_block_and_task_once(protocol):
    jobs = enumerate_jobs(protocol)
    assert len(jobs) == 400
    assert len({job.label for job in jobs}) == 400
    seeds = {job.seed for job in jobs}
    assert seeds == set(range(9001, 9041))
    assert not seeds & set(protocol["tasks"]["development_seeds"])
    main = [job for job in jobs if job.block == "main"]
    assert {job.scenario for job in main} == {
        "nominal",
        "dropout",
        "drift",
        "combined",
        "short_budget",
    }
    assert all(job.methods == ("sweep", "greedy", "adaptive", "dp", "p") for job in main)


def test_job_configs_apply_exactly_the_declared_changes(protocol):
    jobs = {
        (job.block, job.variant, job.scenario, job.seed): job for job in enumerate_jobs(protocol)
    }
    base = job_config(jobs[("main", "default", "combined", 9001)], protocol)
    assert (base.robot_count, base.duration_s, base.controller) == (4, 90.0, "qp")
    assert (base.dropout_prob, base.drift_strength) == (0.30, 0.35)
    assert base.target_mean_variance == 0.0474
    short = job_config(jobs[("main", "default", "short_budget", 9001)], protocol)
    assert short == replace(base, duration_s=45.0)
    assert job_config(jobs[("ablation", "p_no_rollout", "combined", 9001)], protocol) == replace(
        base, p_controller_rollout=False
    )
    assert job_config(jobs[("sogp", "sogp_32", "combined", 9001)], protocol) == replace(
        base, gp_backend="sogp", sogp_max_basis=32
    )
    mismatch = job_config(jobs[("mismatch", "length_scale_16", "nominal", 9001)], protocol)
    nominal = job_config(jobs[("main", "default", "nominal", 9001)], protocol)
    assert mismatch == replace(nominal, length_scale=16.0)


def test_paired_statistics_counts_and_brackets_the_mean():
    result = paired_statistics([-0.2, -0.1, 0.0, 0.3], **STATS)
    assert (result["negative"], result["ties"], result["positive"]) == (2, 1, 1)
    assert result["mean"] == pytest.approx(0.0)
    assert result["median"] == pytest.approx(-0.05)
    assert result["ci_low"] <= result["mean"] <= result["ci_high"]
    assert paired_statistics([-0.2, -0.1, 0.0, 0.3], **STATS) == result
    constant = paired_statistics([0.5] * 5, **STATS)
    assert constant["ci_low"] == constant["ci_high"] == pytest.approx(0.5)
    empty = paired_statistics([], **STATS)
    assert empty["n"] == 0 and empty["mean"] is None


@pytest.mark.parametrize(
    ("values", "overrides"),
    [([float("nan")], {}), ([[1.0]], {}), ([1.0], {"level": 1.0}), ([1.0], {"resamples": 0})],
)
def test_paired_statistics_rejects_invalid_input(values, overrides):
    with pytest.raises(ValueError):
        paired_statistics(values, **{**STATS, **overrides})


@pytest.fixture(scope="module")
def short_comparison(protocol):
    """A real 10 s combined task on a development seed: two sampling decisions."""
    job = Job("main", "default", "combined", "combined", 7, ("sweep", "adaptive", "dp", "p"))
    config = replace(job_config(job, protocol), duration_s=10.0)
    return run_comparison(config, scenario="combined", methods=job.methods)


def test_run_metrics_follow_the_recorded_run(short_comparison):
    run = next(run for run in short_comparison["runs"] if run["method"] == "dp")
    summary = run["summary"]
    reached = run_metrics(run, target=10.0)
    missed = run_metrics(run, target=1e-6)
    assert reached["rmse"] == summary["rmse"]
    assert reached["target_reached"] and not missed["target_reached"]
    assert reached["first_reach_time_s"] == 0.0
    assert missed["first_reach_time_s"] is None
    assert reached["plans_generated"] == 2
    errors = one_step_forecast_errors(run)
    assert len(errors) == 2
    assert reached["one_step_forecast_error_mean"] == pytest.approx(sum(errors) / 2)


def test_open_loop_baselines_report_no_one_step_error(short_comparison):
    sweep = next(run for run in short_comparison["runs"] if run["method"] == "sweep")
    assert one_step_forecast_errors(sweep) == []
    assert run_metrics(sweep, 0.0474)["one_step_forecast_error_mean"] is None


def test_a_failed_run_never_reaches_the_target(short_comparison):
    run = copy.deepcopy(short_comparison["runs"][0])
    run["status"] = "failed"
    run["failure"] = {"last_executed_time_s": 5.0}
    metrics = run_metrics(run, target=10.0)
    assert metrics["status"] == "failed"
    assert not metrics["target_reached"]
    assert metrics["failure_time_s"] == 5.0


@pytest.mark.parametrize("method", ["dp", "p"])
def test_warnings_use_one_decision_per_epoch_and_reproduce_p(short_comparison, method):
    run = next(run for run in short_comparison["runs"] if run["method"] == method)
    rows = warning_series(run, target=0.0474)
    assert [row["time_s"] for row in rows] == [0.0, 5.0]
    assert [row["remaining_sample_epochs"] for row in rows] == [2, 1]
    for row in rows:
        assert row["warning"] == (row["forecast_best"] > 0.0474)
        assert row["forecast_best"] <= row["forecast_selected"] + 1e-12
    assert all(not row["warning"] for row in warning_series(run, target=10.0))


def test_a_tampered_p_forecast_is_detected(short_comparison):
    run = copy.deepcopy(next(run for run in short_comparison["runs"] if run["method"] == "p"))
    run["plans"][0]["target_risk"]["selected_mission_end_mean_variance"] += 1e-3
    with pytest.raises(RuntimeError, match="not reproduced"):
        warning_series(run, target=0.0474)


def test_warnings_and_hold_forecasts_are_limited_to_their_scope(short_comparison):
    sweep = next(run for run in short_comparison["runs"] if run["method"] == "sweep")
    with pytest.raises(ValueError, match="planning methods"):
        warning_series(sweep, 0.0474)
    dp = copy.deepcopy(next(run for run in short_comparison["runs"] if run["method"] == "dp"))
    dp["config"]["gp_backend"] = "sogp"
    with pytest.raises(ValueError, match="exact-GP"):
        hold_continued_forecast(dp, dp["plans"][0])


def _warned(flags, reached):
    return {
        "status": "completed",
        "target_reached": reached,
        "warnings": [
            {"time_s": 5.0 * i, "remaining_sample_epochs": len(flags) - i, "warning": flag}
            for i, flag in enumerate(flags)
        ],
    }


def test_warning_summary_scores_each_epoch_against_the_outcome():
    runs = [
        _warned([True, True, True], reached=False),
        _warned([True, False, True], reached=False),
        _warned([True, True, False], reached=True),
        _warned([False, True, True], reached=True),
        {"status": "failed", "target_reached": False, "warnings": []},
    ]
    summary = warning_summary(runs)
    assert (summary["tasks"], summary["missed"], summary["reached"]) == (4, 2, 2)
    first = summary["per_epoch"][0]
    assert (first["tp"], first["fp"], first["fn"], first["tn"]) == (2, 1, 0, 1)
    assert first["recall"] == 1.0 and first["false_alarm_rate"] == 0.5
    assert summary["first_warning_epoch"] == [0, 0, 0, 1]
    assert summary["stable_correct_epoch"] == {"missed": [0, 2], "reached": [2, None]}
    assert summary["never_stable"] == {"missed": 0, "reached": 1}
    assert warning_summary([]) == {"tasks": 0}
    with pytest.raises(ValueError, match="same number"):
        warning_summary([_warned([True], False), _warned([True, True], False)])


def test_paired_metric_excludes_and_reports_failed_pairs():
    done = {"status": "completed", "rmse": 1.0}
    failed = {"status": "failed", "rmse": 0.0}
    result = paired_metric(
        [done, failed, {"status": "completed", "rmse": 3.0}],
        [{"status": "completed", "rmse": 2.0}, done, {"status": "completed", "rmse": 1.0}],
        "rmse",
        STATS,
    )
    assert result["n"] == 2 and result["excluded_failed_pairs"] == 1
    assert result["mean"] == pytest.approx(0.5)
    with pytest.raises(ValueError, match="same tasks"):
        paired_metric([done], [], "rmse", STATS)


def test_target_table_counts_paired_outcomes():
    rows = [{"target_reached": value} for value in (True, True, False, False)]
    other = [{"target_reached": value} for value in (True, False, True, False)]
    assert target_table(rows, other) == {"both": 1, "left_only": 1, "right_only": 1, "neither": 1}


def _metrics(rmse, status="completed"):
    keys = {name: 0.0 for name in m6.DESCRIBE_METRICS}
    return {
        **keys,
        "status": status,
        "rmse": rmse,
        "mean_variance": rmse / 10,
        "max_variance": rmse,
        "target_reached": rmse < 0.15,
        "first_reach_time_s": 80.0 if rmse < 0.15 else None,
        "min_separation": 3.0,
        "qp_failures": 0,
        "planning_failures": 0,
        "one_step_forecast_error_mean": None,
    }


def test_analyze_runs_the_declared_comparisons_on_synthetic_records(protocol):
    small = copy.deepcopy(protocol)
    small["tasks"]["seed_override"] = [7, 19]
    records = []
    for job in enumerate_jobs(small):
        runs = {}
        for method in job.methods:
            rmse = {"sweep": 0.3, "greedy": 0.25, "adaptive": 0.2, "dp": 0.16}.get(method, 0.14)
            if job.block == "ablation" and job.variant == "p_no_rollout":
                rmse = 0.14
            status = (
                "failed"
                if (
                    job.seed == 19
                    and method == "p"
                    and job.block == "main"
                    and job.scenario == "drift"
                )
                else "completed"
            )
            runs[method] = _metrics(rmse + 0.001 * (job.seed == 19), status)
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
    result = analyze(records, small)
    primary = result["main"]["combined"]["primary"]
    assert primary["n"] == 2 and primary["mean"] == pytest.approx(-0.02)
    assert primary["negative"] == 2
    assert result["main"]["drift"]["primary"]["excluded_failed_pairs"] == 1
    assert result["main"]["drift"]["methods"]["p"]["failed"] == 1
    assert result["main"]["combined"]["target_p_vs_dp"]["left_only"] == 2
    assert result["ablation"]["p_no_rollout"]["identical_to_full_p"] == 2
    assert result["sogp"]["sogp_32"]["minus_exact"]["p"]["rmse"]["mean"] == pytest.approx(0.0)
    assert set(result["mismatch"]["length_scale_16"]["minus_matched"]) == set(
        small["blocks"]["mismatch"]["methods"]
    )
    warned = result["main"]["combined"]["warnings"]["dp"]["best"]
    assert warned["missed"] == 2 and warned["per_epoch"][0]["recall"] == 1.0
    with pytest.raises(ValueError, match="job list"):
        analyze([row for row in records if row["block"] != "sogp"], small)
    with pytest.raises(ValueError, match="exactly once"):
        analyze(records[1:], small)
