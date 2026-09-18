"""Bounded M1 development validation; preserve every outcome and audit raw records."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
import zipfile
from datetime import UTC, datetime
from itertools import combinations, product
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from attain_sampling.demo.runner import run_comparison, save_comparison, scenario_config


def strict_json(path: Path) -> Any:
    def invalid_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON number in {path}: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


def audit_run(run: dict[str, Any]) -> dict[str, Any]:
    config, summary = run["config"], run["summary"]
    motion, controls = run["motion"], run["controls"]
    points = np.asarray([row["positions"] for row in motion])
    times = np.asarray([row["time_s"] for row in motion])
    displacement = np.diff(points, axis=0)
    lengths = np.linalg.norm(displacement, axis=2)
    dt = config["dt"]
    np.testing.assert_allclose(np.diff(times), dt, rtol=0, atol=1e-10)
    np.testing.assert_allclose(points[0], run["initial_positions"], rtol=0, atol=1e-10)
    minimum = float("inf")
    for first, second in combinations(range(config["robot_count"]), 2):
        minimum = min(minimum, float(np.linalg.norm(points[0, first] - points[0, second])))
        for before, change in zip(points[:-1], displacement, strict=True):
            relative = before[first] - before[second]
            delta = change[first] - change[second]
            squared = float(delta @ delta)
            fraction = float(np.clip(-(relative @ delta) / squared, 0, 1)) if squared else 0.0
            minimum = min(minimum, float(np.linalg.norm(relative + fraction * delta)))
    linked: list[int] = []
    for index, row in enumerate(motion[1:]):
        event_index = row["control_event_index"]
        event = controls[event_index]
        assert event["phase"] == "execution" and event["success"]
        assert event["time_s"] == row["time_s"]
        np.testing.assert_allclose(event["positions_before"], points[index], rtol=0, atol=1e-9)
        np.testing.assert_allclose(
            event["applied_velocity"], displacement[index] / dt, rtol=0, atol=1e-9
        )
        np.testing.assert_allclose(row["speeds"], lengths[index] / dt, rtol=0, atol=1e-9)
        linked.append(event_index)
    assert linked == [
        i for i, event in enumerate(controls) if event["phase"] == "execution" and event["success"]
    ]
    assert all(event.get("applied_velocity") is None for event in controls if not event["success"])
    maximum_speed = float(np.max(lengths / dt)) if lengths.size else 0.0
    domain_violation = max(
        0.0, float(np.max(-points)), float(np.max(points - np.asarray(config["domain"])))
    )
    tolerance = config["qp_acceptance_tol"] if config["controller"] == "qp" else 1e-9
    assert minimum >= config["min_separation"] - tolerance
    assert maximum_speed <= config["max_speed"] + tolerance
    assert domain_violation <= tolerance
    for actual, recorded in (
        (minimum, summary["min_separation"]),
        (maximum_speed, summary["max_speed_observed"]),
        (float(np.sum(lengths)), summary["path_length"]),
    ):
        np.testing.assert_allclose(actual, recorded, rtol=0, atol=1e-8)
    np.testing.assert_allclose(
        np.sum(lengths, axis=0), summary["path_length_per_robot"], rtol=0, atol=1e-8
    )
    assert times[-1] == summary["completion_time_s"]
    assert (run["status"] == "completed") == (run["failure"] is None)
    timing = {}
    for phase in ("execution", "preview"):
        values = [event["wall_s"] for event in controls if event["phase"] == phase]
        timing[phase] = {
            "count": len(values),
            "sum_s": float(np.sum(values)),
            "median_s": float(np.median(values)) if values else None,
            "p95_s": float(np.percentile(values, 95)) if values else None,
            "max_s": max(values) if values else None,
        }
    return {
        "segments": len(displacement),
        "control_links": len(linked),
        "min_separation": minimum,
        "max_speed": maximum_speed,
        "domain_violation": domain_violation,
        "fleet_path": float(np.sum(lengths)),
        "timing": timing,
    }


def audit_bundle(path: Path) -> tuple[dict[str, Any], int]:
    manifest = strict_json(path / "artifact_manifest.json")
    for relative, expected in manifest.items():
        target = (path / relative).resolve()
        assert target.is_relative_to(path.resolve()) and not target.is_symlink()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
        if target.suffix == ".json":
            strict_json(target)
    metadata = strict_json(path / "metadata.json")
    with zipfile.ZipFile(path / "source_snapshot.zip") as archive:
        assert archive.testzip() is None
        for relative, expected in metadata["source_sha256"].items():
            assert hashlib.sha256(archive.read(relative)).hexdigest() == expected
    comparison = strict_json(path / "comparison.json")
    for run in comparison["runs"]:
        method_dir = path / run["method"]
        assert pq.read_table(method_dir / "robots.parquet").to_pylist() == run["motion"]
        assert pq.read_table(method_dir / "samples.parquet").to_pylist() == run["samples"]
        assert strict_json(method_dir / "controls.json") == run["controls"]
        parquet_controls = pq.read_table(method_dir / "controls.parquet").to_pylist()
        assert len(parquet_controls) == len(run["controls"])
        for raw, restored in zip(run["controls"], parquet_controls, strict=True):
            assert all(restored.get(key) == value for key, value in raw.items())
    return comparison, len(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/m1-20260909/validation"))
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output.resolve() / f"batch-{stamp}-{uuid.uuid4().hex[:6]}"
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "validation_program.py").write_bytes(Path(__file__).read_bytes())
    report: dict[str, Any] = {
        "scope": "M1 development/control validation, not M6 evidence",
        "created_at": datetime.now(UTC).isoformat(),
        "records": [],
        "manifest_hashes_checked": 0,
        "complete": False,
    }
    jobs = [("pilot", 4, "combined", 7, controller, 300.0) for controller in ("qp", "filter")]
    jobs += [
        ("matrix", robots, scenario, seed, controller, 90.0)
        for robots, scenario, seed, controller in product(
            (2, 4), ("nominal", "combined"), (7, 19), ("filter", "qp")
        )
    ]
    started = time.perf_counter()
    for phase, robots, scenario, seed, controller, duration in jobs:
        comparison = run_comparison(
            scenario_config(
                scenario, robots=robots, seed=seed, duration_s=duration, controller=controller
            ),
            scenario=scenario,
        )
        bundle = save_comparison(comparison, destination / phase)
        comparison, verified = audit_bundle(bundle)
        report["manifest_hashes_checked"] += verified
        for run in comparison["runs"]:
            report["records"].append(
                {
                    "phase": phase,
                    "robots": robots,
                    "scenario": scenario,
                    "seed": seed,
                    "controller": controller,
                    "duration_s": duration,
                    "method": run["method"],
                    "path": str(bundle),
                    "status": run["status"],
                    "failure": run["failure"],
                    "summary": run["summary"],
                    "audit": audit_run(run),
                }
            )
        (destination / "validation.json").write_text(
            json.dumps(report, allow_nan=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{phase}: {robots} robots {scenario} seed={seed} {controller}: "
            f"{comparison['runtime_s']:.3f}s compute, {comparison['status']}; {bundle.name}",
            flush=True,
        )
        if phase == "pilot":
            for row in report["records"][-3:]:
                print(f"  {row['method']}: {row['audit']['timing']}", flush=True)
    report["complete"] = True
    report["elapsed_including_io_s"] = time.perf_counter() - started
    report["failure_count"] = sum(row["status"] == "failed" for row in report["records"])
    (destination / "validation.json").write_text(
        json.dumps(report, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Validated {len(report['records'])} policy runs; index: {destination / 'validation.json'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
