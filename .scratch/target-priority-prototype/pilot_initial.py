"""THROWAWAY: predeclared, one-seed pilot; run with the parent project's Python."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from attain_sampling.attainability import policy  # noqa: E402
from attain_sampling.sim import mapping  # noqa: E402


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    legacy_path = ROOT / ".scratch/target-priority-prototype/legacy_policy.py"
    spec = importlib.util.spec_from_file_location("prototype_legacy_policy", legacy_path)
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy
    spec.loader.exec_module(legacy)

    def legacy_manage(**kwargs):
        kwargs["settings"] = legacy.PolicySettings(**asdict(kwargs["settings"]))
        return legacy.manage_plan(**kwargs)

    base = mapping.MappingConfig(
        domain=(20.0, 14.0), robot_count=2, duration_s=20.0, dt=0.5,
        sample_period_s=2.0, grid_shape=(12, 8), dp_grid_shape=(5, 4),
        dp_horizon_steps=2, length_scale=3.0, max_speed=2.0, seed=7,
        dropout_prob=0.0, controller="filter", gp_backend="exact", model="holonomic",
    )
    metadata = {
        "scope": "predeclared development pilot; no held-out evidence; no charged delay",
        "python": sys.version, "platform": platform.platform(), "base_config": asdict(base),
        "module_paths": {"mapping": mapping.__file__, "policy": policy.__file__},
        "source_hashes": {
            "mapping": digest(Path(mapping.__file__)), "policy": digest(Path(policy.__file__)),
            "legacy_policy": digest(legacy_path), "pilot": digest(Path(__file__)),
            "protocol": digest(ROOT / ".scratch/target-priority-prototype/protocol.md"),
        },
    }
    write_json(output / "metadata.json", metadata)
    calibration = mapping.run_mapping(base, "adaptive")
    target = 1.05 * calibration["summary"]["mean_variance"]
    write_json(output / "calibration.json", {"rule": "1.05 * nominal B2 final mean variance",
        "target": target, "summary": calibration["summary"]})
    print(f"Frozen target: {target:.17g}", flush=True)
    arms = [("B2", "adaptive", False, .01), ("B3", "dp", False, .01),
            ("historical_P", "p", True, .01), ("target_priority_P", "p", False, .01),
            ("zero_margin_P", "p", True, 0.0)]
    results, rows = {}, []
    for drift in (0.0, .35, 1.0):
        for arm, method, historical, margin in arms:
            config = replace(base, drift_strength=drift, target_mean_variance=target,
                             p_switch_margin=margin)
            with patch.object(mapping, "manage_plan", legacy_manage if historical else policy.manage_plan):
                result = mapping.run_mapping(config, method)
            key = f"{arm}-drift-{drift:g}"
            results[(drift, arm)] = result
            raw = json.dumps(result, allow_nan=False).encode()
            (output / f"{key}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
            decisions = []
            for plan in result["plans"]:
                accepted = [c for c in plan.get("candidates", []) if c["status"] == "accepted"]
                retained = next((c for c in accepted if c["candidate_id"] == "retained-plan"), None)
                scored = [c for c in accepted if "mission_end_mean_variance" in c]
                if not scored:
                    continue
                best = min(c["mission_end_mean_variance"] for c in scored)
                value = retained["mission_end_mean_variance"] if retained else None
                decisions.append({
                    "time_s": plan["generated_at_s"], "plan_id": plan["plan_id"],
                    "selected_candidate_id": plan["selected_candidate_id"],
                    "best_forecast": best, "retained_forecast": value,
                    "crosses_target": value is not None and best <= target < value,
                    "override_needed": value is not None and best <= target < value
                        and value - best <= plan["decision"]["switch_margin_variance"],
                    "decision": plan["decision"], "target_risk": plan["target_risk"],
                })
            write_json(output / f"{key}-decisions.json", decisions)
            summary = result["summary"]
            row = {
                "arm": arm, "drift": drift, "status": result["status"], "failure": result["failure"],
                "mean_variance": summary.get("mean_variance"), "max_variance": summary.get("max_variance"),
                "rmse": summary.get("rmse"), "success": result["status"] == "completed"
                    and summary["mean_variance"] <= target,
                "runtime_s": summary["runtime_s"], "planning_s": summary["planning_s"],
                "samples_received": summary["samples_received"],
                "decision_count": len(result["plans"]),
                "candidate_records": sum(len(p.get("candidates", [])) for p in result["plans"]),
                "candidates_evaluated": sum(p.get("decision", {}).get("candidates_evaluated", 0)
                    for p in result["plans"]) if method == "p" else None,
                "crossing_count": sum(d["crosses_target"] for d in decisions),
                "override_needed_count": sum(d["override_needed"] for d in decisions),
                "override_count": sum(d["decision"]["reason"] ==
                    "candidate_reaches_target_while_retained_plan_misses" for d in decisions),
                "raw_file": f"{key}.json.gz", "decisions_file": f"{key}-decisions.json",
            }
            rows.append(row)
            print(f"{key}: mean={row['mean_variance']:.6f}, success={row['success']}, "
                  f"runtime={row['runtime_s']:.3f}s, overrides={row['override_count']}", flush=True)
    for row in rows:
        reference = results[(row["drift"], "historical_P")]
        current = results[(row["drift"], row["arm"])]
        for field, key, name in (("motion", "targets", "first_changed_route_s"),
                                 ("samples", "actual_position", "first_changed_receipt_s")):
            row[name] = next((a["time_s"] for a, b in zip(current[field], reference[field])
                              if a[key] != b[key]), None)
    write_json(output / "summary.json", {"target": target, "rows": rows})


if __name__ == "__main__":
    main()
