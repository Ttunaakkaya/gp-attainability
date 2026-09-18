"""M6 held-out comparison: frozen protocol, job list, metrics, warnings and paired statistics.

Masterplan v2 sections 10, 11 and 16. The protocol lives in
``configs/independent/m6_protocol.yaml`` and is frozen before any held-out run: its
SHA-256 is pinned here, so a changed protocol cannot silently produce "final" results.

Everything in this module reads recorded runs only. Metrics are recomputed from the
saved comparison records, never taken from a policy's own claims, and the warning
analysis compares each method's forecast with that method's own mission outcome.

What this module does not claim
-------------------------------
A paired difference on 40 synthetic tasks is evidence about this simulator, these
fields and these disturbances. It is not a statistical guarantee elsewhere. A forecast
above the target says that the evaluated plan misses it, not that every executable
route does.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from attain_sampling.attainability.budget import mission_budget
from attain_sampling.demo.runner import SCENARIOS, scenario_config
from attain_sampling.gp.exact import ExactGP
from attain_sampling.sim.mapping import AVAILABLE_METHODS, MappingConfig

__all__ = [
    "FROZEN_PROTOCOL_SHA256",
    "METHOD_CODES",
    "PROTOCOL_PATH",
    "Job",
    "ProtocolError",
    "enumerate_jobs",
    "hold_continued_forecast",
    "job_config",
    "load_protocol",
    "paired_statistics",
    "protocol_digest",
    "run_metrics",
    "task_seeds",
    "warning_series",
    "analyze",
    "describe_method",
    "paired_metric",
    "target_table",
    "warning_summary",
]

PROTOCOL_PATH = Path(__file__).resolve().parents[3] / "configs" / "independent" / "m6_protocol.yaml"
FROZEN_PROTOCOL_SHA256 = "b409016561c4116cb69a169205754ec46d047695cead9ca03f7a3449dcb80ee2"
METHOD_CODES = {"sweep": "B0", "greedy": "B1", "adaptive": "B2", "dp": "B3", "p": "P"}
BLOCKS = ("main", "ablation", "sogp", "mismatch")
FORECAST_METHODS = ("adaptive", "dp", "p")
FORECAST_TOLERANCE = 1e-8
_OVERRIDABLE = {
    "duration_s",
    "dp_motion_primitives",
    "p_controller_rollout",
    "p_retain_plan",
    "p_event_triggers",
    "gp_backend",
    "sogp_max_basis",
    "length_scale",
}


class ProtocolError(ValueError):
    """Raised when the protocol is malformed or differs from the frozen version."""


def protocol_digest(text: str) -> str:
    """SHA-256 of the protocol text with LF line endings, whatever the checkout uses."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def load_protocol(
    path: Path = PROTOCOL_PATH,
    *,
    require_frozen: bool = True,
    frozen_sha256: str = FROZEN_PROTOCOL_SHA256,
    blocks: tuple[str, ...] = BLOCKS,
) -> dict[str, Any]:
    """Load and validate a protocol; by default refuse anything but the frozen M6 file."""
    text = path.read_text(encoding="utf-8")
    digest = protocol_digest(text)
    if require_frozen and digest != frozen_sha256:
        raise ProtocolError(
            f"{path.name} differs from the frozen protocol ({digest[:12]} != "
            f"{frozen_sha256[:12]}); results from a changed protocol are "
            "development evidence and need a new task set"
        )
    protocol = yaml.safe_load(text)
    if not isinstance(protocol, dict) or protocol.get("schema_version") != 1:
        raise ProtocolError("protocol must be a schema-v1 mapping")
    tasks = protocol.get("tasks", {})
    seeds = task_seeds(protocol)
    overlap = sorted(set(seeds) & set(tasks.get("development_seeds", [])))
    for low, high in tasks.get("excluded_seed_ranges", []):
        overlap += [seed for seed in seeds if low <= seed <= high]
    if overlap:
        raise ProtocolError(f"held-out seeds overlap development seeds: {sorted(overlap)}")
    if set(protocol.get("blocks", {})) != set(blocks):
        raise ProtocolError(f"protocol blocks must be exactly {blocks}")
    for name, block in protocol["blocks"].items():
        methods = block.get("methods", [])
        if not methods or any(method not in AVAILABLE_METHODS for method in methods):
            raise ProtocolError(f"block {name} has unknown or no methods")
        scenarios = _block_scenarios(name, block)
        for scenario in scenarios.values():
            if scenario.get("base") not in SCENARIOS:
                raise ProtocolError(f"block {name} uses an unknown base scenario")
            _check_overrides(name, {k: v for k, v in scenario.items() if k != "base"})
        for overrides in block.get("variants", {}).values():
            _check_overrides(name, overrides)
    target = protocol.get("target", {}).get("value")
    if target != protocol.get("settings", {}).get("target_mean_variance"):
        raise ProtocolError("the target value and target_mean_variance setting must agree")
    return {**protocol, "sha256": digest}


