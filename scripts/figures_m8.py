"""M8 figure set: the main comparison, ablations, cost and failures, from held-out batches.

Every figure is drawn from the frozen batches' ``analysis.json`` (recomputed from raw
records by ``report_m6.py``), except the comparator-defect counts, which this script
recomputes from the raw run files. No simulation runs here. The output folder gets a
``MANIFEST.json`` with the SHA-256 of every input and figure.

Usage::

    python scripts/figures_m8.py                       # default batches, reports/figures/m8
    python scripts/figures_m8.py --output some/folder
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BATCHES = {
    "m6": ROOT / "outputs/m6-20260916/heldout/batch-20260916T224142922453Z-609588",
    "m7v1": ROOT / "outputs/m7-20260917/heldout/batch-20260917T142113728110Z-8b2fe1",
    "m7v2": ROOT / "outputs/m7v2-20260917/heldout/batch-20260917T152510157339Z-7f95f2",
}
PLATFORMS = {"m6": "Holonomic robots · M6", "m7v2": "Turn-constrained USV · M7 v2"}
SCENARIOS = {
    "nominal": "Nominal",
    "dropout": "Measurement loss",
    "drift": "Tracking drift",
    "combined": "Loss + drift",
    "short_budget": "Short budget (45 s)",
}
VARIANTS = {
    "p_no_rollout": "No rollout",
    "p_no_retain": "No plan retention",
    "p_periodic_only": "Periodic decisions only",
}

# Reference palette (dataviz skill), light mode. Slots 1-3 validate all-pairs on this
# surface; aqua sits below 3:1, so every figure labels its marks and the note repeats
# the numbers in tables. B0 and B1 take ink with distinct marker shapes.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
METHODS: dict[str, dict[str, Any]] = {
    "sweep": {"label": "B0 sweep", "color": MUTED, "marker": "s"},
    "greedy": {"label": "B1 nominal greedy", "color": INK_2, "marker": "^"},
    "adaptive": {"label": "B2 adaptive greedy", "color": "#1baf7a", "marker": "o"},
    "dp": {"label": "B3 periodic DP", "color": "#2a78d6", "marker": "o"},
    "p": {"label": "P execution-aware", "color": "#eb6834", "marker": "o"},
}
P_COLOR = METHODS["p"]["color"]
B3_COLOR = METHODS["dp"]["color"]
STYLE: dict[Any, Any] = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 10,
    "axes.titleweight": "bold",
    "axes.labelsize": 9,
    "axes.grid": True,
    "axes.axisbelow": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _analysis(name: str) -> dict[str, Any]:
    data = json.loads((BATCHES[name] / "analysis.json").read_text(encoding="utf-8"))
    return dict(data["analysis"])


def _forest(axis: Any, rows: list[tuple[str, dict[str, Any]]], color: str, offset: float = 0.0):
    """Mean paired difference with its 95% interval, one row per label."""
    for index, (_, stats) in enumerate(rows):
        if stats.get("mean") is None:
            continue
        y = index + offset
        axis.plot([stats["ci_low"], stats["ci_high"]], [y, y], color=color, lw=2)
        axis.plot(stats["mean"], y, "o", color=color, ms=7, mec=SURFACE, mew=2, zorder=3)


def _rows(axis: Any, labels: list[str], *, zero: bool = True) -> None:
    axis.set_yticks(range(len(labels)), labels)
    axis.set_ylim(len(labels) - 0.5, -0.6)
    axis.grid(axis="y", visible=False)
    if zero:
        axis.axvline(0.0, color=AXIS, lw=1, zorder=1)


def _includes_zero(stats: dict[str, Any]) -> bool:
    return bool(stats["ci_low"] <= 0.0 <= stats["ci_high"])


def figure_primary(analyses: dict[str, dict[str, Any]], out: Path) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.2), sharey=True)
    for axis, name in zip(axes, PLATFORMS, strict=True):
        main = analyses[name]["main"]
        rows = [(SCENARIOS[s], main[s]["primary"]) for s in SCENARIOS]
        _forest(axis, rows, P_COLOR)
        for index, (_, stats) in enumerate(rows):
            axis.annotate(
                f"{stats['mean']:+.4f}",
                (stats["ci_high"], index),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                color=INK_2,
                fontsize=8,
            )
        _rows(axis, [label for label, _ in rows])
        axis.set_title(PLATFORMS[name], loc="left")
        axis.set_xlabel("P − B3 field RMSE  (negative: P better)")
        axis.margins(x=0.25)
    tied = sum(
        _includes_zero(analyses[name]["main"][s]["primary"])
        for name in PLATFORMS
        for s in SCENARIOS
    )
    figure.suptitle(
        f"P − B3 over 40 held-out tasks per block: the 95% interval includes zero in {tied} of "
        f"{len(PLATFORMS) * len(SCENARIOS)} blocks",
        x=0.01,
        ha="left",
        fontsize=10.5,
        color=INK,
    )
    figure.tight_layout()
    return _save(figure, out / "01_primary_p_minus_b3.png")


def _method_dots(axis: Any, main: dict[str, Any], metric: str, stat: str = "mean") -> None:
    offsets = dict(zip(METHODS, (-0.28, -0.14, 0.0, 0.14, 0.28), strict=True))
    for method, spec in METHODS.items():
        for index, scenario in enumerate(SCENARIOS):
            value = main[scenario]["methods"][method][metric][stat]
            axis.plot(
                value,
                index + offsets[method],
                spec["marker"],
                color=spec["color"],
                ms=6.5,
                mec=SURFACE,
                mew=1.2,
                zorder=3,
            )


def _method_legend(figure: Any) -> None:
    handles = [
        Line2D([], [], ls="", marker=s["marker"], color=s["color"], ms=7, label=s["label"])
        for s in METHODS.values()
    ]
    figure.legend(handles=handles, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.01))


def figure_methods(analyses: dict[str, dict[str, Any]], out: Path) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.6), sharey=True)
    for axis, name in zip(axes, PLATFORMS, strict=True):
        _method_dots(axis, analyses[name]["main"], "rmse")
        _rows(axis, list(SCENARIOS.values()), zero=False)
        axis.set_title(PLATFORMS[name], loc="left")
        axis.set_xlabel("Mean field RMSE, 40 tasks  (lower is better)")
    means = [
        {m: analyses[name]["main"][s]["methods"][m]["rmse"]["mean"] for m in METHODS}
        for name in PLATFORMS
        for s in SCENARIOS
    ]
    best = sum(block["adaptive"] <= min(block.values()) for block in means)
    figure.suptitle(
        f"All five methods: B2 adaptive greedy has the lowest (or tied lowest) mean error in "
        f"{best} of {len(means)} blocks",
        x=0.01,
        ha="left",
        fontsize=10.5,
    )
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    _method_legend(figure)
    return _save(figure, out / "02_methods_rmse.png")


def figure_ablations(analyses: dict[str, dict[str, Any]], out: Path) -> Path:
    figure, axes = plt.subplots(2, 2, figsize=(8.2, 4.4), sharey=True)
    for row, name in enumerate(PLATFORMS):
        ablation = analyses[name]["ablation"]
        for column, (metric, label) in enumerate(
            (("rmse", "field RMSE"), ("mean_variance", "mean variance"))
        ):
            axis = axes[row][column]
            rows = [(VARIANTS[v], ablation[v]["minus_full_p"][metric]) for v in VARIANTS]
            _forest(axis, rows, P_COLOR)
            _rows(axis, list(VARIANTS.values()))
            axis.set_title(f"{PLATFORMS[name]} · {label}", loc="left", fontsize=9.5)
            axis.xaxis.set_major_locator(MaxNLocator(5))
            axis.set_xlabel(f"Variant − full P, {label}  (positive: variant worse)")
    measurable = [
        f"{VARIANTS[v]} ({PLATFORMS[name].split(' · ')[1]})"
        for name in PLATFORMS
        for v in VARIANTS
        if not _includes_zero(analyses[name]["ablation"][v]["minus_full_p"]["rmse"])
    ]
    figure.suptitle(
        "Ablations on the combined scenario: "
        + (
            "no variant changes the field RMSE measurably"
            if not measurable
            else "measurable RMSE change only for " + ", ".join(measurable)
        ),
        x=0.01,
        ha="left",
        fontsize=10.5,
    )
    figure.tight_layout()
    return _save(figure, out / "03_ablations.png")


def figure_cost(analyses: dict[str, dict[str, Any]], out: Path) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.6), sharey=True)
    for axis, name in zip(axes, PLATFORMS, strict=True):
        _method_dots(axis, analyses[name]["main"], "planning_s", "median")
        _rows(axis, list(SCENARIOS.values()), zero=False)
        axis.set_xscale("log")
        axis.set_title(PLATFORMS[name], loc="left")
        axis.set_xlabel("Median planning time per 90 s mission, s  (log scale)")
    ratios = [
        analyses[name]["main"][s]["methods"]["p"]["planning_s"]["median"]
        / analyses[name]["main"][s]["methods"]["dp"]["planning_s"]["median"]
        for name in PLATFORMS
        for s in SCENARIOS
    ]
    figure.suptitle(
        f"Cost: P plans {min(ratios):.1f}–{max(ratios):.0f} times longer than B3 "
        "(median, wall-clock on a shared machine)",
        x=0.01,
        ha="left",
        fontsize=10.5,
    )
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    _method_legend(figure)
    return _save(figure, out / "04_planning_cost.png")


def _stopped_robots(path_text: str) -> dict[str, int]:
    """Robots of B3 and P that stop for good at least 30 s before mission end."""
    with gzip.open(path_text, "rb") as stream:
        comparison = json.loads(stream.read())
    counts = {}
    for run in comparison["runs"]:
        if run["method"] not in ("dp", "p"):
            continue
        executed = [event for event in run["controls"] if event["phase"] == "execution"]
        end = executed[-1]["time_s"] + 0.5
        stopped = 0
        for robot in range(len(executed[0]["requested_speeds"])):
            moving = [e["time_s"] for e in executed if e["requested_speeds"][robot] > 1e-6]
            last = moving[-1] + 0.5 if moving else 0.0
            stopped += end - last >= 30.0
        counts[run["method"]] = stopped
    return counts


def defect_counts(out: Path) -> dict[str, Any]:
    """Recomputed from raw runs; cached next to the figures with the input hashes."""
    cache = out / "stopped_robots.json"
    manifests = {v: _sha256(BATCHES[v] / "manifest.json") for v in ("m7v1", "m7v2")}
    if cache.is_file():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("inputs") == manifests:
            return dict(cached)
    scenarios = ("nominal", "dropout", "drift", "combined")
    jobs = []
    for version in ("m7v1", "m7v2"):
        records = json.loads((BATCHES[version] / "records.json").read_text(encoding="utf-8"))
        for record in records:
            if record["block"] == "main" and record["scenario"] in scenarios:
                jobs.append((version, record["scenario"], str(BATCHES[version] / record["file"])))
    with ProcessPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_stopped_robots, [path for _, _, path in jobs]))
    totals: dict[str, dict[str, dict[str, int]]] = {}
    for (version, scenario, _), counts in zip(jobs, results, strict=True):
        for method, count in counts.items():
            cell = totals.setdefault(version, {}).setdefault(scenario, {})
            cell[method] = cell.get(method, 0) + count
    value = {
        "definition": "robots whose requested speed stays zero for the last 30 s or more",
        "inputs": manifests,
        "counts": totals,
    }
    cache.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value


def figure_defect(analyses: dict[str, dict[str, Any]], counts: dict[str, Any], out: Path) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.3), gridspec_kw={"width_ratios": [1, 1.2]})
    scenarios = ("nominal", "dropout", "drift", "combined")
    axis = axes[0]
    for offset, method in ((-0.17, "dp"), (0.17, "p")):
        values = [counts["counts"]["m7v1"][s][method] for s in scenarios]
        spec = METHODS[method]
        axis.barh(
            [i + offset for i in range(len(scenarios))],
            values,
            height=0.3,
            color=spec["color"],
            edgecolor=SURFACE,
            linewidth=2,
            label=spec["label"].split(" ")[0] + " (v1 planner)",
        )
        for index, value in enumerate(values):
            axis.annotate(
                str(value),
                (value, index + offset),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                fontsize=8,
                color=INK_2,
            )
    v2 = sum(sum(cell.values()) for cell in counts["counts"]["m7v2"].values())
    axis.set_yticks(range(len(scenarios)), [SCENARIOS[s] for s in scenarios])
    axis.set_ylim(len(scenarios) - 0.5, -0.6)
    axis.grid(axis="y", visible=False)
    axis.set_xlabel("Robots stopped for good ≥ 30 s  (of 160)")
    axis.set_title("M7 v1: the defective planner strands robots", loc="left")
    axis.legend(loc="upper right", fontsize=8)
    axis.text(
        0.98,
        0.70,
        f"v2, corrected planner: {v2} in total",
        transform=axis.transAxes,
        ha="right",
        fontsize=8,
        color=INK_2,
    )
    axis.margins(x=0.15)
    axis = axes[1]
    rows = [(SCENARIOS[s], s) for s in SCENARIOS]
    _forest(
        axis, [(label, analyses["m7v1"]["main"][s]["primary"]) for label, s in rows], MUTED, -0.15
    )
    _forest(
        axis, [(label, analyses["m7v2"]["main"][s]["primary"]) for label, s in rows], P_COLOR, 0.15
    )
    _rows(axis, [label for label, _ in rows])
    axis.set_xlabel("P − B3 field RMSE  (negative: P better)")
    axis.set_title("The apparent P advantage disappears in v2", loc="left")
    axis.legend(
        handles=[
            Line2D([], [], color=MUTED, marker="o", label="v1, defective B3 (seeds 9101–9140)"),
            Line2D([], [], color=P_COLOR, marker="o", label="v2, corrected B3 (seeds 9201–9240)"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.45, -0.2),
        ncol=2,
        fontsize=8,
    )
    figure.suptitle(
        "A comparator defect found in the raw records, fixed, and confirmed on new tasks",
        x=0.01,
        ha="left",
        fontsize=10.5,
    )
    figure.tight_layout()
    return _save(figure, out / "05_comparator_defect.png")


def figure_forecast(analyses: dict[str, dict[str, Any]], out: Path) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.4), sharey=True)
    methods = ("adaptive", "dp", "p")
    for axis, name in zip(axes, PLATFORMS, strict=True):
        main = analyses[name]["main"]
        for method, offset in zip(methods, (-0.16, 0.0, 0.16), strict=True):
            spec = METHODS[method]
            for index, scenario in enumerate(SCENARIOS):
                value = main[scenario]["methods"][method]["one_step_forecast_error_mean"]["mean"]
                axis.plot(value, index + offset, "o", color=spec["color"], ms=6.5, mec=SURFACE)
        _rows(axis, list(SCENARIOS.values()))
        axis.set_title(PLATFORMS[name], loc="left")
        axis.set_xlabel("Realised − forecast mean variance, one epoch ahead")
    handles = [
        Line2D([], [], ls="", marker="o", color=METHODS[m]["color"], label=METHODS[m]["label"])
        for m in methods
    ]
    figure.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.01))
    figure.suptitle(
        "Forecasts turn optimistic when measurements are lost: they assume every sample arrives",
        x=0.01,
        ha="left",
        fontsize=10.5,
    )
    figure.tight_layout(rect=(0, 0.07, 1, 1))
    return _save(figure, out / "06_forecast_optimism.png")


def _save(figure: Any, path: Path) -> Path:
    figure.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "figures" / "m8")
    args = parser.parse_args()
    out: Path = args.output
    out.mkdir(parents=True, exist_ok=True)
    analyses = {name: _analysis(name) for name in BATCHES}
    counts = defect_counts(out)
    with plt.rc_context(STYLE):
        paths = [
            figure_primary(analyses, out),
            figure_methods(analyses, out),
            figure_ablations(analyses, out),
            figure_cost(analyses, out),
            figure_defect(analyses, counts, out),
            figure_forecast(analyses, out),
        ]
    manifest = {
        "inputs": {
            name: {
                "batch": batch.relative_to(ROOT).as_posix(),
                "analysis_sha256": _sha256(batch / "analysis.json"),
            }
            for name, batch in BATCHES.items()
        },
        "figures": {path.name: _sha256(path) for path in paths},
        "stopped_robots": {
            "file": "stopped_robots.json",
            "sha256": _sha256(out / "stopped_robots.json"),
        },
    }
    (out / "MANIFEST.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    for path in paths:
        print(path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
