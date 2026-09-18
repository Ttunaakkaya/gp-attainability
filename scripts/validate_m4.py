"""Bounded M4 development cases with an independent decision and budget audit.

Every recorded decision is recomputed from the raw run: the prefix and mission-end
forecasts from an independent exact GP over the *rolled-out* sample sites plus the
hold continuation, the budget from the global clock, and the retain/replace choice
from the recorded candidate values and switch margin. Recomputation confirms the
records are self-consistent; it is not evidence that P is better than B3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from validate_m1 import audit_bundle, audit_run

from attain_sampling.attainability.budget import mission_budget
from attain_sampling.demo.runner import run_comparison, save_comparison, scenario_config
from attain_sampling.gp.exact import ExactGP

FORECAST_TOLERANCE = 1e-8


def belief_at(run: dict[str, Any], moment: float) -> tuple[ExactGP, int]:
    """Rebuild the belief a decision saw, from received samples only."""
    config = run["config"]
    gp = ExactGP(
        length_scale=config["length_scale"],
        signal_variance=config["signal_variance"],
        noise_variance=config["noise_std"] ** 2,
    )
    samples = [
        sample
        for sample in run["samples"]
        if sample["received"] and sample["time_s"] <= moment + 1e-9
    ]
    if samples:
        gp.update(
            np.array([sample["actual_position"] for sample in samples]),
            np.array([sample["value"] for sample in samples]),
        )
    return gp, len(samples)


def audit_decisions(run: dict[str, Any]) -> dict[str, Any]:
    """Recompute forecasts, budgets and the retain/replace rule for one P run."""
    config = run["config"]
    xx, yy = np.meshgrid(run["field"]["x"], run["field"]["y"])
    query = np.column_stack((xx.ravel(), yy.ravel()))
    exact = config["gp_backend"] == "exact"
    worst_prefix = 0.0
    worst_mission = 0.0
    prefixes = 0
    actions: dict[str, int] = {}
    triggers: dict[str, int] = {}
    equal_budget_checks = 0
    previous_remaining: int | None = None
    for plan in run.get("plans", []):
        moment = plan["generated_at_s"]
        budget = mission_budget(
            now_s=moment,
            mission_end_s=config["duration_s"],
            sample_period_s=config["sample_period_s"],
            robot_count=config["robot_count"],
            max_speed=config["max_speed"],
        )
        assert plan["budget"]["remaining_sample_epochs"] == budget.remaining_sample_epochs
        assert plan["budget"]["elapsed_sample_epochs"] == budget.elapsed_sample_epochs
        assert plan["budget"]["remaining_time_s"] == budget.remaining_time_s
        if previous_remaining is not None:
            assert budget.remaining_sample_epochs <= previous_remaining
        previous_remaining = budget.remaining_sample_epochs

        decision = plan["decision"]
        actions[decision["action"]] = actions.get(decision["action"], 0) + 1
        triggers[decision["trigger"]] = triggers.get(decision["trigger"], 0) + 1
        accepted = [row for row in plan["candidates"] if row["status"] == "accepted"]
        assert accepted, "every decision must keep at least one executable candidate"
        # Equal remaining sensing budget is the fairness claim of the selection rule.
        for row in accepted:
            assert row["horizon_epochs"] + row["continuation_epochs"] == (
                budget.remaining_sample_epochs
            )
            assert row["scored_sample_epochs"] == budget.remaining_sample_epochs
            equal_budget_checks += 1
        best = min(row["mission_end_mean_variance"] for row in accepted)
        retained = next((row for row in accepted if row["source"] == "retained"), None)
        if retained is None:
            assert decision["action"] in {"initial", "replaced"}
        else:
            gain = retained["mission_end_mean_variance"] - best
            expected = "retained" if gain <= decision["switch_margin_variance"] else "replaced"
            assert decision["action"] == expected, (decision["action"], gain)

        if not exact:
            continue
        gp, observations = belief_at(run, moment)
        assert observations == plan["belief_observation_count"]
        sites = np.asarray(plan["predicted_sample_sites"], dtype=float)
        for epoch, forecast in enumerate(plan["forecast"]):
            prefix = sites[:epoch].reshape(-1, 2)
            variance = (
                gp.fantasy_variance(query, prefix)
                if len(prefix)
                else gp.predict(query, variance="latent").variance
            )
            error = max(
                abs(float(np.mean(variance)) - forecast["mean_variance"]),
                abs(float(np.max(variance)) - forecast["max_variance"]),
            )
            assert error <= FORECAST_TOLERANCE, error
            worst_prefix = max(worst_prefix, error)
            prefixes += 1
        selected = next(row for row in accepted if row["selected"])
        reached = sites[-1] if len(sites) else np.asarray(plan["start_positions"], dtype=float)
        held = np.repeat(reached[None], plan["mission_end_forecast"]["continuation_epochs"], axis=0)
        combined = (np.concatenate((sites, held)) if len(sites) or len(held) else sites).reshape(
            -1, 2
        )
        variance = (
            gp.fantasy_variance(query, combined)
            if len(combined)
            else gp.predict(query, variance="latent").variance
        )
        mission_error = abs(
            float(np.mean(variance)) - plan["mission_end_forecast"]["mean_variance"]
        )
        assert mission_error <= FORECAST_TOLERANCE, mission_error
        assert (
            selected["mission_end_mean_variance"] == (plan["mission_end_forecast"]["mean_variance"])
        )
        worst_mission = max(worst_mission, mission_error)
    return {
        "plans": len(run.get("plans", [])),
        "decision_actions": actions,
        "decision_triggers": triggers,
        "equal_budget_checks": equal_budget_checks,
        "independently_recomputed_prefixes": prefixes,
        "max_prefix_forecast_error": worst_prefix,
        "max_mission_end_forecast_error": worst_mission,
        "forecast_recomputation": "exact" if exact else "skipped_for_approximate_backend",
        "claim_limit": "record self-consistency only; no superiority or attainability claim",
    }


def write_json(path: Path, value: Any) -> str:
    # Bytes, not text: Windows text mode would write CRLF and break the recorded hash.
    payload = (json.dumps(value, allow_nan=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output / f"m4-{datetime.now(UTC):%Y%m%d}" / "validation"
    destination /= f"batch-{stamp}-{uuid.uuid4().hex[:6]}"
    destination.mkdir(parents=True)
    for name in ("validate_m1.py", "validate_m4.py"):
        (destination / name).write_bytes(Path(__file__).with_name(name).read_bytes())

    methods = ("sweep", "greedy", "adaptive", "dp", "p")
    # The three masterplan section 10 ablations are configuration-only variants.
    ablations: dict[str, dict[str, Any]] = {
        "full": {},
        "no-rollout": {"p_controller_rollout": False},
        "no-retain": {"p_retain_plan": False},
        "periodic-only": {"p_event_triggers": False},
    }
    jobs: list[tuple[str, int, str, int, float, tuple[str, ...], dict[str, Any]]] = [
        ("pilot", 4, "combined", 7, 90.0, methods, {})
    ]
    if not args.pilot_only:
        jobs += [
            ("matrix", robots, scenario, seed, 90.0, methods, {})
            for robots, scenario, seed in product((2, 3), ("nominal", "combined"), (7, 19))
        ]
        jobs += [
            (f"ablation-{name}", 3, "combined", 7, 90.0, ("dp", "p"), options)
            for name, options in ablations.items()
        ]
        jobs.append(("partial-tail", 2, "combined", 7, 17.0, ("dp", "p"), {}))
    report: dict[str, Any] = {
        "scope": "M4 development evidence, not M6 held-out comparison or a superiority claim",
        "created_at": datetime.now(UTC).isoformat(),
        "records": [],
        "manifest_hashes_checked": 0,
        "complete": False,
    }
    started = time.perf_counter()
    for phase, robots, scenario, seed, duration, selected, options in jobs:
        config = scenario_config(
            scenario,
            robots=robots,
            seed=seed,
            duration_s=duration,
            controller="qp",
            **options,
        )
        comparison = run_comparison(config, scenario=scenario, methods=selected)
        bundle = save_comparison(comparison, destination / phase)
        restored, verified = audit_bundle(bundle)
        report["manifest_hashes_checked"] += verified
        for run in restored["runs"]:
            method_dir = bundle / run["method"]
            events = json.loads((method_dir / "plan_events.json").read_text(encoding="utf-8"))
            assert events == run.get("plan_events", [])
            record: dict[str, Any] = {
                "phase": phase,
                "robots": robots,
                "scenario": scenario,
                "seed": seed,
                "duration_s": duration,
                "controller": "qp",
                "policy_options": options,
                "method": run["method"],
                "path": str(bundle),
                "status": run["status"],
                "failure": run["failure"],
                "summary": run["summary"],
                "audit": audit_run(run),
            }
            if run["method"] == "p":
                record["decision_audit"] = audit_decisions(run)
            report["records"].append(record)
        write_json(destination / "validation.json", report)
        print(
            f"{phase}: {robots} robots {scenario} seed={seed} {options or 'defaults'}: "
            f"{comparison['runtime_s']:.3f}s compute, {comparison['status']}; {bundle}",
            flush=True,
        )
        for run in restored["runs"]:
            if run["method"] != "p":
                continue
            summary = run["summary"]
            print(
                f"  p: total={summary['runtime_s']:.3f}s planning={summary['planning_s']:.3f}s "
                f"rollout={summary['control_rollout_s']:.3f}s "
                f"calls={summary['rollout_control_calls']} plans={summary['plans_generated']}",
                flush=True,
            )
    report["complete"] = True
    report["failure_count"] = sum(row["status"] == "failed" for row in report["records"])
    report["elapsed_including_io_s"] = time.perf_counter() - started
    digest = write_json(destination / "validation.json", report)
    print(f"Validated {len(report['records'])} runs: {destination / 'validation.json'}", flush=True)
    print(f"validation.json sha256: {digest}", flush=True)


if __name__ == "__main__":
    main()
