"""Compare tick-by-tick execution against independently preserved mission evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import mission_reference as reference

from attain_sampling.sim import mapping

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / ".scratch/mission-execution-ownership/reference/frozen-20260918"
REPAIRED = ROOT / ".scratch/ci-portability/numerical-reference"


def run_stepped(config: mapping.MappingConfig, method: str) -> dict[str, Any]:
    """Use only the agreed execution interface, with a finite physical-tick limit."""
    mission = mapping._MissionExecution(config, method)
    for _ in range(round(config.duration_s / config.dt)):
        if mission.read().status != "running":
            break
        mission.advance()
    if mission.read().status == "running":
        raise AssertionError("mission did not close by its physical deadline")
    return mission.finish()


def check(output: Path) -> bool:
    output.mkdir(parents=True, exist_ok=False)
    # Select the execution interface at the harness's whole-mission seam. Its
    # existing failure triggers, normalization and integrity checks remain intact.
    with patch.object(mapping, "run_mapping", run_stepped):
        historical_passed = reference.check(HISTORICAL, output / "historical")
        repaired_passed = reference.check(REPAIRED, output / "repaired")
    historical = json.loads((HISTORICAL / "manifest.json").read_text(encoding="utf-8"))
    repaired = json.loads((REPAIRED / "manifest.json").read_text(encoding="utf-8"))
    original_hash = hashlib.sha256((HISTORICAL / "manifest.json").read_bytes()).hexdigest()
    if repaired["baseline"]["historical_manifest_sha256"] != original_hash:
        raise ValueError("post-repair checkpoint does not identify this historical reference")
    overrides = {row["name"]: row for row in repaired["cases"]}
    if set(overrides) != {"dp_sogp_pruning"}:
        raise ValueError("unexpected cases in the explicitly scoped numerical checkpoint")
    differences = []
    for row in historical["cases"]:
        expected_row = overrides.get(row["name"], row)
        expected_root = REPAIRED if row["name"] in overrides else HISTORICAL
        expected = json.loads((expected_root / expected_row["normalized"]).read_text("utf-8"))
        actual = json.loads((output / "historical" / row["normalized"]).read_text("utf-8"))
        difference = reference.first_difference(expected, actual)
        if difference:
            differences.append({"case": row["name"], "difference": difference})
    captured = json.loads((output / "historical/report.json").read_text("utf-8"))
    report = {
        "passed": not differences and repaired_passed,
        "cases_compared": len(historical["cases"]),
        "historical_comparison_passed": historical_passed,
        "repaired_comparison_passed": repaired_passed,
        "historical_manifest_sha256": original_hash,
        "repaired_manifest_sha256": hashlib.sha256(
            (REPAIRED / "manifest.json").read_bytes()
        ).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "harness_sha256": captured["harness_sha256"],
        "source": captured["source"],
        "environment": captured["environment"],
        "differences": differences,
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Incremental preservation: {report['cases_compared']} cases; passed={report['passed']}")
    return bool(report["passed"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    return 0 if check(parser.parse_args().output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
