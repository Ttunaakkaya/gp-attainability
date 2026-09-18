"""Bounded M2 development cases with independent geometry and GP-prefix audits."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from validate_m1 import audit_bundle, audit_run

from attain_sampling.demo.runner import run_comparison, save_comparison, scenario_config
from attain_sampling.gp.exact import ExactGP
from attain_sampling.sim.mapping import segment_min_separation


def audit_plans(run: dict[str, Any]) -> dict[str, Any]:
    config = run["config"]
    xx, yy = np.meshgrid(run["field"]["x"], run["field"]["y"])
    query = np.column_stack((xx.ravel(), yy.ravel()))
    maximum_error = 0.0
    prefixes = 0
    orders: set[tuple[int, ...]] = set()
    chosen: dict[str, int] = {}
    for plan in run.get("plans", []):
        samples = [
            s for s in run["samples"] if s["received"] and s["time_s"] <= plan["generated_at_s"]
        ]
        assert plan["received_sample_keys"] == [[s["time_s"], s["robot_id"]] for s in samples]
        assert plan["belief_observation_count"] == len(samples)
        assert plan["mission_end_s"] == config["duration_s"]
        gp = ExactGP(
            length_scale=config["length_scale"],
            signal_variance=config["signal_variance"],
            noise_variance=config["noise_std"] ** 2,
        )
        if samples:
            gp.update(
                np.array([s["actual_position"] for s in samples]),
                np.array([s["value"] for s in samples]),
            )
        for epoch, forecast in enumerate(plan["forecast"]):
            sites = np.asarray(plan["targets_by_epoch"][:epoch]).reshape(-1, 2)
            variance = gp.fantasy_variance(query, sites)
            error = max(
                abs(float(np.mean(variance)) - forecast["mean_variance"]),
                abs(float(np.max(variance)) - forecast["max_variance"]),
            )
            assert error <= 1e-8
            maximum_error = max(maximum_error, error)
            prefixes += 1
        previous = np.asarray(plan["start_positions"])
        previous_time = plan["generated_at_s"]
        for sample_time, positions in zip(
            plan["sample_times_s"], plan["targets_by_epoch"], strict=True
        ):
            current = np.asarray(positions)
            assert sample_time > previous_time
            assert sample_time <= config["duration_s"]
            assert (
                abs(
                    sample_time / config["sample_period_s"]
                    - round(sample_time / config["sample_period_s"])
                )
                <= 1e-9
            )
            assert np.max(np.linalg.norm(current - previous, axis=1)) <= (
                config["max_speed"] * (sample_time - previous_time) + 1e-7
            )
            assert segment_min_separation(previous, current) >= config["min_separation"] - 1e-7
            previous, previous_time = current, sample_time
        accepted = []
        for candidate in plan["candidates"]:
            if candidate.get("robot_order"):
                orders.add(tuple(candidate["robot_order"]))
            if candidate["status"] != "accepted":
                assert candidate["rejection_reason"]
                continue
            sites = np.asarray(candidate["targets_by_epoch"]).reshape(-1, 2)
            value = float(np.mean(gp.fantasy_variance(query, sites)))
            assert abs(value - candidate["terminal_mean_variance"]) <= 1e-8
            accepted.append(candidate)
        if accepted:
            selected = [c for c in accepted if c["selected"]]
            assert len(selected) == 1
            selected = selected[0]
            assert selected["candidate_id"] == plan["selected_candidate_id"]
            assert selected["targets_by_epoch"] == plan["targets_by_epoch"]
            assert selected["terminal_mean_variance"] <= (
                min(c["terminal_mean_variance"] for c in accepted)
                + plan["selection_variance_tolerance"]
            )
            generator = selected["generator"]
            chosen[generator] = chosen.get(generator, 0) + 1
    return {
        "plans": len(run.get("plans", [])),
        "prefixes_recomputed": prefixes,
        "maximum_prefix_variance_error": maximum_error,
        "robot_orders_searched": [list(order) for order in sorted(orders)],
        "selected_generators": chosen,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/m2-20260914/validation"))
    parser.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output.resolve() / f"batch-{stamp}-{uuid.uuid4().hex[:6]}"
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "validate_m2.py").write_bytes(Path(__file__).read_bytes())
    (destination / "validate_m1.py").write_bytes(
        Path(__file__).with_name("validate_m1.py").read_bytes()
    )
    methods = ("sweep", "greedy", "adaptive", "dp")
    jobs = [("pilot", 4, "combined", 7, 300.0, ("adaptive", "dp"))]
    if not args.pilot_only:
        jobs += [
            ("matrix", robots, scenario, seed, 90.0, methods)
            for robots, scenario, seed in product((2, 4), ("nominal", "combined"), (7, 19))
        ]
        jobs.append(("partial-tail", 2, "combined", 7, 17.0, ("adaptive", "dp")))
    report: dict[str, Any] = {
        "scope": "M2 development/control comparison, not M6 held-out evidence",
        "created_at": datetime.now(UTC).isoformat(),
        "records": [],
        "manifest_hashes_checked": 0,
        "complete": False,
    }
    started = time.perf_counter()
    for phase, robots, scenario, seed, duration, selected_methods in jobs:
        config = scenario_config(
            scenario, robots=robots, seed=seed, duration_s=duration, controller="qp"
        )
        comparison = run_comparison(config, scenario=scenario, methods=selected_methods)
        bundle = save_comparison(comparison, destination / phase)
        restored, verified = audit_bundle(bundle)
        report["manifest_hashes_checked"] += verified
        for run in restored["runs"]:
            method_dir = bundle / run["method"]
            assert (
                json.loads((method_dir / "plans.json").read_text(encoding="utf-8")) == run["plans"]
            )
            planned = pq.read_table(method_dir / "planned_samples.parquet").to_pylist()
            assert len(planned) == sum(len(p["sample_times_s"]) * robots for p in run["plans"])
            report["records"].append(
                {
                    "phase": phase,
                    "robots": robots,
                    "scenario": scenario,
                    "seed": seed,
                    "duration_s": duration,
                    "controller": "qp",
                    "method": run["method"],
                    "path": str(bundle),
                    "status": run["status"],
                    "failure": run["failure"],
                    "summary": run["summary"],
                    "audit": audit_run(run),
                    "plan_audit": audit_plans(run),
                }
            )
        (destination / "validation.json").write_text(
            json.dumps(report, allow_nan=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{phase}: {robots} robots {scenario} seed={seed}: "
            f"{comparison['runtime_s']:.3f}s compute, {comparison['status']}; {bundle}",
            flush=True,
        )
        if phase == "pilot":
            for run in restored["runs"]:
                print(
                    f"  {run['method']}: total={run['summary']['runtime_s']:.3f}s "
                    f"planning={run['summary']['planning_s']:.3f}s "
                    f"DP p95={run['summary']['dp_planning_p95_s']}",
                    flush=True,
                )
    report["complete"] = True
    report["failure_count"] = sum(r["status"] == "failed" for r in report["records"])
    report["elapsed_including_io_s"] = time.perf_counter() - started
    (destination / "validation.json").write_text(
        json.dumps(report, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Validated {len(report['records'])} runs: {destination / 'validation.json'}", flush=True)


if __name__ == "__main__":
    main()
