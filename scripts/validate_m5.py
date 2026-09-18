"""M5 closed-loop ECC profile: pre-declared qualitative criteria and independent audits.

The eight criteria below are written from the paper's own statements about its
simulations (pp. 308-310) and are saved to ``criteria_declared.json`` *before* any run of
this batch starts. They are evaluated per seed and configuration and reported as counts;
nothing is re-tuned after seeing them. Seed 7 was also used for the development pilot that
exposed the solver conditioning fix; it is kept, not dropped.

A run whose QP is rejected is kept and reported as failed. Its pair then counts as not
meeting any criterion, because a truncated run cannot support a claim about the end state.

Configurations
--------------
A  Theorem 1 scale (k(x,x) = 1), robots start at the square (0, 75)   — primary
B  Theorem 1 scale, robots start at the field edge (0, 58)          — sensitivity
C  Fig. 3 scale (k(x,x) = 4), start at (0, 75)                       — sensitivity
D  Fig. 3 scale, start at the field edge                             — sensitivity

A is primary because it follows the text and the figures' starting square. B and D exist
because, under A and C, the constraint-only controller receives no usable gradient 15 m
outside the field, so the paper's deadlock mechanism cannot even be exercised there.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sim import ecc2025
from attain_sampling.sim.ecc2025 import EccProfileConfig, ground_truth, run_ecc_profile
from attain_sampling.sources.ecc2025 import parameters

PAPER = parameters()
SEEDS = (7, 19, 31, 43, 59)
CONFIGURATIONS: dict[str, dict[str, Any]] = {
    "A_theorem_scale_paper_start": {"signal_variance": 1.0, "start_center": (0.0, 75.0)},
    "B_theorem_scale_edge_start": {"signal_variance": 1.0, "start_center": (0.0, 58.0)},
    "C_figure_scale_paper_start": {"signal_variance": 4.0, "start_center": (0.0, 75.0)},
    "D_figure_scale_edge_start": {"signal_variance": 4.0, "start_center": (0.0, 58.0)},
}
STALL_RATIO = 0.25
UNCOVERED_MIN = 0.05
NEAR_ZERO_MSE_FRACTION = 0.05
CRITERIA: dict[str, dict[str, str]] = {
    "C1_constraint_only_stalls": {
        "source": "p. 308, Fig. 2: a robot stays in a low-variance region from 640 s to 1000 s",
        "test": (
            f"some E0 robot's path over [640, 1000] s is below {STALL_RATIO} of its path over "
            f"[0, 360] s, while more than {UNCOVERED_MIN} of F_d keeps variance above 0.5 k(x,x)"
        ),
    },
    "C2_constraint_only_leaves_the_track_early": {
        "source": "p. 308: J gets off the track of constraint (6) immediately",
        "test": "E0 first violates eq. (5) at an epoch l <= 5",
    },
    "C3_both_initially_meet_the_decay": {
        "source": "p. 310: the decay rate of J initially meets (6) for both controllers",
        "test": "both E0 and E1 satisfy eq. (5) at l = 1",
    },
    "C4_both_end_stationary_and_violating": {
        "source": "p. 310: both reach stationary values while violating (6); J never reaches 0",
        "test": "both violate eq. (5) at the final epoch and both final J are positive",
    },
    "C5_constraint_only_ends_with_larger_J": {
        "source": "p. 310: the final J of controller (11) is bigger than that of (17)",
        "test": "final J(E0) > final J(E1)",
    },
    "C6_constraint_only_ends_with_larger_error": {
        "source": "p. 310: the difference in mean squared error is not negligible in the end",
        "test": "final MSE(E0) > final MSE(E1)",
    },
    "C7_hierarchical_error_nearly_vanishes": {
        "source": "p. 310: the error for the hierarchical controller converges to almost zero",
        "test": f"final MSE(E1) <= {NEAR_ZERO_MSE_FRACTION} x initial MSE",
    },
    "C8_hierarchical_covers_without_stalling": {
        "source": "p. 309: robots densely cover the whole area without getting stuck",
        "test": "uncovered fraction(E1) < uncovered fraction(E0) and no E1 robot stalls",
    },
}


def stalled(summary: dict[str, Any]) -> bool:
    early = summary["path_first_360s_m"]
    late = summary["path_last_360s_m"]
    return any(
        first > 0 and last < STALL_RATIO * first for first, last in zip(early, late, strict=True)
    )


def evaluate(e0: dict[str, Any], e1: dict[str, Any]) -> dict[str, bool]:
    # A rejected controller may stop before the first sample. Preserve that failure
    # instead of indexing a nonexistent epoch or treating its partial end state as final.
    if any(run["status"] != "completed" for run in (e0, e1)):
        return dict.fromkeys(CRITERIA, False)
    s0, s1 = e0["summary"], e1["summary"]
    last0, last1 = e0["epochs"][-1], e1["epochs"][-1]
    first_decay_met = all(
        len(run["epochs"]) > 1 and run["epochs"][1]["meets_eq5"] for run in (e0, e1)
    )
    violation0 = s0["first_eq5_violation_epoch"]
    return {
        "C1_constraint_only_stalls": stalled(s0) and s0["uncovered_fraction"] > UNCOVERED_MIN,
        "C2_constraint_only_leaves_the_track_early": violation0 is not None and violation0 <= 5,
        "C3_both_initially_meet_the_decay": first_decay_met,
        "C4_both_end_stationary_and_violating": bool(
            not last0["meets_eq5"] and not last1["meets_eq5"] and last0["J"] > 0 and last1["J"] > 0
        ),
        "C5_constraint_only_ends_with_larger_J": s0["final_J"] > s1["final_J"],
        "C6_constraint_only_ends_with_larger_error": s0["final_mse"] > s1["final_mse"],
        "C7_hierarchical_error_nearly_vanishes": (
            s1["final_mse"] <= NEAR_ZERO_MSE_FRACTION * s1["initial_mse"]
        ),
        "C8_hierarchical_covers_without_stalling": (
            s1["uncovered_fraction"] < s0["uncovered_fraction"] and not stalled(s1)
        ),
    }


def audit(run: dict[str, Any]) -> dict[str, Any]:
    """Recompute J from the recorded samples and re-check the recorded limits."""
    config = run["config"]
    queries = np.asarray(run["field"]["queries"])
    signal = float(config["signal_variance"])
    model = SparseOnlineGP(
        length_scale=float(PAPER["L"]),
        signal_variance=signal,
        noise_variance=float(PAPER["sigma_eps"]) ** 2,
        max_basis=int(PAPER["n_d_max"]),
        novelty_tolerance=float(PAPER["omega"]) / signal,
    )
    by_epoch: dict[int, list[dict[str, Any]]] = {}
    for sample in run["samples"]:
        by_epoch.setdefault(sample["l"], []).append(sample)
    worst = 0.0
    for entry in run["epochs"][1:]:
        for sample in sorted(by_epoch.get(entry["l"], []), key=lambda item: item["robot"]):
            model.update(np.asarray([sample["position"]]), np.asarray([sample["value"]]))
        variance = model.predict(queries, variance="latent").variance
        worst = max(worst, abs(float(np.sum(variance)) - entry["J"]))
    assert worst <= 1e-8 * max(1.0, run["epochs"][0]["J"]), worst
    summary = run["summary"]
    assert summary["max_speed_mps"] <= float(config["max_speed"]) + 1e-6
    assert summary["min_separation_m"] >= float(PAPER["d_ca"]) - 1e-6
    return {"max_J_recompute_error": worst, "epochs": len(run["epochs"]) - 1}


def paired_innovations(e0: dict[str, Any], e1: dict[str, Any], seed: int) -> float:
    # A failed run is truncated; only its received prefix has a paired innovation.
    # In particular, do not pass an empty (0,) positions array to the field evaluator.
    shared = min(len(e0["samples"]), len(e1["samples"]))
    if shared == 0:
        return 0.0
    prefixes = [run["samples"][:shared] for run in (e0, e1)]
    keys = [[(sample["l"], sample["robot"]) for sample in samples] for samples in prefixes]
    if keys[0] != keys[1]:
        raise ValueError("paired innovation prefixes must share the same (l, robot) keys")
    truth = ground_truth(seed, int(e0["config"]["field_components"]))
    noise = []
    for samples in prefixes:
        positions = np.asarray([sample["position"] for sample in samples])
        values = np.asarray([sample["value"] for sample in samples])
        noise.append(values - ecc2025._field(positions, truth))
    return float(np.max(np.abs(noise[0] - noise[1])))


def write_json(path: Path, value: Any) -> str:
    # Bytes, not text: Windows text mode would write CRLF and break the recorded hash.
    payload = (json.dumps(value, allow_nan=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in SEEDS))
    parser.add_argument("--duration", type=float, default=1000.0)
    args = parser.parse_args()
    seeds = tuple(int(value) for value in args.seeds.split(","))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output / f"m5-{datetime.now(UTC):%Y%m%d}" / "validation"
    destination /= f"batch-{stamp}-{uuid.uuid4().hex[:6]}"
    (destination / "runs").mkdir(parents=True)
    (destination / "validate_m5.py").write_bytes(Path(__file__).read_bytes())

    declared = {
        "declared_at": datetime.now(UTC).isoformat(),
        "criteria": CRITERIA,
        "configurations": {
            name: {
                "signal_variance": options["signal_variance"],
                "start_center": list(options["start_center"]),
            }
            for name, options in CONFIGURATIONS.items()
        },
        "seeds": list(seeds),
        "duration_s": args.duration,
        "note": (
            "declared before this batch ran; seed 7 was also used in the development pilot. "
            "An earlier batch was stopped after five runs, before any result was read, to fix "
            "the recorded start description and keep failed runs; the criteria are unchanged."
        ),
    }
    hashes = {
        "criteria_declared.json": write_json(destination / "criteria_declared.json", declared)
    }
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for name, options in CONFIGURATIONS.items():
        for seed in seeds:
            runs = {}
            for controller in ("constraint_only", "hierarchical"):
                config = EccProfileConfig(
                    controller=controller,  # type: ignore[arg-type]
                    seed=seed,
                    duration_s=args.duration,
                    signal_variance=options["signal_variance"],
                    start_center=options["start_center"],
                )
                run = run_ecc_profile(config)
                runs[controller] = run
                # Short names: nested output paths can exceed the Windows path limit.
                tag = "e0" if controller == "constraint_only" else "e1"
                label = f"{name[0]}_s{seed}_{tag}.json.gz"
                payload = json.dumps(run, allow_nan=False).encode()
                with gzip.open(destination / "runs" / label, "wb") as stream:
                    stream.write(payload)
                hashes[f"runs/{label}"] = hashlib.sha256(payload).hexdigest()
            e0, e1 = runs["constraint_only"], runs["hierarchical"]
            failed = {
                label: run["failure"]
                for label, run in (("E0", e0), ("E1", e1))
                if run["status"] != "completed"
            }
            criteria = evaluate(e0, e1)
            record = {
                "configuration": name,
                "seed": seed,
                "failed_runs": failed,
                "criteria": criteria,
                "audit": {"E0": audit(e0), "E1": audit(e1)},
                "max_paired_innovation_gap": paired_innovations(e0, e1, seed),
                "E0": {key: e0["summary"][key] for key in e0["summary"]},
                "E1": {key: e1["summary"][key] for key in e1["summary"]},
                "E0_moved": e0["summary"]["max_speed_mps"] > 1e-2,
            }
            assert record["max_paired_innovation_gap"] <= 1e-9
            results.append(record)
            print(
                f"{name} seed {seed}{' FAILED ' + ','.join(failed) if failed else ''}: "
                f"E0 J={e0['summary']['final_J']:.1f} "
                f"mse={e0['summary']['final_mse']:.1f} | E1 J={e1['summary']['final_J']:.1f} "
                f"mse={e1['summary']['final_mse']:.1f} | "
                + " ".join(
                    key[:2] + ("+" if value else "-") for key, value in record["criteria"].items()
                ),
                flush=True,
            )
    counts = {
        name: {
            criterion: sum(
                row["criteria"][criterion] for row in results if row["configuration"] == name
            )
            for criterion in CRITERIA
        }
        for name in CONFIGURATIONS
    }
    failures = {
        name: sum(bool(row["failed_runs"]) for row in results if row["configuration"] == name)
        for name in CONFIGURATIONS
    }
    report = {
        "scope": (
            "M5 qualitative source-profile comparison; not a numerical reproduction of the "
            "paper's figures, whose seeds and ground truth are unpublished"
        ),
        "created_at": datetime.now(UTC).isoformat(),
        "criteria": CRITERIA,
        "seeds": list(seeds),
        "counts_out_of_seeds": counts,
        "pairs_with_a_failed_run": failures,
        "results": results,
        "elapsed_s": time.perf_counter() - started,
    }
    hashes["validation.json"] = write_json(destination / "validation.json", report)
    write_json(destination / "manifest.json", hashes)
    print(json.dumps(counts, indent=2))
    print(f"Validated {len(results)} paired seeds: {destination / 'validation.json'}")


if __name__ == "__main__":
    main()
