"""Analyse an M6 or M7 batch from its raw records only, then draw the report figures.

Every metric and warning is recomputed from ``runs/*.json.gz`` (after checking each
file against the manifest) and must equal the record the worker wrote. Only then is
the pre-declared analysis run. Figures are drawn from the analysis and the recomputed
records; nothing is typed in by hand.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fieldwork-matplotlib"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from attain_sampling.eval import m6, m7, m7_v2  # noqa: E402
from attain_sampling.eval.m6 import METHOD_CODES, protocol_digest  # noqa: E402
from attain_sampling.eval.m6 import task_seeds as protocol_seeds  # noqa: E402

# Reference palette (dataviz skill): slots 1-2 validated all-pairs in light mode;
# the other methods take the muted ink and are identified by axis position.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
B3_COLOR = "#2a78d6"
P_COLOR = "#eb6834"
METHOD_COLORS = {"dp": B3_COLOR, "p": P_COLOR}
STYLE: dict[Any, Any] = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.grid": True,
    "axes.axisbelow": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "grid.linestyle": "-",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 9,
    "lines.linewidth": 2,
    "lines.solid_capstyle": "round",
    "legend.frameon": False,
}
SCENARIO_LABELS = {
    "nominal": "Nominal",
    "dropout": "Dropout",
    "drift": "Drift",
    "combined": "Combined",
    "short_budget": "Short budget",
}


def _load(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rb") as stream:
        value = json.loads(stream.read())
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a comparison record")
    return value


MILESTONES: dict[str, Any] = {"m6": m6, "m7": m7, "m7v2": m7_v2}


def recompute(args: tuple[str, str, dict[str, Any], float, str]) -> dict[str, Any]:
    """Recompute one job's metrics and warnings from its saved file."""
    batch, file, record, target, milestone = args
    module = MILESTONES[milestone]
    path = Path(batch) / file
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != record["sha256"]:
        raise RuntimeError(f"{file}: hash differs from the worker record")
    comparison = _load(path)
    runs: dict[str, Any] = {}
    for run in comparison["runs"]:
        metrics = module.run_metrics(run, target)
        if "warnings" in record["runs"][run["method"]]:
            metrics["warnings"] = module.warning_series(run, target)
        runs[run["method"]] = metrics
    if runs != record["runs"]:
        raise RuntimeError(f"{file}: recomputed metrics differ from the worker record")
    return {**{k: v for k, v in record.items() if k != "runs"}, "runs": runs}


def _forest(axis: Any, rows: list[tuple[str, dict[str, Any]]], color: str) -> None:
    """Mean paired difference with its bootstrap interval; zero marks no difference."""
    axis.axvline(0.0, color=AXIS, linewidth=1)
    for index, (_label, stats) in enumerate(rows):
        if stats["mean"] is None:
            continue
        axis.plot([stats["ci_low"], stats["ci_high"]], [index, index], color=color, lw=2)
        axis.plot(
            stats["mean"], index, "o", color=color, markersize=7, mec=SURFACE, mew=2, zorder=3
        )
    axis.set_yticks(range(len(rows)), [label for label, _ in rows])
    axis.invert_yaxis()
    axis.grid(axis="y", visible=False)


