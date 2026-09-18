"""Capture immutable pre-refactor mission evidence, then compare through run_mapping.

Use the repository virtual environment. Capture refuses source differing from the
preserved baseline; check deliberately permits source changes but pins the runtime.
Neither command overwrites an existing output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import sys
import time
import zipfile
from contextlib import ExitStack
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sim import mapping

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".scratch/research-refinement/baseline/20260918T145314Z/manifest.json"


# Exact artifact paths, not a suffix filter: physical times always remain checked.
TIMING_PATHS = (
    "summary.runtime_s",
    "summary.planning_s",
    "summary.gp_s",
    "summary.control_s",
    "summary.control_preview_s",
    "summary.control_rollout_s",
    "summary.control_median_s",
    "summary.control_p95_s",
    "summary.control_max_s",
    "summary.dp_planning_s",
    "summary.dp_planning_median_s",
    "summary.dp_planning_p95_s",
    "summary.dp_failed_planning_s",
    "summary.failure_reconstruction_gp_s",
    "plans.*.planning_wall_s",
    "plans.*.posterior_covariance_wall_s",
    "plans.*.candidate_search.planning_wall_s",
    "plans.*.candidates.*.generation_wall_s",
    "plans.*.candidates.*.joint_evaluation_wall_s",
    "plans.*.candidates.*.evaluation_wall_s",
    "plans.*.candidates.*.rollout.wall_s",
    "planning_failures.*.wall_s",
    "gp_failures.*.wall_s",
) + tuple(
    f"{prefix}.{field}"
    for prefix in ("controls.*", "failure.details")
    for field in ("wall_s", "setup_s", "solve_s", "setup_wall_s", "solve_wall_s", "control_s")
)


def normalize(value: Any, path: str = "") -> Any:
    """Replace only named measured runtimes; preserve keys, nulls and all other data."""
    if path in TIMING_PATHS:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}: runtime must be a number or null")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{path}: runtime must be finite and nonnegative")
        return "<measured seconds>"
    if isinstance(value, dict):
        return {key: normalize(item, f"{path}.{key}".lstrip(".")) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item, f"{path}.*") for item in value]
    return value


def first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    """Return the first differing record/field, with strict types and no tolerances."""
    if type(expected) is not type(actual):
        return f"{path}: expected {expected!r}, got {actual!r} (type differs)"
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            return f"{path}: keys differ: expected {sorted(expected)}, got {sorted(actual)}"
        for key in sorted(expected):
            difference = first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} records, got {len(actual)}"
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference:
                return difference
    elif expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _write(path: Path, value: Any) -> None:
    path.write_text(_json(value), encoding="utf-8", newline="\n")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment() -> dict[str, Any]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "osqp", "clarabel")
        },
    }


def source_identity() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): _sha(path)
        for path in sorted((ROOT / "src").rglob("*.py"))
    }


def verify_baseline_source() -> dict[str, Any]:
    """Verify both current source and archived copies against the frozen manifest."""
    manifest = _read(BASELINE)
    archive = BASELINE.parent / manifest["archive"]
    if _sha(archive) != manifest["archive_sha256"]:
        raise ValueError("preserved archive SHA256 mismatch")
    expected = {
        row["path"]: row["sha256"]
        for row in manifest["files"]
        if row["path"].startswith("src/") and row["path"].endswith(".py")
    }
    difference = first_difference(expected, source_identity())
    if difference:
        raise ValueError(f"source differs from frozen baseline: {difference}")
    with zipfile.ZipFile(archive) as bundle:
        for path, digest in expected.items():
            if hashlib.sha256(bundle.read(path)).hexdigest() != digest:
                raise ValueError(f"preserved source differs: {path}")
    return {
        "manifest_path": str(BASELINE.relative_to(ROOT)),
        "manifest_sha256": _sha(BASELINE),
        "archive_sha256": _sha(archive),
        "source": expected,
    }


def cases() -> list[dict[str, Any]]:
    """Small development configurations, deliberately not a factorial experiment."""
    base = mapping.MappingConfig(
        robot_count=2,
        duration_s=10.0,
        grid_shape=(6, 4),
        dp_grid_shape=(4, 3),
        dp_horizon_steps=2,
        seed=7,
    )
    definitions = [
        ("sweep_filter", "sweep", {}, None),
        ("greedy_usv", "greedy", {"model": "usv", "drift_strength": 0.35}, None),
        ("adaptive_qp", "adaptive", {"controller": "qp", "dropout_prob": 0.3}, None),
        (
            "dp_fractional_tail",
            "dp",
            {
                "dt": 0.7,
                "sample_period_s": 2.1,
                "duration_s": 7.0,
                "controller": "qp",
                "drift_strength": 0.35,
            },
            None,
        ),
        ("dp_sogp_pruning", "dp", {"gp_backend": "sogp", "sogp_max_basis": 2}, None),
        ("dp_total_loss", "dp", {"dropout_prob": 1.0, "duration_s": 7.0}, None),
        (
            "p_interior",
            "p",
            {
                "controller": "qp",
                "drift_strength": 0.35,
                "p_deviation_trigger_m": 0.05,
                "p_intervention_trigger_mps": 1000.0,
                "target_mean_variance": 0.2,
            },
            None,
        ),
        (
            "p_curvature",
            "p",
            {
                "model": "usv_curvature",
                "drift_strength": 0.15,
                "target_mean_variance": 0.2,
            },
            None,
        ),
        ("preview_before_receipt", "sweep", {"controller": "qp", "qp_max_iter": 1}, None),
        ("preview_after_receipt", "adaptive", {"controller": "qp", "qp_max_iter": 1}, None),
        ("execution_rejected", "adaptive", {"controller": "qp"}, {"kind": "execution", "tick": 13}),
        ("planning_initial", "dp", {"controller": "qp"}, {"kind": "planning", "time_s": 0.0}),
        ("planning_later", "dp", {"controller": "qp"}, {"kind": "planning", "time_s": 5.0}),
        (
            "gp_batch_rejected",
            "dp",
            {"gp_backend": "sogp", "sogp_max_basis": 2},
            {"kind": "gp_batch", "committed_observations": 2},
        ),
    ]
    return [
        {
            "name": name,
            "method": method,
            "config": asdict(replace(base, **changes)),
            "trigger": trigger,
        }
        for name, method, changes, trigger in definitions
    ]


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Use existing deterministic dependency hooks; observe only the mission result."""
    config_values = dict(case["config"])
    for key in ("domain", "grid_shape", "dp_grid_shape"):
        config_values[key] = tuple(config_values[key])
    config = mapping.MappingConfig(**config_values)
    trigger = case["trigger"]
    with ExitStack() as stack:
        if trigger and trigger["kind"] == "execution":
            advance = mapping._advance

            def rejected_motion(positions, headings, targets, settings, tick, **kwargs):
                if kwargs.get("phase") == "execution" and tick == trigger["tick"]:
                    settings = replace(settings, qp_max_iter=1)
                return advance(positions, headings, targets, settings, tick, **kwargs)

            stack.enter_context(patch.object(mapping, "_advance", rejected_motion))
        elif trigger and trigger["kind"] == "planning":
            planner = mapping.plan_timed_dp

            def rejected_plan(*args, **kwargs):
                if kwargs["now_s"] == trigger["time_s"]:
                    raise FloatingPointError("reference injected covariance failure")
                return planner(*args, **kwargs)

            stack.enter_context(patch.object(mapping, "plan_timed_dp", rejected_plan))
        elif trigger and trigger["kind"] == "gp_batch":
            update = SparseOnlineGP.update

            def rejected_update(belief, x, y):
                if belief.observation_count >= trigger["committed_observations"]:
                    raise FloatingPointError("reference injected transactional GP update failure")
                return update(belief, x, y)

            stack.enter_context(patch.object(SparseOnlineGP, "update", rejected_update))
        return mapping.run_mapping(config, case["method"])


