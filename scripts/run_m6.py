"""M6/M7 held-out batch: every job of a frozen protocol, in parallel, with raw records.

``--milestone m6`` (default) runs the holonomic M6 protocol, ``--milestone m7`` the
turn-constrained USV protocol of M7 and ``--milestone m7v2`` its confirmation on new
tasks with the corrected primitive planner (D057). All use the same machinery and checks.

The protocol hash is checked before anything runs, and the job list is written to
``declared.json`` before the first job starts. Each job saves its full comparison
(frames, motion, samples, controls, plans) as gzip JSON; metrics and warnings are
computed from that record, and ``scripts/report_m6.py`` recomputes them from the saved
files before analysing anything.

In-worker audits, per run: the M1 geometric/control audit (``validate_m1.audit_run``)
and, for P, the M4 decision audit (``validate_m4.audit_decisions``). Across jobs: every
job of the same task and duration must see the same noise and dropout schedule.

``--dev-seeds`` and ``--allow-unfrozen`` exist for smoke tests. ``--dev-seeds`` replaces
the held-out tasks with development seeds, so a smoke test never touches a held-out
task before the protocol is frozen. Such batches are labelled ``development`` and are
never evidence for the protocol.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
import traceback
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_m1 import audit_run  # noqa: E402
from validate_m4 import audit_decisions  # noqa: E402

from attain_sampling.demo.runner import run_comparison  # noqa: E402
from attain_sampling.eval import m6, m7, m7_v2  # noqa: E402
from attain_sampling.eval.m6 import Job  # noqa: E402

MILESTONES = {"m6": m6, "m7": m7, "m7v2": m7_v2}


def write_bytes(path: Path, payload: bytes) -> str:
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> str:
    return write_bytes(path, (json.dumps(value, allow_nan=False, indent=2) + "\n").encode())


def schedule_signature(run: dict[str, Any]) -> str:
    """Hash of the exogenous sample schedule: identical for every policy on a task."""
    rows = [
        [s["time_s"], s["robot_id"], s["received"], s["noise_innovation"], s["dropout_uniform"]]
        for s in run["samples"]
    ]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def execute(
    job: Job, protocol: dict[str, Any], runs_dir: str, milestone: str = "m6"
) -> dict[str, Any]:
    module: Any = MILESTONES[milestone]
    started = time.perf_counter()
    record: dict[str, Any] = {
        "label": job.label,
        "block": job.block,
        "variant": job.variant,
        "scenario": job.scenario,
        "base": job.base,
        "seed": job.seed,
        "methods": list(job.methods),
        "overrides": dict(job.overrides),
    }
    try:
        config = module.job_config(job, protocol)
        comparison = run_comparison(config, scenario=job.scenario, methods=job.methods)
        payload = json.dumps(comparison, allow_nan=False).encode()
        packed = gzip.compress(payload, compresslevel=6)
        record["file"] = f"runs/{job.label}.json.gz"
        record["sha256_uncompressed"] = hashlib.sha256(payload).hexdigest()
        record["sha256"] = write_bytes(Path(runs_dir) / f"{job.label}.json.gz", packed)
        target = float(protocol["target"]["value"])
        record["runs"] = {}
        record["audits"] = {}
        signatures = set()
        for run in comparison["runs"]:
            metrics = module.run_metrics(run, target)
            completed = metrics["status"] == "completed"
            if job.block == "main" and run["method"] in {"dp", "p"} and completed:
                metrics["warnings"] = module.warning_series(run, target)
            record["runs"][run["method"]] = metrics
            audit: dict[str, Any] = {}
            if run["status"] == "completed":
                audit["m1"] = audit_run(run)
            if run["method"] == "p":
                audit["m4"] = audit_decisions(run)
            record["audits"][run["method"]] = audit
            if run["status"] == "completed":
                signatures.add(schedule_signature(run))
        if len(signatures) > 1:
            raise RuntimeError("policies on one task saw different exogenous schedules")
        record["schedule_signature"] = signatures.pop() if signatures else None
        record["duration_s"] = config.duration_s
        record["config_hash"] = comparison["config_hash"]
        record["status"] = comparison["status"]
    except Exception as error:  # noqa: BLE001 - every job failure is recorded, not hidden
        record["status"] = "job_error"
        record["error"] = f"{type(error).__name__}: {error}"
        record["traceback"] = traceback.format_exc()
    record["wall_s"] = time.perf_counter() - started
    return record


def source_snapshot(destination: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, patterns in (("src", ("*.py",)), ("scripts", ("*.py",)), ("configs", ("*",))):
            for pattern in patterns:
                for path in sorted((ROOT / folder).rglob(pattern)):
                    if path.is_file() and "__pycache__" not in path.parts:
                        relative = path.relative_to(ROOT).as_posix()
                        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
                        archive.write(path, relative)
        for name in ("pyproject.toml", "uv.lock"):
            path = ROOT / name
            if path.is_file():
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                archive.write(path, name)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    parser.add_argument("--milestone", choices=tuple(MILESTONES), default="m6")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--dev-seeds", default=None, help="smoke test: comma-separated development seeds"
    )
    parser.add_argument("--allow-unfrozen", action="store_true", help="smoke test only")
    args = parser.parse_args()
    development = args.dev_seeds is not None or args.allow_unfrozen
    if args.allow_unfrozen and args.dev_seeds is None:
        parser.error("--allow-unfrozen requires --dev-seeds: never run held-out tasks unfrozen")
    module: Any = MILESTONES[args.milestone]
    protocol = module.load_protocol(require_frozen=not args.allow_unfrozen)
    jobs = module.enumerate_jobs(protocol)
    if args.dev_seeds is not None:
        seeds = [int(value) for value in args.dev_seeds.split(",")]
        if not set(seeds) <= set(protocol["tasks"]["development_seeds"]):
            parser.error("--dev-seeds must be development seeds listed in the protocol")
        first = jobs[0].seed
        jobs = [replace(job, seed=seed) for job in jobs if job.seed == first for seed in seeds]
        protocol["tasks"]["seed_override"] = seeds
    workers = args.workers or int(protocol["execution"]["workers"])

    now = datetime.now(UTC)
    kind = "development" if development else "heldout"
    destination = args.output / f"{args.milestone}-{now:%Y%m%d}" / kind
    destination /= f"batch-{now:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:6]}"
    runs_dir = destination / "runs"
    runs_dir.mkdir(parents=True)
    hashes = {
        "protocol.yaml": write_bytes(
            destination / "protocol.yaml",
            Path(module.PROTOCOL_PATH).read_bytes(),
        ),
    }
    hashes["declared.json"] = write_json(
        destination / "declared.json",
        {
            "declared_at": now.isoformat(),
            "kind": kind,
            "milestone": args.milestone,
            "protocol_id": protocol["protocol_id"],
            "protocol_sha256": protocol["sha256"],
            "jobs": [job.label for job in jobs],
            "seeds": sorted({job.seed for job in jobs}),
            "workers": workers,
            "note": (
                "written before the first job started"
                if not development
                else "development smoke batch; not evidence for the frozen protocol"
            ),
        },
    )
    source_hashes = source_snapshot(destination / "source_snapshot.zip")
    hashes["source_snapshot.zip"] = hashlib.sha256(
        (destination / "source_snapshot.zip").read_bytes()
    ).hexdigest()
    hashes["source_sha256.json"] = write_json(destination / "source_sha256.json", source_hashes)
    print(f"{len(jobs)} jobs, {workers} workers -> {destination}", flush=True)

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(execute, job, protocol, str(runs_dir), args.milestone) for job in jobs
        ]
        for count, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            records.append(record)
            if record["status"] == "job_error":
                print(f"ERROR {record['label']}: {record['error']}", flush=True)
            if count % 20 == 0 or count == len(jobs):
                elapsed = time.perf_counter() - started
                print(f"{count}/{len(jobs)} jobs in {elapsed:.0f}s", flush=True)
    order = {job.label: index for index, job in enumerate(jobs)}
    records.sort(key=lambda row: order[row["label"]])

    # Every job on the same task, duration and disturbance setting must share its
    # exogenous schedule, whatever the policy, GP backend or kernel.
    schedules: dict[tuple[int, float, str], set[str]] = {}
    for record in records:
        if record.get("schedule_signature"):
            key = (record["seed"], record["duration_s"], record["base"])
            schedules.setdefault(key, set()).add(record["schedule_signature"])
    mismatched = sorted(key for key, values in schedules.items() if len(values) > 1)

    errors = [record["label"] for record in records if record["status"] == "job_error"]
    for record in records:
        if record.get("sha256"):
            hashes[record["file"]] = record["sha256"]
    hashes["records.json"] = write_json(destination / "records.json", records)
    hashes["batch.json"] = write_json(
        destination / "batch.json",
        {
            "kind": kind,
            "protocol_sha256": protocol["sha256"],
            "jobs": len(jobs),
            "job_errors": errors,
            "failed_runs": sum(
                run["status"] != "completed"
                for record in records
                for run in record.get("runs", {}).values()
            ),
            "schedule_mismatches": [list(key) for key in mismatched],
            "wall_s": time.perf_counter() - started,
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )
    write_json(destination / "manifest.json", hashes)
    print(f"done: {len(errors)} job errors, {len(mismatched)} schedule mismatches", flush=True)
    return 1 if errors or mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