def _check_overrides(block: str, overrides: Mapping[str, Any]) -> None:
    unknown = set(overrides) - _OVERRIDABLE
    if unknown:
        raise ProtocolError(f"block {block} overrides unsupported settings: {sorted(unknown)}")


def _block_scenarios(name: str, block: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if name == "main":
        return {key: dict(value) for key, value in block.get("scenarios", {}).items()}
    scenario = dict(block.get("scenario", {}))
    label = scenario.pop("name", None)
    if not label:
        raise ProtocolError(f"block {name} needs one named scenario")
    return {label: scenario}


def task_seeds(protocol: Mapping[str, Any]) -> list[int]:
    """Held-out task seeds; a development smoke batch may override them in memory only."""
    tasks = protocol["tasks"]
    if "seed_override" in tasks:
        return [int(seed) for seed in tasks["seed_override"]]
    start, count = tasks["seed_start"], tasks["seed_count"]
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (start, count)):
        raise ProtocolError("seed_start and seed_count must be integers")
    if start < 0 or count < 1:
        raise ProtocolError("seeds must be non-negative and at least one task is needed")
    return list(range(start, start + count))


@dataclass(frozen=True, slots=True)
class Job:
    """One paired comparison: every listed method on the same task."""

    block: str
    variant: str
    scenario: str
    base: str
    seed: int
    methods: tuple[str, ...]
    overrides: tuple[tuple[str, Any], ...] = field(default=())

    @property
    def label(self) -> str:
        return f"{self.block}-{self.variant}-{self.scenario}-s{self.seed}"


def enumerate_jobs(protocol: Mapping[str, Any]) -> list[Job]:
    """Every paired comparison the protocol asks for, in a fixed order."""
    jobs: list[Job] = []
    seeds = task_seeds(protocol)
    for name in protocol["blocks"]:
        block = protocol["blocks"][name]
        methods = tuple(block["methods"])
        variants = block.get("variants") or {"default": {}}
        for scenario, spec in _block_scenarios(name, block).items():
            scenario_overrides = {k: v for k, v in spec.items() if k != "base"}
            for variant, overrides in variants.items():
                merged = {**scenario_overrides, **overrides}
                for seed in seeds:
                    jobs.append(
                        Job(
                            block=name,
                            variant=variant,
                            scenario=scenario,
                            base=spec["base"],
                            seed=seed,
                            methods=methods,
                            overrides=tuple(sorted(merged.items())),
                        )
                    )
    return jobs