def figure_primary(analysis: dict[str, Any], destination: Path, tasks: int) -> Path:
    pairs = (("p-dp", "P − B3"), ("p-adaptive", "P − B2"), ("dp-adaptive", "B3 − B2"))
    scenarios = list(analysis["main"])
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True, constrained_layout=True)
    for axis, (key, title) in zip(axes, pairs, strict=True):
        rows = [
            (SCENARIO_LABELS[name], analysis["main"][name]["pairs"][key]["rmse"])
            for name in scenarios
        ]
        _forest(axis, rows, P_COLOR if key.startswith("p") else B3_COLOR)
        axis.set_title(title, loc="left")
        axis.set_xlabel("Paired Δ field RMSE (negative: left method better)")
    fig.suptitle(
        f"Mission-end field RMSE, paired over {tasks} tasks: mean and 95% bootstrap interval",
        x=0.01,
        ha="left",
        color=INK,
    )
    path = destination / "primary_delta_rmse.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def figure_rmse(records: list[dict[str, Any]], protocol: dict[str, Any], destination: Path) -> Path:
    methods = protocol["blocks"]["main"]["methods"]
    scenarios = list(protocol["blocks"]["main"]["scenarios"])
    fig, axes = plt.subplots(1, len(scenarios), figsize=(12, 3.6), sharey=True)
    rng = np.random.default_rng(0)
    for axis, scenario in zip(axes, scenarios, strict=True):
        rows = [r for r in records if r["block"] == "main" and r["scenario"] == scenario]
        for position, method in enumerate(methods):
            values = [
                r["runs"][method]["rmse"]
                for r in rows
                if r["runs"][method]["status"] == "completed"
            ]
            jitter = rng.uniform(-0.18, 0.18, len(values))
            color = METHOD_COLORS.get(method, MUTED)
            axis.scatter(position + jitter, values, s=12, color=color, alpha=0.55, linewidths=0)
            axis.plot([position - 0.3, position + 0.3], [np.median(values)] * 2, color=INK, lw=2)
        axis.set_xticks(range(len(methods)), [METHOD_CODES[m] for m in methods])
        axis.set_title(SCENARIO_LABELS[scenario], loc="left")
        axis.grid(axis="x", visible=False)
    axes[0].set_ylabel("Mission-end field RMSE")
    fig.suptitle(
        "Field RMSE per task (dots) and median (bar); B3 blue, P orange",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    path = destination / "rmse_by_method.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def figure_planning(analysis: dict[str, Any], protocol: dict[str, Any], destination: Path) -> Path:
    methods = protocol["blocks"]["main"]["methods"]
    scenarios = list(analysis["main"])
    fig, axis = plt.subplots(figsize=(7, 3.6))
    width = 0.8 / len(scenarios)
    for offset, scenario in enumerate(scenarios):
        for position, method in enumerate(methods):
            stats = analysis["main"][scenario]["methods"][method]["planning_s"]
            x = position - 0.4 + width * (offset + 0.5)
            color = METHOD_COLORS.get(method, MUTED)
            axis.plot([x, x], [stats["min"], stats["max"]], color=color, lw=1, alpha=0.6)
            axis.plot(x, stats["median"], "o", color=color, markersize=5, mec=SURFACE, mew=1)
    axis.set_yscale("log")
    axis.set_xticks(range(len(methods)), [METHOD_CODES[m] for m in methods])
    axis.set_ylabel("Planning wall time per mission (s, log)")
    axis.set_title(
        "Planning cost per mission: median and range over tasks; marks left to right are\n"
        "nominal, dropout, drift, combined, short budget",
        loc="left",
    )
    axis.grid(axis="x", visible=False)
    fig.tight_layout()
    path = destination / "planning_time.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def figure_warnings(analysis: dict[str, Any], destination: Path, target: float) -> Path:
    scenarios = list(analysis["main"])
    fig, axes = plt.subplots(
        2, len(scenarios), figsize=(12, 5.2), sharey=True, constrained_layout=True
    )
    for column, scenario in enumerate(scenarios):
        for row, (key, label) in enumerate(
            (("recall", "Recall (missed tasks warned)"), ("false_alarm_rate", "False-alarm rate"))
        ):
            axis = axes[row][column]
            drawn = False
            for method, name in (("dp", "B3"), ("p", "P")):
                summary = analysis["main"][scenario]["warnings"][method]["best"]
                if not summary.get("tasks"):
                    continue
                points = [
                    (item["epoch"], item[key])
                    for item in summary["per_epoch"]
                    if item[key] is not None
                ]
                if not points:
                    continue
                xs, ys = zip(*points, strict=True)
                axis.plot(xs, ys, color=METHOD_COLORS[method], label=name)
                drawn = True
            if not drawn:
                empty = "no missed tasks" if key == "recall" else "no tasks reached the target"
                axis.text(0.5, 0.5, empty, ha="center", color=MUTED, transform=axis.transAxes)
            axis.set_ylim(-0.03, 1.03)
            if row == 0:
                missed = analysis["main"][scenario]["warnings"]["p"]["best"].get("missed", 0)
                reached = analysis["main"][scenario]["warnings"]["p"]["best"].get("reached", 0)
                axis.set_title(
                    f"{SCENARIO_LABELS[scenario]}\nP: {missed} missed / {reached} reached",
                    loc="left",
                )
            if column == 0:
                axis.set_ylabel(label)
            if row == 1:
                axis.set_xlabel("Sampling epoch of the warning")
    fig.legend(
        handles=[
            Line2D([], [], color=B3_COLOR, label="B3 (evaluator's hold-continued forecast)"),
            Line2D([], [], color=P_COLOR, label="P (best candidate, its own target_risk)"),
        ],
        loc="upper right",
        ncols=2,
    )
    fig.suptitle(
        f"Does the mission-end forecast call the method's own outcome? (target {target:g})",
        x=0.01,
        ha="left",
        color=INK,
    )
    path = destination / "warnings.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def figure_blocks(analysis: dict[str, Any], destination: Path) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), constrained_layout=True)
    ablation = [
        (name.replace("p_", "").replace("_", " "), entry["minus_full_p"]["rmse"])
        for name, entry in analysis["ablation"].items()
    ]
    _forest(axes[0], ablation, P_COLOR)
    axes[0].set_title("Ablations: variant − full P", loc="left")
    axes[0].set_xlabel("Paired Δ field RMSE")
    sogp = analysis["sogp"]["sogp_32"]["minus_exact"]
    _forest(axes[1], [("B3", sogp["dp"]["rmse"]), ("P", sogp["p"]["rmse"])], INK_2)
    axes[1].set_title("SOGP-32 − exact GP (combined)", loc="left")
    axes[1].set_xlabel("Paired Δ field RMSE")
    mismatch = analysis["mismatch"]["length_scale_16"]["minus_matched"]
    rows = [(METHOD_CODES[m], mismatch[m]["rmse"]) for m in mismatch]
    _forest(axes[2], rows, INK_2)
    axes[2].set_title("GP length 16 m − 8 m (nominal)", loc="left")
    axes[2].set_xlabel("Paired Δ field RMSE")
    path = destination / "blocks_delta_rmse.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def figure_mismatch(analysis: dict[str, Any], destination: Path) -> Path:
    mismatch = analysis["mismatch"]["length_scale_16"]["minus_matched"]
    fig, axes = plt.subplots(1, 2, figsize=(8, 3), sharey=True, constrained_layout=True)
    for axis, metric, title in (
        (axes[0], "mean_variance", "Δ mean latent variance"),
        (axes[1], "rmse", "Δ field RMSE"),
    ):
        rows = [(METHOD_CODES[m], mismatch[m][metric]) for m in mismatch]
        _forest(axis, rows, INK_2)
        axis.set_title(title, loc="left")
    fig.suptitle(
        "Smoother GP (16 m) vs matched (8 m), nominal: the model's uncertainty and the"
        " map's error move apart",
        x=0.01,
        ha="left",
        color=INK,
    )
    path = destination / "mismatch_variance_vs_error.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def figure_usv_blocks(analysis: dict[str, Any], destination: Path) -> Path:
    """M7: ablations, the straight-line planner, and the rollout under each planner."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), constrained_layout=True)
    ablation = [
        (name.replace("p_", "").replace("_", " "), entry["minus_full_p"]["rmse"])
        for name, entry in analysis["ablation"].items()
    ]
    _forest(axes[0], ablation, P_COLOR)
    axes[0].set_title("Ablations: variant − full P", loc="left")
    axes[0].set_xlabel("Paired Δ field RMSE")
    straight = analysis["straight_line"]["straight"]["minus_primitives"]
    _forest(axes[1], [("B3", straight["dp"]["rmse"]), ("P", straight["p"]["rmse"])], INK_2)
    axes[1].set_title("Straight-line planner − primitive planner", loc="left")
    axes[1].set_xlabel("Paired Δ field RMSE")
    rollout = [
        ("primitive planner", analysis["ablation"]["p_no_rollout"]["minus_full_p"]["rmse"]),
        (
            "straight-line planner",
            analysis["straight_line"]["rollout_effect"]["no_rollout_minus_rollout_p"]["rmse"],
        ),
    ]
    _forest(axes[2], rollout, P_COLOR)
    axes[2].set_title("P without rollout − P with rollout", loc="left")
    axes[2].set_xlabel("Paired Δ field RMSE")
    path = destination / "usv_blocks_delta_rmse.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    batch: Path = args.batch
    declared = json.loads((batch / "declared.json").read_text(encoding="utf-8"))
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    protocol_text = (batch / "protocol.yaml").read_text(encoding="utf-8")
    if protocol_digest(protocol_text) != declared["protocol_sha256"]:
        raise SystemExit("batch protocol copy does not match its declaration")
    milestone = declared.get("milestone", "m6")
    module = MILESTONES[milestone]
    if declared["kind"] == "heldout":
        protocol = module.load_protocol()
        if protocol["sha256"] != declared["protocol_sha256"]:
            raise SystemExit("held-out batch was not produced by the frozen protocol")
    else:
        protocol = {**yaml.safe_load(protocol_text), "sha256": declared["protocol_sha256"]}
        protocol["tasks"]["seed_override"] = declared["seeds"]
    records = json.loads((batch / "records.json").read_text(encoding="utf-8"))
    errors = [record["label"] for record in records if record["status"] == "job_error"]
    if errors:
        raise SystemExit(f"batch has job errors: {errors}")
    for record in records:
        if manifest.get(record["file"]) != record["sha256"]:
            raise SystemExit(f"{record['file']} is not in the manifest with the same hash")
    target = float(protocol["target"]["value"])
    jobs = [(str(batch), record["file"], record, target, milestone) for record in records]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        recomputed = list(pool.map(recompute, jobs, chunksize=4))
    print(f"recomputed {len(recomputed)} jobs from raw records: identical", flush=True)

    analysis = module.analyze(recomputed, protocol)
    output = {
        "scope": (
            f"{milestone.upper()} held-out comparison on the independent profile; "
            "paired synthetic tasks, "
            "not a guarantee beyond this simulator"
            if declared["kind"] == "heldout"
            else "development smoke analysis; not evidence for the protocol"
        ),
        "kind": declared["kind"],
        "milestone": milestone,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol["sha256"],
        "target": target,
        "jobs": len(recomputed),
        "failed_runs": sum(
            run["status"] != "completed" for record in recomputed for run in record["runs"].values()
        ),
        "audits": {
            "m1_runs": sum("m1" in audit for r in records for audit in r["audits"].values()),
            "m4_p_runs": sum("m4" in audit for r in records for audit in r["audits"].values()),
            "m4_recomputed_prefixes": sum(
                audit["m4"]["independently_recomputed_prefixes"]
                for r in records
                for audit in r["audits"].values()
                if "m4" in audit
            ),
            "metrics_recomputed_from_raw": len(recomputed),
        },
        "analysis": analysis,
    }
    payload = (json.dumps(output, allow_nan=False, indent=2) + "\n").encode()
    (batch / "analysis.json").write_bytes(payload)
    figures = batch / "figures"
    figures.mkdir(exist_ok=True)
    with plt.rc_context(STYLE):
        paths = [
            figure_primary(analysis, figures, len(protocol_seeds(protocol))),
            figure_rmse(recomputed, protocol, figures),
            figure_planning(analysis, protocol, figures),
            figure_warnings(analysis, figures, target),
        ]
        if milestone == "m6":
            paths += [figure_blocks(analysis, figures), figure_mismatch(analysis, figures)]
        else:
            paths += [figure_usv_blocks(analysis, figures)]
    hashes = {"analysis.json": hashlib.sha256(payload).hexdigest()}
    hashes.update({f"figures/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (batch / "report_manifest.json").write_bytes((json.dumps(hashes, indent=2) + "\n").encode())
    for scenario, entry in analysis["main"].items():
        primary = entry["primary"]
        print(
            f"{scenario:13s} P-B3 dRMSE mean {primary['mean']:+.4f} "
            f"[{primary['ci_low']:+.4f}, {primary['ci_high']:+.4f}] "
            f"P better {primary['negative']} / tie {primary['ties']} / B3 better "
            f"{primary['positive']} (excluded {primary['excluded_failed_pairs']})",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
