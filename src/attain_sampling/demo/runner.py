"""Paired independent comparisons and immutable, auditable output bundles."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from attain_sampling.attainability.policy import TRIGGERS
from attain_sampling.eval.artifacts import canonical_digest
from attain_sampling.planning.clock import remaining_sample_times
from attain_sampling.random import derive_seed_manifest, indexed_normal
from attain_sampling.sim.mapping import (
    AVAILABLE_METHODS,
    METHODS,
    PLANNING_METHODS,
    PLANNING_MODELS,
    MappingConfig,
    run_mapping,
)

SCENARIOS = {
    "nominal": {"dropout_prob": 0.0, "drift_strength": 0.0},
    "dropout": {"dropout_prob": 0.30, "drift_strength": 0.0},
    "drift": {"dropout_prob": 0.0, "drift_strength": 0.35},
    "combined": {"dropout_prob": 0.30, "drift_strength": 0.35},
}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def scenario_config(
    scenario: str = "combined",
    *,
    robots: int = 3,
    seed: int = 7,
    duration_s: float = 90.0,
    model: str = "holonomic",
    gp_backend: str = "exact",
    sogp_max_basis: int = 64,
    sogp_novelty_tolerance: float = 1e-6,
    controller: str = "filter",
    qp_alpha: float = 1.0,
    qp_polygon_sides: int = 16,
    qp_max_iter: int = 10000,
    qp_acceptance_tol: float = 1e-7,
    dp_horizon_steps: int = 4,
    dp_grid_shape: tuple[int, int] = (9, 7),
    dp_travel_weight: float = 0.01,
    p_controller_rollout: bool = True,
    p_retain_plan: bool = True,
    p_event_triggers: bool = True,
    p_deviation_trigger_m: float = 1.5,
    p_intervention_trigger_mps: float = 0.25,
    p_switch_margin: float = 0.01,
    p_max_rollout_candidates: int = 6,
    target_mean_variance: float | None = None,
) -> MappingConfig:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    return MappingConfig(
        robot_count=robots,
        seed=seed,
        duration_s=duration_s,
        model=model,
        gp_backend=gp_backend,
        sogp_max_basis=sogp_max_basis,
        sogp_novelty_tolerance=sogp_novelty_tolerance,
        controller=controller,
        qp_alpha=qp_alpha,
        qp_polygon_sides=qp_polygon_sides,
        qp_max_iter=qp_max_iter,
        qp_acceptance_tol=qp_acceptance_tol,
        dp_horizon_steps=dp_horizon_steps,
        dp_grid_shape=dp_grid_shape,
        dp_travel_weight=dp_travel_weight,
        p_controller_rollout=p_controller_rollout,
        p_retain_plan=p_retain_plan,
        p_event_triggers=p_event_triggers,
        p_deviation_trigger_m=p_deviation_trigger_m,
        p_intervention_trigger_mps=p_intervention_trigger_mps,
        p_switch_margin=p_switch_margin,
        p_max_rollout_candidates=p_max_rollout_candidates,
        target_mean_variance=target_mean_variance,
        dropout_prob=SCENARIOS[scenario]["dropout_prob"],
        drift_strength=SCENARIOS[scenario]["drift_strength"],
    )


def _validate_pairing(config: MappingConfig, runs: list[dict[str, Any]]) -> None:
    """Validate full schedules or failed prefixes against the keyed exogenous process.

    Different failure times are legitimate observations, not reasons to discard a
    policy. Missing, reordered, duplicated or altered completed observations are
    still rejected. Positions and measured values intentionally depend on policy.
    """
    sample_ticks = round(config.sample_period_s / config.dt)
    total_ticks = round(config.duration_s / config.dt)
    expected = [
        (tick * config.dt, robot, tick)
        for tick in range(0, total_ticks + 1, sample_ticks)
        for robot in range(config.robot_count)
    ]
    manifest = derive_seed_manifest(config.seed)
    for run in runs:
        if canonical_digest(run["config"]) != canonical_digest(asdict(config)):
            raise RuntimeError("policies used different simulation configurations")
        status = run.get("status", "completed")
        if status not in {"completed", "failed"}:
            raise RuntimeError("unknown mission completion status")
        samples = run["samples"]
        if len(samples) > len(expected) or (
            status == "completed" and len(samples) != len(expected)
        ):
            raise RuntimeError("policies used invalid exogenous sample schedules")
        if status == "failed" and not run.get("failure"):
            raise RuntimeError("failed mission is missing its failure evidence")
        if len(samples) % config.robot_count:
            raise RuntimeError("failed sample schedule is not a complete sensor-epoch prefix")
        summary = run["summary"]
        if (
            summary["samples_attempted"] != len(samples)
            or summary["samples_received"] != sum(sample["received"] for sample in samples)
            or summary["samples_lost"] != sum(not sample["received"] for sample in samples)
        ):
            raise RuntimeError("mission sample counts disagree with its sensor records")
        if status == "failed" and samples and samples[-1]["time_s"] > summary["completion_time_s"]:
            raise RuntimeError("failed mission contains samples after its last executed time")
        if status == "failed":
            last_time = summary["completion_time_s"]
            if (
                not math.isfinite(last_time)
                or not 0 <= last_time <= config.duration_s
                or run["motion"][-1]["time_s"] != last_time
            ):
                raise RuntimeError("failed mission has an invalid last executed time")
            # Offline sweep/greedy planning can fail before the initial sensor
            # epoch exists. Once execution starts, every elapsed epoch is required.
            preflight_failure = (
                not samples
                and last_time == 0
                and run["method"] in {"sweep", "greedy"}
                and run["failure"]["phase"] == "preview"
                and len(run["motion"]) == 1
                and not any(event["phase"] == "execution" for event in run["controls"])
            )
            elapsed_events = sum(time_s <= last_time for time_s, _, _ in expected)
            if not preflight_failure and len(samples) != elapsed_events:
                raise RuntimeError("failed mission is missing elapsed sensor epochs")
        if any(not isinstance(sample.get("assimilated"), bool) for sample in samples):
            raise RuntimeError("sensor records must identify successful belief assimilation")
        assimilated = sum(sample["assimilated"] for sample in samples)
        if (
            assimilated != summary.get("samples_assimilated")
            or assimilated != run["gp_telemetry"]["observation_count"]
            or any(sample["assimilated"] and not sample["received"] for sample in samples)
        ):
            raise RuntimeError("belief assimilation counts disagree with sensor records")
        rejected_samples = [s for s in samples if s["received"] and not s["assimilated"]]
        if rejected_samples and (
            status != "failed"
            or run["failure"]["phase"] != "gp_update"
            or any(s["time_s"] != run["failure"]["time_s"] for s in rejected_samples)
        ):
            raise RuntimeError("unassimilated received samples require an explicit update failure")
        for sample, (time_s, robot, tick) in zip(samples, expected, strict=False):
            if (sample["time_s"], sample["robot_id"]) != (time_s, robot):
                raise RuntimeError("policies used different exogenous sample event keys")
            noise = config.noise_std * indexed_normal(manifest.measurement_noise_key, robot, tick)
            coin = indexed_normal(config.seed, robot, tick, stream="dropout")
            dropout_uniform = 0.5 * (1 + math.erf(coin / math.sqrt(2)))
            if (
                sample["received"] != (dropout_uniform >= config.dropout_prob)
                or sample["noise_innovation"] != noise
                or sample["dropout_uniform"] != dropout_uniform
            ):
                raise RuntimeError("policies used different exogenous dropout/noise innovations")
    if not all(run["field"] == runs[0]["field"] for run in runs):
        raise RuntimeError("policies used different evaluation fields")
    if not all(run["initial_positions"] == runs[0]["initial_positions"] for run in runs):
        raise RuntimeError("policies used different starting positions")
    if not all(run["seed_manifest"] == runs[0]["seed_manifest"] for run in runs):
        raise RuntimeError("policies used different seed manifests")


def _validate_methods(config: MappingConfig, methods: tuple[str, ...]) -> None:
    if (
        not isinstance(methods, (tuple, list))
        or not methods
        or any(not isinstance(method, str) or method not in AVAILABLE_METHODS for method in methods)
        or len(set(methods)) != len(methods)
    ):
        raise ValueError(
            "methods must be a nonempty unique selection of sweep, greedy, adaptive, dp, p"
        )
    if any(method in PLANNING_METHODS for method in methods) and config.model not in (
        PLANNING_MODELS
    ):
        raise ValueError(
            "timed DP and M4 management support holonomic robots and the M7 curvature USV; "
            "the original turn-in-place USV has no heading-state MDP or rollout"
        )


def _validate_managed_plans(
    config: MappingConfig, run: dict[str, Any], plans: list[dict[str, Any]]
) -> None:
    """Check the M4 evidence contract: budget, decision and target-risk provenance.

    These checks confirm that the recorded decisions are self-consistent and that
    the budget only ever runs down. They do not validate that the policy is good,
    and a recorded target warning remains a statement about the candidate set.
    """
    events = run.get("plan_events", [])
    if not isinstance(events, list) or len(events) != len(plans):
        raise RuntimeError("P must record exactly one decision event per generated plan")
    previous_remaining: int | None = None
    for index, (plan, event) in enumerate(zip(plans, events, strict=True)):
        budget = plan.get("budget")
        decision = plan.get("decision")
        risk = plan.get("target_risk")
        horizon = plan.get("mission_end_forecast")
        if not isinstance(budget, dict) or not isinstance(decision, dict):
            raise RuntimeError("P plan requires a budget and a decision record")
        if not isinstance(risk, dict) or not isinstance(horizon, dict):
            raise RuntimeError("P plan requires target-risk and mission-end forecast records")
        generated = plan["generated_at_s"]
        expected_remaining = remaining_sample_times(
            generated, config.duration_s, config.sample_period_s
        )
        if budget.get("remaining_sample_epochs") != len(expected_remaining) or not math.isclose(
            budget.get("now_s", -1.0), generated, rel_tol=0, abs_tol=1e-9
        ):
            raise RuntimeError("P budget must match the global clock at its generation time")
        if not math.isclose(
            budget.get("mission_end_s", -1.0), config.duration_s, rel_tol=0, abs_tol=1e-9
        ):
            raise RuntimeError("P budget must keep the common mission deadline")
        if (
            previous_remaining is not None
            and budget["remaining_sample_epochs"] > previous_remaining
        ):
            raise RuntimeError("P remaining sample budget must never increase")
        previous_remaining = budget["remaining_sample_epochs"]
        if decision.get("action") not in {"initial", "retained", "replaced"}:
            raise RuntimeError("P decision action is not one of initial/retained/replaced")
        if (decision["action"] == "initial") != (index == 0):
            raise RuntimeError("only the first P plan may record the initial decision")
        if decision.get("trigger") not in TRIGGERS:
            raise RuntimeError("P decision trigger is not a declared trigger")
        if (decision["trigger"] == "initial") != (index == 0):
            raise RuntimeError("only the first P plan may use the initial trigger")
        selected = [
            candidate
            for candidate in plan.get("candidates", [])
            if candidate.get("selected") is True
        ]
        if len(selected) != 1 or selected[0]["candidate_id"] != plan.get("selected_candidate_id"):
            raise RuntimeError("P must select exactly one recorded candidate")
        if selected[0].get("status") != "accepted":
            raise RuntimeError("P must not select a rejected candidate")
        if decision["action"] == "retained" and selected[0].get("source") != "retained":
            raise RuntimeError("a retained decision must select the retained candidate")
        if (
            horizon.get("continuation_epochs")
            != budget["remaining_sample_epochs"] - plan["horizon_steps"]
        ):
            raise RuntimeError("P hold continuation must cover exactly the epochs beyond the plan")
        if config.p_controller_rollout:
            for candidate in plan.get("candidates", []):
                if candidate.get("horizon_epochs") and candidate.get("rollout") is None:
                    raise RuntimeError("P candidate rollout evidence is missing")
        if risk.get("target_mean_variance") != config.target_mean_variance:
            raise RuntimeError("P target risk must report the configured mission target")
        if event.get("plan_id") != plan["plan_id"] or not math.isclose(
            event.get("time_s", -1.0), generated, rel_tol=0, abs_tol=1e-9
        ):
            raise RuntimeError("P decision events must align with their plans")
        # The explicit skipped count marks the corrected telemetry contract. Older
        # immutable bundles predate it and must remain readable without rewriting.
        if "candidates_not_evaluated" in decision:
            counts = {
                status: sum(row.get("status") == status for row in plan["candidates"])
                for status in ("accepted", "rejected", "not_evaluated")
            }
            expected_counts = {
                "candidates_evaluated": counts["accepted"] + counts["rejected"],
                "candidates_rejected": counts["rejected"],
                "candidates_not_evaluated": counts["not_evaluated"],
            }
            if sum(counts.values()) != len(plan["candidates"]) or any(
                type(decision.get(name)) is not int or decision[name] != expected
                for name, expected in expected_counts.items()
            ):
                raise RuntimeError("P candidate counters must match the recorded statuses")


def _validate_plans(config: MappingConfig, run: dict[str, Any]) -> None:
    """Check timed-plan evidence and references without claiming motion attainability."""
    plans = run.get("plans", [])
    if not isinstance(plans, list) or (run["method"] not in PLANNING_METHODS and plans):
        raise RuntimeError("invalid timed plan list for selected method")
    by_id: dict[str, dict[str, Any]] = {}
    previous_version = -1
    previous_generated = -1.0

    def finite(value: Any) -> bool:
        return (
            not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        )

    for plan in plans:
        identifier = plan.get("plan_id")
        version = plan.get("plan_version")
        generated = plan.get("generated_at_s")
        deadline = plan.get("mission_end_s")
        if not isinstance(identifier, str) or not identifier or identifier in by_id:
            raise RuntimeError("timed plans require unique nonempty plan_id values")
        if isinstance(version, bool) or not isinstance(version, int) or version <= previous_version:
            raise RuntimeError("timed plans require strictly increasing integer versions")
        if (
            not finite(generated)
            or not previous_generated <= generated <= config.duration_s
            or not finite(deadline)
            or not math.isclose(deadline, config.duration_s, rel_tol=0, abs_tol=1e-9)
        ):
            raise RuntimeError("timed plans require ordered generation times and a common deadline")
        observations = plan.get("belief_observation_count")
        if isinstance(observations, bool) or not isinstance(observations, int) or observations < 0:
            raise RuntimeError("timed plan requires a nonnegative belief observation count")
        received = [
            [sample["time_s"], sample["robot_id"]]
            for sample in run["samples"]
            if sample["assimilated"] and sample["time_s"] <= generated + 1e-9
        ]
        if observations != len(received) or plan.get("received_sample_keys") != received:
            raise RuntimeError("timed plan belief must match its actual received sample prefix")
        starts = next(
            (
                state["positions"]
                for state in run["motion"]
                if math.isclose(state["time_s"], generated, rel_tol=0, abs_tol=1e-9)
            ),
            None,
        )
        if starts is None or plan.get("start_positions") != starts:
            raise RuntimeError("timed plan must start from its actual executed robot positions")
        previous_id = next(reversed(by_id), None)
        if plan.get("previous_plan_id") != previous_id:
            raise RuntimeError("timed plan previous_plan_id must link the recorded plan sequence")
        times = plan.get("sample_times_s")
        targets = plan.get("targets_by_epoch")
        forecast = plan.get("forecast")
        if (
            not isinstance(times, list)
            or not isinstance(targets, list)
            or len(times) != len(targets)
            or len(times) > config.dp_horizon_steps
            or not isinstance(forecast, list)
            or len(forecast) != len(times) + 1
        ):
            raise RuntimeError("timed plan horizon, targets and forecast lengths disagree")
        sample_ticks = round(config.sample_period_s / config.dt)
        total_ticks = round(config.duration_s / config.dt)
        future_epochs = [
            tick * config.dt
            for tick in range(0, total_ticks + 1, sample_ticks)
            if tick * config.dt > generated + 1e-9
        ][: config.dp_horizon_steps]
        # A retained P plan legitimately runs out: its remainder covers a *prefix* of
        # the epochs a fresh plan would cover, and the recorded hold continuation
        # carries the rest of the budget. Every other plan must fill the horizon, so
        # a short horizon can never hide silently dropped epochs.
        retained_remainder = (
            run["method"] == "p"
            and isinstance(plan.get("decision"), dict)
            and plan["decision"].get("action") == "retained"
        )
        length_ok = (
            len(times) <= len(future_epochs)
            if retained_remainder
            else (len(times) == len(future_epochs))
        )
        if not length_ok or any(
            not finite(actual) or not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
            for actual, expected in zip(times, future_epochs, strict=False)
        ):
            raise RuntimeError("timed plan sample times must follow the remaining physical clock")
        for epoch in targets:
            if not isinstance(epoch, list) or len(epoch) != config.robot_count:
                raise RuntimeError("timed plan target epoch has the wrong robot count")
            for position in epoch:
                if (
                    not isinstance(position, list)
                    or len(position) != 2
                    or any(
                        not finite(value) or not -1e-7 <= value <= extent + 1e-7
                        for value, extent in zip(position, config.domain, strict=True)
                    )
                ):
                    raise RuntimeError("timed plan target positions must be finite and in-domain")
        for prediction, expected_time in zip(forecast, [generated, *times], strict=True):
            if (
                not isinstance(prediction, dict)
                or not finite(prediction.get("time_s"))
                or not math.isclose(prediction["time_s"], expected_time, rel_tol=0, abs_tol=1e-9)
                or any(
                    not finite(prediction.get(key)) or prediction[key] < -1e-9
                    for key in ("mean_variance", "max_variance")
                )
            ):
                raise RuntimeError("timed plan forecast must align with its physical sample times")
        by_id[identifier] = plan
        previous_version, previous_generated = version, generated
    planning_method = run["method"] in PLANNING_METHODS
    if planning_method and run.get("status", "completed") == "completed" and not plans:
        raise RuntimeError("completed planning mission is missing its timed plans")
    if planning_method:
        sample_ticks = round(config.sample_period_s / config.dt)
        total_ticks = round(config.duration_s / config.dt)
        last_tick = round(run["summary"]["completion_time_s"] / config.dt)
        failed = run.get("status", "completed") == "failed"
        failed_planning = failed and run["failure"]["phase"] in {"planning", "gp_update"}
        expected_generations = [
            tick * config.dt
            for tick in range(0, total_ticks, sample_ticks)
            if not failed or (tick <= last_tick and not (failed_planning and tick == last_tick))
        ]
        generated_times = [plan["generated_at_s"] for plan in plans]
        if run["method"] == "dp":
            if len(plans) != len(expected_generations) or any(
                not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
                for actual, expected in zip(generated_times, expected_generations, strict=False)
            ):
                raise RuntimeError("DP plans must preserve every elapsed periodic generation epoch")
        else:
            # P keeps every periodic decision and may add event-triggered ones, so
            # the periodic epochs must remain an ordered subsequence, never be lost.
            pending = list(expected_generations)
            for actual in generated_times:
                if not math.isclose(actual / config.dt, round(actual / config.dt), abs_tol=1e-9):
                    raise RuntimeError("P plans must be generated on the control clock")
                if pending and math.isclose(actual, pending[0], rel_tol=0, abs_tol=1e-9):
                    pending.pop(0)
            if pending:
                raise RuntimeError("P plans must preserve every elapsed periodic decision epoch")
            _validate_managed_plans(config, run, plans)

        def active_plan(time_s: float, *, incoming: bool) -> dict[str, Any] | None:
            # Motion/control timestamps denote step endpoints; a sensor epoch
            # precedes replacement. Frames show the outgoing plan after replacement.
            return next(
                (
                    plan
                    for plan in reversed(plans)
                    if (
                        plan["generated_at_s"] < time_s - 1e-9
                        if incoming
                        else plan["generated_at_s"] <= time_s + 1e-9
                    )
                ),
                None,
            )

        executed_controls = [
            event for event in run.get("controls", []) if event["phase"] == "execution"
        ]
        if any(
            event.get("plan_id") is not None
            for event in run.get("controls", [])
            if event["phase"] == "candidate_rollout"
        ):
            raise RuntimeError("candidate rollout controls must not claim an executing plan")
        for records in (run["motion"], run["samples"], executed_controls):
            for record in records:
                plan = active_plan(record["time_s"], incoming=True)
                expected_id = plan["plan_id"] if plan is not None else None
                if record.get("plan_id") != expected_id:
                    raise RuntimeError("execution must reference its active incoming timed plan")
        for frame in run["frames"]:
            outgoing = active_plan(frame["time_s"], incoming=False)
            expected_id = outgoing["plan_id"] if outgoing is not None else None
            if frame.get("plan_id") != expected_id:
                raise RuntimeError("frame must reference its active outgoing timed plan")
            incoming = active_plan(frame["time_s"], incoming=True)
            expected_forecast = None
            if incoming is not None and any(
                math.isclose(item["time_s"], frame["time_s"], rel_tol=0, abs_tol=1e-9)
                for item in incoming["forecast"]
            ):
                expected_forecast = incoming["plan_id"]
            failed_final = failed and math.isclose(
                frame["time_s"], run["summary"]["completion_time_s"], rel_tol=0, abs_tol=1e-9
            )
            actual_forecast = frame.get("forecast_plan_id")
            if actual_forecast != expected_forecast and not (
                failed_final and actual_forecast is None
            ):
                raise RuntimeError("frame forecast must reference its active incoming timed plan")
    for records in (run["motion"], run["samples"], run["frames"], run.get("controls", [])):
        for record in records:
            for key in ("plan_id", "forecast_plan_id"):
                identifier = record.get(key)
                if identifier is None:
                    continue
                if identifier not in by_id:
                    raise RuntimeError("mission record links to an unknown timed plan_id")
                plan = by_id[identifier]
                if plan["generated_at_s"] > record["time_s"] + 1e-9:
                    raise RuntimeError("mission record links to a future timed plan")
                if key == "forecast_plan_id" and not any(
                    math.isclose(item["time_s"], record["time_s"], rel_tol=0, abs_tol=1e-9)
                    for item in plan["forecast"]
                ):
                    raise RuntimeError("frame forecast link does not match a plan forecast time")


def run_comparison(
    config: MappingConfig, *, scenario: str = "custom", methods: tuple[str, ...] = METHODS
) -> dict[str, Any]:
    """Change only policy, retaining failed missions with valid paired prefixes."""
    started = time.perf_counter()
    _validate_methods(config, methods)
    runs = [run_mapping(config, method) for method in methods]
    _validate_pairing(config, runs)
    for run in runs:
        _validate_plans(config, run)
    failure_count = sum(run.get("status") == "failed" for run in runs)
    return {
        "schema_version": 1,
        "status": "completed_with_failures" if failure_count else "completed",
        "failure_count": failure_count,
        "mode": "independent_sogp" if config.gp_backend == "sogp" else "independent_exact_gp",
        "scenario": scenario,
        "config": asdict(config),
        "config_hash": canonical_digest(asdict(config)),
        "created_at": datetime.now(UTC).isoformat(),
        "runs": runs,
        "selected_methods": list(methods),
        "runtime_s": time.perf_counter() - started,
        "claims": {
            "ecc_reproduction": False,
            "formal_safety_certificate": False,
            "field_error_guarantee": False,
            "comparison_scope": "paired synthetic finite-grid kinematic simulation",
            "failed_runs": "retained as partial trajectories; not full-horizon performance scores",
            "dp_forecast": (
                "M2 geometric timed-sample forecast; not controller-in-the-loop rollout, "
                "remaining-budget reachability certification, or M4 attainability"
            ),
            "p_forecast": (
                "M4 nominal controller rollout plus an executable hold continuation over the "
                "remaining epochs; an upper candidate for the mission-end value, not an "
                "attainability floor, a recovery certificate or an impossibility proof"
            ),
        },
    }


def _source_provenance() -> dict[str, Any]:
    hashes: dict[str, str] = {}
    for path in sorted(PACKAGE_ROOT.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".html", ".css", ".js"}:
            hashes["attain_sampling/" + path.relative_to(PACKAGE_ROOT).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    revision: str | None = None
    dirty: bool | None = None
    try:
        if not (PROJECT_ROOT / "src" / "attain_sampling").is_dir():
            raise OSError("installed wheel has no source checkout Git provenance")
        git = ["git", "-c", f"safe.directory={PROJECT_ROOT.as_posix()}"]
        head = subprocess.run(
            [*git, "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        revision = head.stdout.strip() if head.returncode == 0 else None
        status = subprocess.run(
            [*git, "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    except OSError:
        pass
    return {"git_revision": revision, "git_dirty": dirty, "source_sha256": hashes}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def _auditable_summary(run: dict[str, Any], duration_s: float) -> dict[str, Any]:
    """Keep metric keys compatible while labelling incomplete mission outcomes."""
    status = run.get("status", "completed")
    return {
        **run["summary"],
        "status": status,
        "failure": run.get("failure"),
        "requested_duration_s": duration_s,
        "metric_scope": (
            "partial_mission_at_last_executed_time"
            if status == "failed"
            else "completed_full_horizon"
        ),
    }


def save_comparison(comparison: dict[str, Any], output_root: Path) -> Path:
    """New directory per run; DONE denotes saved evidence, not mission success."""
    for run in comparison["runs"]:
        _validate_plans(MappingConfig(**comparison["config"]), run)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_name = f"{stamp}-{comparison['config_hash'][:8]}-{uuid.uuid4().hex[:6]}"
    destination = output_root.resolve() / run_name
    destination.mkdir(parents=True, exist_ok=False)
    _write_json(destination / "comparison.json", comparison)
    (destination / "config.yaml").write_text(
        yaml.safe_dump(comparison["config"], sort_keys=True), encoding="utf-8"
    )
    metadata = {
        **_source_provenance(),
        "created_at": comparison["created_at"],
        "config_hash": comparison["config_hash"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "command": sys.argv,
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "pyarrow", "matplotlib", "imageio", "osqp")
        },
        "comparison_status": comparison.get("status", "completed"),
        "failure_count": comparison.get("failure_count", 0),
        "done_marker_scope": "artifact serialization complete; inspect mission status separately",
        "controller_config": {
            key: value
            for key, value in comparison["config"].items()
            if key == "controller" or key.startswith("qp_")
        },
        "selected_methods": comparison.get(
            "selected_methods", [run["method"] for run in comparison["runs"]]
        ),
        "planner_config": {
            key: value
            for key, value in comparison["config"].items()
            if key.startswith("dp_") or key.startswith("p_") or key == "target_mean_variance"
        },
        "gp_config": {
            key: value
            for key, value in comparison["config"].items()
            if key == "gp_backend" or key.startswith("sogp_")
        },
        "gp_forecast_scopes": {
            run["method"]: run["scope"].get("forecast") for run in comparison["runs"]
        },
        "seed_manifest": comparison["runs"][0]["seed_manifest"],
        "claims": comparison["claims"],
    }
    _write_json(destination / "metadata.json", metadata)
    with zipfile.ZipFile(destination / "source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in metadata["source_sha256"]:
            path = PACKAGE_ROOT.parent / relative
            archive.write(path, relative)
        for name in ("pyproject.toml", "uv.lock"):
            path = PROJECT_ROOT / name
            if path.is_file():
                archive.write(path, name)
    _write_json(
        destination / "summary.json",
        {
            run["method"]: _auditable_summary(run, comparison["config"]["duration_s"])
            for run in comparison["runs"]
        },
    )
    for run in comparison["runs"]:
        method_dir = destination / run["method"]
        method_dir.mkdir()
        pq.write_table(pa.Table.from_pylist(run["motion"]), method_dir / "robots.parquet")
        pq.write_table(pa.Table.from_pylist(run["samples"]), method_dir / "samples.parquet")
        controls = run.get("controls", [])
        plans = run.get("plans", [])
        _write_json(method_dir / "plans.json", plans)
        _write_json(method_dir / "plan_events.json", run.get("plan_events", []))
        _write_json(method_dir / "gp_updates.json", run.get("gp_updates", []))
        _write_json(method_dir / "gp_failures.json", run.get("gp_failures", []))
        _write_json(
            method_dir / "gp_telemetry.json",
            {
                "final": run.get("gp_telemetry"),
                "frames": [
                    {"time_s": frame["time_s"], **frame["gp_telemetry"]}
                    for frame in run["frames"]
                    if "gp_telemetry" in frame
                ],
            },
        )
        planned_samples = [
            {"plan_id": plan["plan_id"], "time_s": time_s, "robot_id": robot, "position": position}
            for plan in plans
            for time_s, epoch in zip(plan["sample_times_s"], plan["targets_by_epoch"], strict=True)
            for robot, position in enumerate(epoch)
        ]
        planned_schema = pa.schema(
            [
                ("plan_id", pa.string()),
                ("time_s", pa.float64()),
                ("robot_id", pa.int64()),
                ("position", pa.list_(pa.float64(), 2)),
            ]
        )
        pq.write_table(
            pa.Table.from_pylist(planned_samples, schema=planned_schema),
            method_dir / "planned_samples.parquet",
        )
        _write_json(method_dir / "controls.json", controls)
        # Include the union of keys: failure diagnostics can extend a successful
        # event's schema, and Arrow otherwise takes column names from row zero.
        control_keys = sorted({key for event in controls for key in event})
        control_rows = [{key: event.get(key) for key in control_keys} for event in controls]
        pq.write_table(pa.Table.from_pylist(control_rows), method_dir / "controls.parquet")
        _write_json(
            method_dir / "status.json",
            {"status": run.get("status", "completed"), "failure": run.get("failure")},
        )
        metrics = [
            {key: value for key, value in frame.items() if isinstance(value, (int, float))}
            for frame in run["frames"]
        ]
        pq.write_table(pa.Table.from_pylist(metrics), method_dir / "timeseries.parquet")
        _write_json(method_dir / "seed_manifest.json", run["seed_manifest"])
    artifacts = {
        p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destination.rglob("*"))
        if p.is_file()
    }
    _write_json(destination / "artifact_manifest.json", artifacts)
    # A read-back catches truncation or an invalid/nonfinite serialized result.
    loaded = json.loads((destination / "comparison.json").read_text(encoding="utf-8"))
    if loaded["config_hash"] != canonical_digest(loaded["config"]):
        raise RuntimeError("serialized configuration hash mismatch")
    for relative, expected_hash in artifacts.items():
        if hashlib.sha256((destination / relative).read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError(f"serialized artifact hash mismatch: {relative}")
    (destination / "DONE").write_text(
        "artifact serialization complete; mission success is recorded in comparison.json\n",
        encoding="utf-8",
    )
    return destination


def latest_comparison(output_root: Path) -> Path | None:
    candidates = [
        path for path in output_root.glob("*/comparison.json") if (path.parent / "DONE").is_file()
    ]
    return max(candidates, key=lambda path: path.parent.name) if candidates else None


def benchmark(
    base: MappingConfig,
    *,
    seeds: list[int],
    scenarios: list[str],
    output_root: Path,
    methods: tuple[str, ...] = METHODS,
) -> dict[str, Any]:
    """A pilot precedes the remaining jobs; summary includes every requested job."""
    if not seeds or not scenarios or len(set(seeds)) != len(seeds):
        raise ValueError("benchmark requires unique seeds and at least one scenario")
    _validate_methods(base, methods)
    records: list[dict[str, Any]] = []
    pilot_s: float | None = None
    for scenario in scenarios:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        for seed in seeds:
            config = replace(
                base,
                seed=seed,
                dropout_prob=SCENARIOS[scenario]["dropout_prob"],
                drift_strength=SCENARIOS[scenario]["drift_strength"],
            )
            comparison = run_comparison(config, scenario=scenario, methods=methods)
            path = save_comparison(comparison, output_root)
            if pilot_s is None:
                pilot_s = float(comparison["runtime_s"])
                total = pilot_s * len(seeds) * len(scenarios)
                print(
                    f"Pilot comparison: {pilot_s:.2f}s; projected batch compute: {total:.1f}s "
                    "(excludes artifact I/O; linear estimate, not a guarantee).",
                    flush=True,
                )
            for run in comparison["runs"]:
                records.append(
                    {
                        "scenario": scenario,
                        "seed": seed,
                        "path": str(path),
                        "method": run["method"],
                        **_auditable_summary(run, config.duration_s),
                    }
                )
            print(
                f"Saved {scenario}, seed {seed}: {path.name} "
                f"({comparison['status']}; {comparison['failure_count']} failed missions)",
                flush=True,
            )
    failure_count = sum(row["status"] == "failed" for row in records)
    result = {
        "mode": "independent_development_benchmark",
        "status": "completed_with_failures" if failure_count else "completed",
        "failure_count": failure_count,
        "pilot_comparison_s": pilot_s,
        "seeds": seeds,
        "scenarios": scenarios,
        "selected_methods": list(methods),
        "records": records,
        "interpretation": (
            "Development scenarios; no held-out superiority claim. Failed missions are retained; "
            "their partial metrics must not be compared as completed full-horizon scores."
        ),
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_root / f"benchmark-{stamp}.json"
    _write_json(path, result)
    result["report_path"] = str(path)
    return result
