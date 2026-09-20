"""M8 guided showcases: four recorded comparisons for the demo and the video.

Masterplan v2 section 17 asks for four demonstrations: the system working in nominal
conditions, a plan update under measurement loss or control intervention, the USV turn
limit changing where samples land, and a case where the method does not help. Each is
one paired comparison on a **development** seed (7, 19 or 31). They illustrate
mechanisms and are never evidence: every card names the held-out result that carries
the claim.

The first three seeds are fixed here. The fourth card must show a case without a gain,
so its seed is chosen by a stated rule, not by eye: under measurement loss, among
seeds 7, 19 and 31, the one where P's final RMSE exceeds B3's by the most. The card
lists all three differences.

Every number shown on a card is computed from the saved comparison by this script.
The manifest pins each comparison by SHA-256, and the demo server refuses a file that
no longer matches.

Usage::

    python scripts/make_showcases.py            # about five minutes, four processes
    python scripts/make_showcases.py --only usv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from attain_sampling.demo.runner import run_comparison, save_comparison, scenario_config
from attain_sampling.eval.m6 import run_metrics

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "showcases"
METHODS = ("sweep", "greedy", "adaptive", "dp", "p")
CODES = {"sweep": "B0", "greedy": "B1", "adaptive": "B2", "dp": "B3", "p": "P"}
# The held-out targets of M6 (holonomic) and M7 v2 (USV), so a card's target means
# the same thing as in the reports.
HOLONOMIC_TARGET = 0.0474
USV_TARGET = 0.0774

TRIGGERS = {
    "initial": "the mission start",
    "periodic_sampling_epoch": "a scheduled sampling epoch",
    "missed_measurement": "a lost measurement",
    "execution_deviation": "a robot drifting off its reference path",
    "control_intervention": "the safety controller changing a command",
}
REASONS = {
    "no_plan_in_force": "there was no plan yet",
    "plan_retention_disabled_by_ablation": "plan retention is switched off",
    "retained_plan_shares_no_remaining_epoch": "the plan in force had no epochs left",
    "retained_plan_no_longer_executable_from_here": (
        "the plan in force was no longer executable from where the robots actually are"
    ),
    "candidate_improves_mission_forecast_beyond_switch_margin": (
        "a new candidate lowers the mission-end forecast by more than the switch margin"
    ),
    "candidate_reaches_target_while_retained_plan_misses": (
        "the chosen route is predicted to meet the fixed target "
        "while the plan in force would miss it"
    ),
    "retained_plan_within_switch_margin_of_the_best_candidate": (
        "no candidate beats the plan in force by more than the switch margin"
    ),
}

SHOWCASES: dict[str, dict[str, Any]] = {
    "nominal": {
        "title": "The loop in nominal conditions",
        "question": "How do belief, plan, controller and measurement connect?",
        "config": {"scenario": "nominal", "model": "holonomic", "controller": "qp", "seed": 7},
        "target": HOLONOMIC_TARGET,
        "focus": "dp",
        "compare": False,
        "look_for": [
            "Squares are the timed cells of the plan in force; labels are their sampling times.",
            "Every 5 s the periodic planner re-plans from the received data and actual poses.",
            "Uncertainty (layer) falls where samples land; the error map does not fall evenly.",
        ],
        "evidence": (
            "Held-out, 40 tasks (M6): in nominal conditions B3 and P are statistically "
            "tied and both beat the sweep. reports/m6_results_2026-09-17.md"
        ),
    },
    "loss": {
        "title": "A plan update after loss and drift",
        "question": "Why does P keep or replace its plan when execution goes wrong?",
        "config": {"scenario": "combined", "model": "holonomic", "controller": "qp", "seed": 19},
        "target": HOLONOMIC_TARGET,
        "focus": "p",
        "compare": True,
        "look_for": [
            "Left B3, right P, same world, same lost measurements (crosses).",
            "Under the P map: which event triggered the decision and why the plan was kept "
            "or replaced.",
            "The plan panel separates the fixed mission target from P's new forecast.",
        ],
        "evidence": (
            "Held-out, 40 tasks (M6): under loss and drift P's RMSE difference to B3 is "
            "+0.0039 [-0.0028, +0.0106]; B2 beats both. reports/m6_results_2026-09-17.md"
        ),
    },
    "usv": {
        "title": "The turn limit moves where samples land",
        "question": "What changes when the robot cannot turn on the spot?",
        "config": {
            "scenario": "drift",
            "model": "usv_curvature",
            "controller": "filter",
            "seed": 7,
        },
        "target": USV_TARGET,
        "focus": "p",
        "compare": True,
        "look_for": [
            "Plans are drawn as the arcs the boat can fly (4.44 m minimum turning radius).",
            "On the P map, hollow circles are where P's controller rollout says each "
            "robot will actually be when it samples; squares are the commanded cells.",
            "Dashed rings mark robots the safety filter holds on their private loiter circle.",
        ],
        "evidence": (
            "Held-out, 40 tasks (M7 v2): under drift P's rollout lowers the arrival error "
            "by about 2 m and the variance, but the RMSE difference to B3 is -0.0078 "
            "[-0.0157, +0.0004]. reports/m7_results_2026-09-17.md"
        ),
    },
    "no_gain": {
        "title": "Where the method does not help",
        "question": "What does P cost, and what does it fail to fix?",
        "config": {"scenario": "dropout", "model": "holonomic", "controller": "qp"},
        "seeds": (7, 19, 31),
        "target": HOLONOMIC_TARGET,
        "focus": "p",
        "compare": True,
        "look_for": [
            "Compare the final RMSE of all five methods with the planning time in the ledger.",
            "'Plan meets reality': under loss the realised variance stays above the forecast, "
            "because every forecast assumes each measurement arrives.",
            "P's rollout models the controller, not the loss, so it cannot close that gap.",
        ],
        "evidence": (
            "Held-out, 40 tasks (M6): under measurement loss B2 beats P by +0.0094 "
            "[+0.0029, +0.0159], and P's one-step forecast is optimistic by +0.017. "
            "reports/m6_results_2026-09-17.md"
        ),
    },
}


def _seeds(spec: dict[str, Any]) -> tuple[int, ...]:
    return tuple(spec.get("seeds") or (spec["config"]["seed"],))


def _config(spec: dict[str, Any], seed: int) -> Any:
    settings = spec["config"]
    return scenario_config(
        settings["scenario"],
        robots=4,
        seed=seed,
        duration_s=90.0,
        model=settings["model"],
        controller=settings["controller"],
        target_mean_variance=spec["target"],
    )


def generate(name: str, seed: int, output: str) -> str:
    """Run one showcase and save it; returns the comparison path."""
    spec = SHOWCASES[name]
    config = _config(spec, seed)
    comparison = run_comparison(config, scenario=spec["config"]["scenario"], methods=METHODS)
    destination = save_comparison(comparison, Path(output) / name)
    return str(destination / "comparison.json")


def _runs(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {run["method"]: run for run in comparison["runs"]}


def decision_sentence(plan: dict[str, Any]) -> str:
    """Plain-language account of one recorded P decision."""
    decision = plan.get("decision") or {}
    action = {"initial": "set its first plan", "replaced": "replaced its plan"}.get(
        decision.get("action", ""), "kept its plan"
    )
    trigger = TRIGGERS.get(decision.get("trigger", ""), "a recorded event")
    reason = REASONS.get(decision.get("reason", ""), "of the recorded comparison")
    time = plan["generated_at_s"]
    return f"At {time:.1f} s, {trigger} led P to check; it {action} because {reason}."


def _key_loss(runs: dict[str, dict[str, Any]]) -> tuple[float, str]:
    plans = runs["p"]["plans"]
    events = {"missed_measurement", "execution_deviation", "control_intervention"}
    chosen = next(
        (
            plan
            for plan in plans
            if plan["decision"]["action"] == "replaced" and plan["decision"]["trigger"] in events
        ),
        None,
    ) or next((plan for plan in plans if plan["decision"]["action"] == "replaced"), plans[0])
    lost = sum(
        1
        for sample in runs["p"]["samples"]
        if not sample["received"] and sample["time_s"] <= chosen["generated_at_s"] + 1e-9
    )
    return float(chosen["generated_at_s"]), (
        f"{decision_sentence(chosen)} {lost} measurement(s) had been lost by then."
    )


def _site_gaps(plan: dict[str, Any]) -> np.ndarray:
    targets = np.asarray(plan["targets_by_epoch"][0], dtype=float)
    sites = np.asarray(plan["predicted_sample_sites"][0], dtype=float)
    return np.asarray(np.linalg.norm(targets - sites, axis=1))


def _key_usv(runs: dict[str, dict[str, Any]]) -> tuple[float, str]:
    run = runs["p"]
    plans = [
        plan
        for plan in run["plans"]
        if plan.get("targets_by_epoch") and plan.get("predicted_sample_sites")
    ]
    chosen = max(plans, key=lambda plan: float(np.max(_site_gaps(plan))))
    gaps = _site_gaps(chosen)
    robot = int(np.argmax(gaps))
    start, end = float(chosen["generated_at_s"]), float(chosen["sample_times_s"][0])
    starts = np.asarray(chosen["starts"], dtype=float)
    nearest = min(
        float(np.linalg.norm(starts[robot] - starts[other]))
        for other in range(len(starts))
        if other != robot
    )
    steps = [
        event
        for event in run["controls"]
        if event["phase"] == "execution" and start - 1e-9 <= event["time_s"] < end - 1e-9
    ]
    loiter = sum(bool(event["loitering"][robot]) for event in steps)
    sample = next(
        item
        for item in run["samples"]
        if item["robot_id"] == robot and abs(item["time_s"] - end) < 1e-9
    )
    predicted = np.asarray(chosen["predicted_sample_sites"][0][robot], dtype=float)
    miss = float(np.linalg.norm(np.asarray(sample["actual_position"]) - predicted))
    trigger = TRIGGERS.get(chosen["decision"]["trigger"], "a recorded event")
    return start, (
        f"At {start:.1f} s P re-planned after {trigger}. For robot R{robot + 1} its rollout "
        f"predicts a sample {gaps[robot]:.1f} m from the commanded cell: the robot starts "
        f"{nearest:.1f} m from another one and, unable to turn on the spot, is held on its "
        f"loiter circle in {loiter} of {len(steps)} control steps. The real sample landed "
        f"{miss:.1f} m from the rollout's prediction."
    )


def facts_for(name: str, comparison: dict[str, Any]) -> tuple[float, str, list[list[str]]]:
    """Key replay time, its plain-language description and the card's numbers."""
    spec = SHOWCASES[name]
    runs = _runs(comparison)
    metrics = {method: run_metrics(run, spec["target"]) for method, run in runs.items()}
    rmse = " · ".join(f"{CODES[m]} {metrics[m]['rmse']:.4f}" for m in METHODS)
    best = min(METHODS, key=lambda m: metrics[m]["rmse"])
    facts = [
        ["Final map RMSE (lower is better)", rmse],
        ["Lowest RMSE in this run", f"{CODES[best]} (one seed; not a ranking)"],
        [
            "Planning time B3 / P",
            f"{metrics['dp']['planning_s']:.1f} s / {metrics['p']['planning_s']:.1f} s",
        ],
        [
            "Mission target (mean variance) reached",
            " · ".join(
                f"{CODES[m]} {'yes' if metrics[m]['target_reached'] else 'no'}" for m in METHODS
            )
            + f" (target {spec['target']})",
        ],
    ]
    duration = float(comparison["config"]["duration_s"])
    if name == "nominal":
        replans = sum(plan["generated_at_s"] <= 30 for plan in runs["dp"]["plans"])
        key, moment = (
            30.0,
            (
                f"By 30 s B3 has planned {replans} times from the data that actually arrived; "
                "the squares ahead are its next timed cells."
            ),
        )
    elif name == "loss":
        key, moment = _key_loss(runs)
        facts.append(
            [
                "P decisions: replaced / kept / event-triggered",
                f"{metrics['p']['decisions_replaced']} / {metrics['p']['decisions_retained']} / "
                f"{metrics['p']['event_triggered_decisions']}",
            ]
        )
    elif name == "usv":
        key, moment = _key_usv(runs)
        facts.append(
            [
                "Mean sampling distance from the commanded cell B3 / P",
                f"{runs['dp']['summary']['mean_sample_position_error']:.2f} m / "
                f"{runs['p']['summary']['mean_sample_position_error']:.2f} m",
            ]
        )
    else:
        key = duration
        errors = {m: metrics[m]["one_step_forecast_error_mean"] for m in ("adaptive", "dp", "p")}
        moment = (
            "At mission end: realised minus forecast variance, one epoch ahead, averages "
            + " · ".join(f"{CODES[m]} {errors[m]:+.4f}" for m in errors if errors[m] is not None)
            + ". Positive means the forecast was optimistic."
        )
        ratio = metrics["p"]["planning_s"] / max(metrics["dp"]["planning_s"], 1e-9)
        facts.append(["P planning time relative to B3", f"{ratio:.0f}×"])
    return key, moment, facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--only", choices=tuple(SHOWCASES), action="append")
    args = parser.parse_args()
    names = args.only or list(SHOWCASES)
    output: Path = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "showcases.json"
    previous = (
        {entry["id"]: entry for entry in json.loads(manifest_path.read_text())["showcases"]}
        if manifest_path.is_file()
        else {}
    )
    tasks = [(name, seed) for name in names for seed in _seeds(SHOWCASES[name])]
    with ProcessPoolExecutor(max_workers=len(tasks)) as pool:
        done = list(
            pool.map(
                generate,
                [name for name, _ in tasks],
                [seed for _, seed in tasks],
                [str(output)] * len(tasks),
            )
        )
    recorded: dict[str, dict[int, Path]] = {}
    for (name, seed), path_text in zip(tasks, done, strict=True):
        recorded.setdefault(name, {})[seed] = Path(path_text)
    entries = dict(previous)
    for name, by_seed in recorded.items():
        spec = SHOWCASES[name]
        comparisons = {seed: json.loads(path.read_bytes()) for seed, path in by_seed.items()}
        for seed, comparison in comparisons.items():
            if comparison.get("status") != "completed":
                raise SystemExit(f"{name}: seed {seed} did not complete; inspect {by_seed[seed]}")
        gains = {
            seed: _runs(c)["p"]["summary"]["rmse"] - _runs(c)["dp"]["summary"]["rmse"]
            for seed, c in comparisons.items()
        }
        seed = max(gains, key=lambda item: gains[item])
        path = by_seed[seed]
        data = path.read_bytes()
        comparison = comparisons[seed]
        key, moment, facts = facts_for(name, comparison)
        if len(gains) > 1:
            listed = " · ".join(f"seed {s}: {gains[s]:+.4f}" for s in sorted(gains))
            facts.append(
                [
                    "Why this seed (stated rule)",
                    f"Largest P minus B3 RMSE under loss among development seeds: {listed}",
                ]
            )
        entries[name] = {
            "id": name,
            "title": spec["title"],
            "question": spec["question"],
            "look_for": spec["look_for"],
            "evidence": spec["evidence"],
            "focus": spec["focus"],
            "compare": spec["compare"],
            "key_time_s": key,
            "key_moment": moment,
            "facts": facts,
            "config": {
                **spec["config"],
                "seed": seed,
                "robots": 4,
                "duration_s": 90.0,
                "target": spec["target"],
            },
            "comparison": path.relative_to(output).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "runtime_s": comparison["runtime_s"],
        }
        print(f"{name}: key {key:.1f} s · {moment}")
    ordered = [entries[name] for name in SHOWCASES if name in entries]
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": (
            "illustrative paired comparisons on development seeds; the held-out evidence "
            "is in reports/m6_results_2026-09-17.md and reports/m7_results_2026-09-17.md"
        ),
        "median_runtime_s": statistics.median(entry["runtime_s"] for entry in ordered),
        "showcases": ordered,
    }
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {manifest_path}")


if __name__ == "__main__":
    main()