def coverage(result: dict[str, Any]) -> dict[str, Any]:
    """Record observed behavior, including evidence that a configured branch ran."""
    config = result["config"]
    periodic = config["sample_period_s"]
    summary = result["summary"]
    return {
        "method": result["method"],
        "model": config["model"],
        "controller": config["controller"],
        "gp_backend": config["gp_backend"],
        "status": result["status"],
        "failure_phase": result["failure"]["phase"] if result["failure"] else None,
        "sample_times_s": sorted({sample["time_s"] for sample in result["samples"]}),
        "received": summary["samples_received"],
        "assimilated": summary["samples_assimilated"],
        "pruned_count": result["gp_telemetry"].get("pruned_count", 0),
        "last_executed_time_s": result["motion"][-1]["time_s"],
        "interior_decisions": [
            event["time_s"]
            for event in result["plan_events"]
            if not math.isclose(event["time_s"] / periodic, round(event["time_s"] / periodic))
        ],
        "distinct_incoming_outgoing_frames": [
            frame["time_s"]
            for frame in result["frames"]
            if frame.get("forecast_plan_id") is not None
            and frame.get("plan_id") != frame["forecast_plan_id"]
        ],
        "executed_controls": sum(event["phase"] == "execution" for event in result["controls"]),
        "plans": len(result["plans"]),
    }