def job_config(job: Job, protocol: Mapping[str, Any]) -> MappingConfig:
    """The exact simulator configuration of one job."""
    tasks, settings = protocol["tasks"], protocol["settings"]
    config = scenario_config(
        job.base,
        robots=tasks["robots"],
        seed=job.seed,
        duration_s=tasks["duration_s"],
        gp_backend=tasks["gp_backend"],
        controller=tasks["controller"],
        model=tasks.get("model", "holonomic"),
        dp_horizon_steps=settings["dp_horizon_steps"],
        dp_grid_shape=tuple(settings["dp_grid_shape"]),
        dp_travel_weight=settings["dp_travel_weight"],
        p_switch_margin=settings["p_switch_margin"],
        p_deviation_trigger_m=settings["p_deviation_trigger_m"],
        p_intervention_trigger_mps=settings["p_intervention_trigger_mps"],
        p_max_rollout_candidates=settings["p_max_rollout_candidates"],
        target_mean_variance=settings["target_mean_variance"],
    )
    return replace(config, **dict(job.overrides))


def _epoch_frames(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    config = run["config"]
    period = config["sample_period_s"]
    return [
        frame
        for frame in run["frames"]
        if math.isclose(frame["time_s"] / period, round(frame["time_s"] / period), abs_tol=1e-9)
    ]


def one_step_forecast_errors(run: Mapping[str, Any]) -> list[float]:
    """Realised minus forecast mean latent variance, one sampling epoch ahead.

    Only B2, B3 and P forecast one epoch ahead from the belief they act on. B0/B1
    record an open-loop nominal forecast from the mission start instead, which is a
    different quantity, so they return no values here.
    """
    if run["method"] not in FORECAST_METHODS:
        return []
    frames = _epoch_frames(run)
    return [
        float(frame["mean_variance"]) - float(frame["planned_mean_variance"])
        for frame in frames[1:]
        if frame.get("planned_mean_variance") is not None
    ]


def run_metrics(run: Mapping[str, Any], target: float) -> dict[str, Any]:
    """Mission metrics recomputed from one recorded run."""
    summary = run["summary"]
    completed = run.get("status", "completed") == "completed"
    frames = _epoch_frames(run)
    reach = next(
        (float(frame["time_s"]) for frame in frames if frame["mean_variance"] <= target), None
    )
    errors = one_step_forecast_errors(run)
    plan_times = [float(plan["planning_wall_s"]) for plan in run.get("plans", [])]
    events = run.get("plan_events", [])
    return {
        "status": run.get("status", "completed"),
        "failure_time_s": None if completed else run["failure"]["last_executed_time_s"],
        "rmse": float(summary["rmse"]),
        "mean_variance": float(summary["mean_variance"]),
        "max_variance": float(summary["max_variance"]),
        "target_reached": bool(completed and summary["mean_variance"] <= target),
        "first_reach_time_s": reach,
        "path_length": float(summary["path_length"]),
        "samples_received": int(summary["samples_received"]),
        "samples_attempted": int(summary["samples_attempted"]),
        "runtime_s": float(summary["runtime_s"]),
        "planning_s": float(summary["planning_s"]),
        "plan_wall_median_s": float(np.median(plan_times)) if plan_times else None,
        "plan_wall_p95_s": float(np.quantile(plan_times, 0.95)) if plan_times else None,
        "gp_s": float(summary["gp_s"]),
        "control_s": float(summary["control_s"]),
        "control_rollout_s": float(summary["control_rollout_s"]),
        "min_separation": float(summary["min_separation"]),
        "max_speed_observed": float(summary["max_speed_observed"]),
        "control_interventions": int(summary["control_interventions"]),
        "qp_failures": int(summary["qp_failures"]),
        "planning_failures": int(summary["planning_failures"]),
        "gp_failures": int(summary["gp_failures"]),
        "plans_generated": int(summary["plans_generated"]),
        "decisions_replaced": sum(event["action"] == "replaced" for event in events),
        "decisions_retained": sum(event["action"] == "retained" for event in events),
        "event_triggered_decisions": sum(
            event["trigger"] in {"execution_deviation", "control_intervention"} for event in events
        ),
        "one_step_forecast_error_mean": float(np.mean(errors)) if errors else None,
        "one_step_forecast_error_abs_mean": float(np.mean(np.abs(errors))) if errors else None,
    }


def _belief(run: Mapping[str, Any], moment: float) -> ExactGP:
    config = run["config"]
    gp = ExactGP(
        length_scale=config["length_scale"],
        signal_variance=config["signal_variance"],
        noise_variance=config["noise_std"] ** 2,
    )
    received = [
        sample
        for sample in run["samples"]
        if sample["received"] and sample["time_s"] <= moment + 1e-9
    ]
    if received:
        gp.update(
            np.asarray([sample["actual_position"] for sample in received], dtype=float),
            np.asarray([sample["value"] for sample in received], dtype=float),
        )
    return gp


def hold_continued_forecast(
    run: Mapping[str, Any], plan: Mapping[str, Any], sites_key: str = "targets_by_epoch"
) -> tuple[float, int]:
    """Mission-end mean latent variance of a recorded plan held at its last sites.

    The same continuation P scores its candidates with, applied by the evaluator to a
    plan that never computed it. Exact GP only: the belief is rebuilt from the samples
    the run had received when the plan was made. Returns the forecast and the number of
    remaining sampling epochs it covers.
    """
    config = run["config"]
    if config["gp_backend"] != "exact":
        raise ValueError("hold-continued forecasts are recomputed for exact-GP runs only")
    moment = float(plan["generated_at_s"])
    gp = _belief(run, moment)
    if gp.observation_count != plan["belief_observation_count"]:
        raise RuntimeError("rebuilt belief does not match the plan's recorded belief")
    budget = mission_budget(
        now_s=moment,
        mission_end_s=config["duration_s"],
        sample_period_s=config["sample_period_s"],
        robot_count=config["robot_count"],
        max_speed=config["max_speed"],
    )
    sites = np.asarray(plan[sites_key], dtype=float).reshape(-1, config["robot_count"], 2)
    remaining = budget.remaining_sample_epochs
    if len(sites) > remaining:
        raise RuntimeError("plan covers more epochs than the mission has left")
    last = sites[-1] if len(sites) else np.asarray(plan["starts"], dtype=float)
    held = np.repeat(last[None], remaining - len(sites), axis=0)
    future = np.concatenate((sites, held)).reshape(-1, 2) if remaining else np.empty((0, 2))
    xx, yy = np.meshgrid(run["field"]["x"], run["field"]["y"])
    query = np.column_stack((xx.ravel(), yy.ravel()))
    variance = (
        gp.fantasy_variance(query, future)
        if len(future)
        else gp.predict(query, variance="latent").variance
    )
    return float(np.mean(np.maximum(variance, 0.0))), remaining


def _epoch_plans(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The one decision each method makes at every sampling epoch before the deadline."""
    config = run["config"]
    period = config["sample_period_s"]
    by_epoch: dict[int, Mapping[str, Any]] = {}
    for plan in run.get("plans", []):
        ratio = float(plan["generated_at_s"]) / period
        if not math.isclose(ratio, round(ratio), abs_tol=1e-9):
            continue
        epoch = round(ratio)
        trigger = plan.get("decision", {}).get("trigger")
        if trigger in {"execution_deviation", "control_intervention"}:
            continue
        if epoch in by_epoch:
            raise RuntimeError(f"two epoch decisions at epoch {epoch}")
        by_epoch[epoch] = plan
    return [by_epoch[key] for key in sorted(by_epoch)]


def warning_series(run: Mapping[str, Any], target: float) -> list[dict[str, Any]]:
    """Per-epoch mission-end forecasts and warnings for a B3 or P run (exact GP)."""
    method = run["method"]
    if method not in {"dp", "p"}:
        raise ValueError("warnings are defined for the planning methods dp and p")
    rows = []
    for plan in _epoch_plans(run):
        if method == "p":
            risk = plan["target_risk"]
            best = float(risk["best_candidate_mission_end_mean_variance"])
            selected = float(risk["selected_mission_end_mean_variance"])
            # P scores the sites its rollout predicts; recomputing its selected value from
            # the record is an independent check that the evaluator's continuation is P's.
            recomputed, remaining = hold_continued_forecast(run, plan, "predicted_sample_sites")
            if abs(recomputed - selected) > FORECAST_TOLERANCE:
                raise RuntimeError(f"P forecast not reproduced: {recomputed} vs {selected}")
            if remaining != plan["budget"]["remaining_sample_epochs"]:
                raise RuntimeError("P budget does not match the global clock")
        else:
            best, remaining = hold_continued_forecast(run, plan)
            selected = best
        rows.append(
            {
                "time_s": float(plan["generated_at_s"]),
                "remaining_sample_epochs": remaining,
                "forecast_best": best,
                "forecast_selected": selected,
                "warning": best > target,
                "warning_selected": selected > target,
            }
        )
    return rows


def paired_statistics(
    differences: Sequence[float],
    *,
    resamples: int,
    seed: int,
    level: float,
    tie_tolerance: float,
) -> dict[str, Any]:
    """Mean and median paired difference with a task-level percentile bootstrap."""
    values = np.asarray(differences, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("differences must be a finite one-dimensional sequence")
    if not 0 < level < 1 or resamples < 1:
        raise ValueError("level must lie in (0, 1) and resamples must be positive")
    count = len(values)
    result: dict[str, Any] = {
        "n": count,
        "negative": int(np.sum(values < -tie_tolerance)),
        "ties": int(np.sum(np.abs(values) <= tie_tolerance)),
        "positive": int(np.sum(values > tie_tolerance)),
    }
    if not count:
        return {**result, "mean": None, "median": None, "ci_low": None, "ci_high": None}
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, count, size=(resamples, count))].mean(axis=1)
    tail = (1 - level) / 2
    return {
        **result,
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "ci_low": float(np.quantile(means, tail)),
        "ci_high": float(np.quantile(means, 1 - tail)),
    }


# ---------------------------------------------------------------------------
# Analysis over per-job records
# ---------------------------------------------------------------------------
# A record is one job: {"block", "variant", "scenario", "seed", "runs": {method: {
# **run_metrics, "warnings": [...] (main-block dp/p only)}}}.

PAIR_METRICS = ("rmse", "mean_variance", "max_variance", "path_length", "planning_s", "runtime_s")
DESCRIBE_METRICS = (
    "rmse",
    "mean_variance",
    "max_variance",
    "path_length",
    "samples_received",
    "runtime_s",
    "planning_s",
    "one_step_forecast_error_mean",
    "one_step_forecast_error_abs_mean",
    "plans_generated",
    "decisions_replaced",
    "decisions_retained",
    "event_triggered_decisions",
)


def _completed(run: Mapping[str, Any] | None) -> bool:
    return run is not None and run["status"] == "completed"


def _stats(protocol: Mapping[str, Any]) -> dict[str, Any]:
    settings = protocol["analysis"]["bootstrap"]
    return {
        "resamples": settings["resamples"],
        "seed": settings["seed"],
        "level": settings["level"],
        "tie_tolerance": protocol["analysis"]["tie_tolerance"],
    }


def _index(records: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], list[Any]]:
    grouped: dict[tuple[str, str, str], list[Any]] = {}
    for record in records:
        key = (record["block"], record["variant"], record["scenario"])
        grouped.setdefault(key, []).append(record)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["seed"])
    return grouped


def describe_method(rows: Sequence[Mapping[str, Any]], method: str) -> dict[str, Any]:
    """Per-method distribution over tasks; failed runs are counted, not averaged."""
    runs = [row["runs"][method] for row in rows]
    done = [run for run in runs if _completed(run)]
    summary: dict[str, Any] = {
        "tasks": len(runs),
        "failed": len(runs) - len(done),
        "target_reached": sum(run["target_reached"] for run in done),
        "min_separation": min((run["min_separation"] for run in runs), default=None),
        "qp_failures": sum(run["qp_failures"] for run in runs),
        "planning_failures": sum(run["planning_failures"] for run in runs),
    }
    reach = [run["first_reach_time_s"] for run in done if run["target_reached"]]
    summary["first_reach_time_median_s"] = float(np.median(reach)) if reach else None
    for metric in DESCRIBE_METRICS:
        values = [run[metric] for run in done if run.get(metric) is not None]
        summary[metric] = (
            {
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "p95": float(np.quantile(values, 0.95)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }
            if values
            else None
        )
    return summary


def paired_metric(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    metric: str,
    stats: Mapping[str, Any],
) -> dict[str, Any]:
    """Left minus right on tasks where both runs completed; exclusions are reported."""
    if len(left) != len(right):
        raise ValueError("paired sequences must cover the same tasks")
    keep = [(a, b) for a, b in zip(left, right, strict=True) if _completed(a) and _completed(b)]
    differences = [float(a[metric]) - float(b[metric]) for a, b in keep]
    return {
        **paired_statistics(differences, **stats),
        "excluded_failed_pairs": len(left) - len(keep),
    }


def target_table(
    left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    """Paired fixed-target outcomes; a failed run counts as not reaching the target."""
    table = {"both": 0, "left_only": 0, "right_only": 0, "neither": 0}
    for a, b in zip(left, right, strict=True):
        if a["target_reached"] and b["target_reached"]:
            table["both"] += 1
        elif a["target_reached"]:
            table["left_only"] += 1
        elif b["target_reached"]:
            table["right_only"] += 1
        else:
            table["neither"] += 1
    return table


def warning_summary(runs: Sequence[Mapping[str, Any]], key: str = "warning") -> dict[str, Any]:
    """How well a method's per-epoch warning calls that method's own mission outcome."""
    done = [run for run in runs if _completed(run) and run.get("warnings")]
    if not done:
        return {"tasks": 0}
    epochs = len(done[0]["warnings"])
    if any(len(run["warnings"]) != epochs for run in done):
        raise ValueError("every task must have the same number of epoch decisions")
    per_epoch = []
    for epoch in range(epochs):
        counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for run in done:
            warned = bool(run["warnings"][epoch][key])
            missed = not run["target_reached"]
            if warned:
                counts["tp" if missed else "fp"] += 1
            else:
                counts["fn" if missed else "tn"] += 1
        missed_total = counts["tp"] + counts["fn"]
        reached_total = counts["fp"] + counts["tn"]
        row = done[0]["warnings"][epoch]
        per_epoch.append(
            {
                "epoch": epoch,
                "time_s": row["time_s"],
                "remaining_sample_epochs": row["remaining_sample_epochs"],
                **counts,
                "recall": counts["tp"] / missed_total if missed_total else None,
                "false_alarm_rate": counts["fp"] / reached_total if reached_total else None,
            }
        )
    stable: dict[str, list[int | None]] = {"missed": [], "reached": []}
    first_warning: list[int | None] = []
    for run in done:
        flags = [bool(item[key]) for item in run["warnings"]]
        missed = not run["target_reached"]
        first_warning.append(next((i for i, flag in enumerate(flags) if flag), None))
        # Earliest epoch from which every later warning agrees with the outcome.
        start: int | None = None
        for index in range(epochs - 1, -1, -1):
            if flags[index] != missed:
                break
            start = index
        stable["missed" if missed else "reached"].append(start)
    return {
        "tasks": len(done),
        "missed": len(stable["missed"]),
        "reached": len(stable["reached"]),
        "epochs": epochs,
        "per_epoch": per_epoch,
        "first_warning_epoch": first_warning,
        "stable_correct_epoch": stable,
        "never_stable": {
            outcome: sum(value is None for value in values) for outcome, values in stable.items()
        },
    }


def _runs(rows: Sequence[Mapping[str, Any]], method: str) -> list[Any]:
    return [row["runs"][method] for row in rows]


def _pair_block(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    metrics: Sequence[str],
    stats: Mapping[str, Any],
) -> dict[str, Any]:
    return {metric: paired_metric(left, right, metric, stats) for metric in metrics}


def analyze(records: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]) -> dict[str, Any]:
    """The pre-declared M6 analysis over every job record of one batch."""
    stats = _stats(protocol)
    index = _index(records)
    seeds = task_seeds(protocol)
    expected = {(job.block, job.variant, job.scenario) for job in enumerate_jobs(protocol)}
    if set(index) != expected:
        raise ValueError("records do not match the protocol's job list")
    for key, rows in index.items():
        if [row["seed"] for row in rows] != seeds:
            raise ValueError(f"block {key} does not cover every held-out task exactly once")
    settings = protocol["analysis"]
    primary = settings["primary"]
    pairs = [tuple(primary["comparison"]), *(tuple(pair) for pair in settings["context_pairs"])]
    blocks = protocol["blocks"]
    result: dict[str, Any] = {"main": {}, "ablation": {}, "sogp": {}, "mismatch": {}}

    for scenario in blocks["main"]["scenarios"]:
        rows = index[("main", "default", scenario)]
        left, right = (_runs(rows, method) for method in primary["comparison"])
        result["main"][scenario] = {
            "methods": {
                method: describe_method(rows, method) for method in blocks["main"]["methods"]
            },
            "primary": paired_metric(left, right, primary["metric"], stats),
            "pairs": {
                f"{a}-{b}": _pair_block(_runs(rows, a), _runs(rows, b), PAIR_METRICS, stats)
                for a, b in pairs
            },
            "target_p_vs_dp": target_table(_runs(rows, "p"), _runs(rows, "dp")),
            "warnings": {
                method: {
                    "best": warning_summary(_runs(rows, method), "warning"),
                    "selected": warning_summary(_runs(rows, method), "warning_selected"),
                }
                for method in ("dp", "p")
            },
        }

    name = blocks["ablation"]["scenario"]["name"]
    reference = index[("main", "default", name)]
    for variant in blocks["ablation"]["variants"]:
        rows = index[("ablation", variant, name)]
        variant_p, full_p = _runs(rows, "p"), _runs(reference, "p")
        result["ablation"][variant] = {
            "method": describe_method(rows, "p"),
            "minus_full_p": _pair_block(variant_p, full_p, PAIR_METRICS, stats),
            "minus_dp": _pair_block(variant_p, _runs(reference, "dp"), PAIR_METRICS, stats),
            "identical_to_full_p": sum(
                _completed(a)
                and _completed(b)
                and all(a[key] == b[key] for key in ("rmse", "mean_variance", "path_length"))
                for a, b in zip(variant_p, full_p, strict=True)
            ),
        }

    for block, label, metrics in (
        ("sogp", "minus_exact", PAIR_METRICS),
        ("mismatch", "minus_matched", ("rmse", "mean_variance", "max_variance")),
    ):
        name = blocks[block]["scenario"]["name"]
        reference = index[("main", "default", name)]
        methods = blocks[block]["methods"]
        for variant in blocks[block]["variants"]:
            rows = index[(block, variant, name)]
            result[block][variant] = {
                "methods": {method: describe_method(rows, method) for method in methods},
                "p-dp": _pair_block(_runs(rows, "p"), _runs(rows, "dp"), PAIR_METRICS, stats),
                label: {
                    method: _pair_block(
                        _runs(rows, method), _runs(reference, method), metrics, stats
                    )
                    for method in methods
                },
            }
    return result
