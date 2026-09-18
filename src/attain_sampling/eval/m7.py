"""M7 held-out USV comparison: the M6 machinery on the turn-constrained vehicle.

The protocol lives in ``configs/independent/m7_protocol.yaml`` and is frozen before
any held-out run, exactly like M6. The metrics add what the vehicle model makes
relevant: how far a robot is from its commanded cell when it samples, and how often
the certified filter had to put a robot on its loiter circle. The analysis adds the
rollout effect under two planners: the motion-primitive planner (ablation block) and
the straight-line M2 planner whose geometry is wrong for this vehicle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from attain_sampling.eval import m6
from attain_sampling.eval.m6 import (
    PAIR_METRICS,
    describe_method,
    enumerate_jobs,
    paired_metric,
    target_table,
    task_seeds,
    warning_series,
    warning_summary,
)

__all__ = [
    "BLOCKS",
    "FROZEN_PROTOCOL_SHA256",
    "PROTOCOL_PATH",
    "analyze",
    "enumerate_jobs",
    "job_config",
    "load_protocol",
    "run_metrics",
    "warning_series",
]

PROTOCOL_PATH = m6.PROTOCOL_PATH.with_name("m7_protocol.yaml")
FROZEN_PROTOCOL_SHA256 = "8a9a4d71120718a9ed7a05a368d1f65ab244f9751b6bfeab74a3c7810eba296d"
BLOCKS = ("main", "ablation", "straight_line")
USV_METRICS = ("mean_arrival_error_m", "loiter_steps", "filter_modified_steps")
job_config = m6.job_config


def load_protocol(
    path: Path = PROTOCOL_PATH,
    *,
    require_frozen: bool = True,
    frozen_sha256: str = FROZEN_PROTOCOL_SHA256,
) -> dict[str, Any]:
    """Load the M7 protocol; by default refuse anything but the frozen file."""
    protocol = m6.load_protocol(
        path,
        require_frozen=require_frozen,
        frozen_sha256=frozen_sha256,
        blocks=BLOCKS,
    )
    if protocol["tasks"].get("model") != "usv_curvature":
        raise m6.ProtocolError("the M7 protocol is defined for the usv_curvature model")
    return protocol


def run_metrics(run: Mapping[str, Any], target: float) -> dict[str, Any]:
    """M6 metrics plus arrival error and filter interventions of the executed run."""
    metrics = m6.run_metrics(run, target)
    executed = [event for event in run["controls"] if event.get("phase") == "execution"]
    arrival = run["summary"].get("mean_sample_position_error")
    metrics.update(
        {
            "mean_arrival_error_m": None if arrival is None else float(arrival),
            "loiter_steps": sum(any(event.get("loitering") or []) for event in executed),
            "filter_modified_steps": sum(event.get("status") == "modified" for event in executed),
        }
    )
    return metrics


def _runs(rows: Sequence[Mapping[str, Any]], method: str) -> list[Any]:
    return [row["runs"][method] for row in rows]


def _describe(rows: Sequence[Mapping[str, Any]], method: str) -> dict[str, Any]:
    summary = describe_method(rows, method)
    done = [run for run in _runs(rows, method) if run["status"] == "completed"]
    for metric in USV_METRICS:
        values = [run[metric] for run in done if run.get(metric) is not None]
        summary[metric] = (
            {"mean": float(np.mean(values)), "median": float(np.median(values))} if values else None
        )
    return summary


def _pairs(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    stats: Mapping[str, Any],
    metrics: Sequence[str] = (*PAIR_METRICS, "mean_arrival_error_m"),
) -> dict[str, Any]:
    return {metric: paired_metric(left, right, metric, stats) for metric in metrics}


def analyze(records: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]) -> dict[str, Any]:
    """The pre-declared M7 analysis over every job record of one batch."""
    settings = protocol["analysis"]
    stats = {
        "resamples": settings["bootstrap"]["resamples"],
        "seed": settings["bootstrap"]["seed"],
        "level": settings["bootstrap"]["level"],
        "tie_tolerance": settings["tie_tolerance"],
    }
    index: dict[tuple[str, str, str], list[Any]] = {}
    for record in records:
        index.setdefault((record["block"], record["variant"], record["scenario"]), []).append(
            record
        )
    for rows in index.values():
        rows.sort(key=lambda row: row["seed"])
    expected = {(job.block, job.variant, job.scenario) for job in enumerate_jobs(protocol)}
    if set(index) != expected:
        raise ValueError("records do not match the protocol's job list")
    seeds = task_seeds(protocol)
    for key, rows in index.items():
        if [row["seed"] for row in rows] != seeds:
            raise ValueError(f"block {key} does not cover every held-out task exactly once")
    blocks = protocol["blocks"]
    primary = settings["primary"]
    pairs = [tuple(primary["comparison"]), *(tuple(pair) for pair in settings["context_pairs"])]
    result: dict[str, Any] = {"main": {}, "ablation": {}, "straight_line": {}}

    for scenario in blocks["main"]["scenarios"]:
        rows = index[("main", "default", scenario)]
        left, right = (_runs(rows, method) for method in primary["comparison"])
        result["main"][scenario] = {
            "methods": {method: _describe(rows, method) for method in blocks["main"]["methods"]},
            "primary": paired_metric(left, right, primary["metric"], stats),
            "pairs": {f"{a}-{b}": _pairs(_runs(rows, a), _runs(rows, b), stats) for a, b in pairs},
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
            "method": _describe(rows, "p"),
            "minus_full_p": _pairs(variant_p, full_p, stats),
            "minus_dp": _pairs(variant_p, _runs(reference, "dp"), stats),
            "identical_to_full_p": sum(
                a["status"] == "completed"
                and b["status"] == "completed"
                and all(a[key] == b[key] for key in ("rmse", "mean_variance", "path_length"))
                for a, b in zip(variant_p, full_p, strict=True)
            ),
        }

    name = blocks["straight_line"]["scenario"]["name"]
    reference = index[("main", "default", name)]
    variants = list(blocks["straight_line"]["variants"])
    for variant in variants:
        rows = index[("straight_line", variant, name)]
        result["straight_line"][variant] = {
            "methods": {method: _describe(rows, method) for method in ("dp", "p")},
            "p-dp": _pairs(_runs(rows, "p"), _runs(rows, "dp"), stats),
            "minus_primitives": {
                method: _pairs(_runs(rows, method), _runs(reference, method), stats)
                for method in ("dp", "p")
            },
        }
    with_rollout = index[("straight_line", variants[0], name)]
    without_rollout = index[("straight_line", variants[1], name)]
    result["straight_line"]["rollout_effect"] = {
        "no_rollout_minus_rollout_p": _pairs(
            _runs(without_rollout, "p"), _runs(with_rollout, "p"), stats
        ),
        "dp_identical_across_variants": all(
            a["rmse"] == b["rmse"] and a["path_length"] == b["path_length"]
            for a, b in zip(_runs(with_rollout, "dp"), _runs(without_rollout, "dp"), strict=True)
        ),
    }
    return result