def assert_coverage(rows: list[dict[str, Any]]) -> None:
    observed = {row["name"]: row["coverage"] for row in rows}
    assert {row["method"] for row in observed.values()} == set(mapping.AVAILABLE_METHODS)
    assert {row["model"] for row in observed.values()} == set(mapping.MODELS)
    assert observed["dp_sogp_pruning"]["pruned_count"] > 0
    assert observed["dp_total_loss"]["received"] == 0
    assert observed["p_interior"]["interior_decisions"]
    assert observed["p_curvature"]["executed_controls"] > 0
    assert observed["p_curvature"]["plans"] > 0
    assert observed["dp_fractional_tail"]["distinct_incoming_outgoing_frames"]
    assert observed["dp_fractional_tail"]["last_executed_time_s"] == 7.0
    assert max(observed["dp_fractional_tail"]["sample_times_s"]) < 7.0
    for name in (
        "sweep_filter",
        "greedy_usv",
        "adaptive_qp",
        "dp_fractional_tail",
        "dp_sogp_pruning",
        "dp_total_loss",
        "p_interior",
        "p_curvature",
    ):
        assert observed[name]["status"] == "completed", name
    for name, phase, received, assimilated, reached in (
        ("preview_before_receipt", "preview", 0, 0, 0),
        ("preview_after_receipt", "preview", 2, 2, 0),
        ("execution_rejected", "execution", 4, 4, 6),
        ("planning_initial", "planning", 2, 2, 0),
        ("planning_later", "planning", 4, 4, 5),
        ("gp_batch_rejected", "gp_update", 4, 2, 5),
    ):
        row = observed[name]
        assert (
            row["status"],
            row["failure_phase"],
            row["received"],
            row["assimilated"],
            row["last_executed_time_s"],
        ) == ("failed", phase, received, assimilated, reached), name


def _record_cases(output: Path, definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in definitions:
        started = time.perf_counter()
        result = run_case(case)
        raw = output / f"{case['name']}.raw.json"
        normalized = output / f"{case['name']}.normalized.json"
        _write(raw, result)
        # JSON roundtrip is intentional: MappingConfig tuples serialize as lists.
        _write(normalized, normalize(_read(raw)))
        rows.append(
            {
                **case,
                "raw": raw.name,
                "raw_sha256": _sha(raw),
                "normalized": normalized.name,
                "normalized_sha256": _sha(normalized),
                "coverage": coverage(result),
                "capture_wall_s": time.perf_counter() - started,
            }
        )
        print(f"{case['name']}: {result['status']} ({rows[-1]['capture_wall_s']:.3f}s)", flush=True)
    return rows


def capture(output: Path) -> None:
    identity = verify_baseline_source()
    output.mkdir(parents=True, exist_ok=False)
    rows = _record_cases(output, cases())
    assert_coverage(rows)
    _write(
        output / "manifest.json",
        {
            "schema_version": 1,
            "created_utc": datetime.now(UTC).isoformat(),
            "baseline": identity,
            "environment": environment(),
            "timing_paths": TIMING_PATHS,
            "harness_sha256": _sha(Path(__file__)),
            "cases": rows,
        },
    )


def check(reference: Path, output: Path) -> bool:
    """Retain fresh raw evidence and report a first differing path for each case."""
    manifest = _read(reference / "manifest.json")
    if manifest["harness_sha256"] != _sha(Path(__file__)):
        raise ValueError("capture harness differs from frozen reference")
    for row in manifest["cases"]:
        for kind in ("raw", "normalized"):
            if _sha(reference / row[kind]) != row[f"{kind}_sha256"]:
                raise ValueError(f"{row['name']}: frozen {kind} hash mismatch")
        difference = first_difference(
            normalize(_read(reference / row["raw"])), _read(reference / row["normalized"])
        )
        if difference:
            raise ValueError(f"{row['name']}: normalization mismatch: {difference}")
    if manifest["timing_paths"] != list(TIMING_PATHS):
        raise ValueError("timing exclusion rules differ from frozen reference")
    difference = first_difference(manifest["environment"], environment())
    if difference:
        raise ValueError(f"runtime differs from reference: {difference}")
    output.mkdir(parents=True, exist_ok=False)
    rows = _record_cases(output, manifest["cases"])
    differences = []
    for row in rows:
        difference = first_difference(
            _read(reference / row["normalized"]), _read(output / row["normalized"])
        )
        if difference:
            differences.append({"case": row["name"], "difference": difference})
            print(f"DIFFERENCE {row['name']}: {difference}", flush=True)
    report = {
        "passed": not differences,
        "reference_manifest_sha256": _sha(reference / "manifest.json"),
        "environment": environment(),
        "source": source_identity(),
        "harness_sha256": _sha(Path(__file__)),
        "cases": rows,
        "differences": differences,
    }
    _write(output / "report.json", report)
    return not differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--output", type=Path, required=True)
    check_parser = commands.add_parser("check")
    check_parser.add_argument("--reference", type=Path, required=True)
    check_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.output)
        return 0
    return 0 if check(args.reference, args.output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
