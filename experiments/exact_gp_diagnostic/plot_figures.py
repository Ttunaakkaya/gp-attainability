"""Optional standard scientific plots. Requires Matplotlib; core does not.

Run diagnostic.py first, then: python plot_figures.py
Reads persisted CSV/JSON; never reruns or changes experiments.
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
plt.rcParams.update({"font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
                     "svg.fonttype": "none", "savefig.facecolor": "white"})
COLORS = ["#0072B2", "#D55E00", "#009E73"]


def save(fig, name):
    fig.savefig(ROOT / f"{name}.png", dpi=180, bbox_inches="tight")
    fig.savefig(ROOT / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def repeated_plot():
    with (ROOT / "repeated_samples.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    x = np.asarray([int(row["observations"]) for row in rows])
    fig, ax = plt.subplots(figsize=(8.4, 4.6), layout="constrained")
    for column, label, color in [("latent_variance", "Latent posterior variance", COLORS[0]),
                                  ("predictive_variance", "Observation-predictive variance", COLORS[1])]:
        ax.plot(x, [float(row[column]) for row in rows], "o-", ms=4, label=label, color=color)
    ax.axhline(0.25, color="#6d7278", lw=1.1, ls="--", label="Fixed observation-noise variance = 0.25")
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlim(0, int(x.max()))
    ax.set(xlabel="Independent observations at the same point (symlog scale)",
           ylabel="Variance", title="Noisy repeated sampling: latent and predictive uncertainty differ")
    ax.grid(alpha=0.22)
    ax.legend(loc="upper right", fontsize=9)
    save(fig, "repeated_variance")


def stress_plot(metrics):
    stress = metrics["missed_sample_stress"]
    x = np.arange(len(stress["planned_curve"]))
    fig, ax = plt.subplots(figsize=(8.4, 4.9), layout="constrained")
    for values, label, color, style in [
        (stress["planned_curve"], "Original exact-optimal plan: all 8 new samples", COLORS[0], "o-"),
        (stress["continue_original_route_after_miss_curve"], "Miss first robot's first sample; continue original route", COLORS[1], "s--"),
        (stress["replanned_curve"], "Same miss; recompute exact best remaining route", COLORS[2], "^-.")]:
        ax.plot(x, values, style, color=color, ms=5, label=label)
    ax.axvline(1, color="#6d7278", lw=1, ls=":")
    ax.text(1.06, 0.66, "One sample missed\nPositions unchanged", fontsize=9, va="top")
    ax.annotate(f"Original target: {stress['original_terminal_target']:.5f}\nBest after miss: {stress['best_remaining_terminal_variance']:.5f}",
                xy=(4, stress["best_remaining_terminal_variance"]), xytext=(2.35, 0.39), fontsize=9,
                arrowprops={"arrowstyle": "->", "color": "#555555"})
    ax.set(xlabel="Sampling step", ylabel="Mean latent posterior variance over 7 nodes",
           title="An executable prefix reference becomes stale after one missed sample", xticks=x)
    ax.grid(alpha=0.22)
    ax.legend(loc="upper right", fontsize=8.5)
    save(fig, "prefix_stress")


def robust_plot(metrics):
    audits = metrics["matched_dropout_audits"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), layout="constrained")
    x = np.arange(len(audits["nominal_optimum"]["prefix_envelope"]))
    for method, label, color, style in [("nominal_optimum", "Nominal-optimal route", COLORS[0], "o-"),
                                      ("greedy", "Greedy route", COLORS[1], "s--"),
                                      ("robust_optimum", "Min-max route (ties nominal)", COLORS[2], "^-.")]:
        audit = audits[method]
        axes[0].plot(x, audit["prefix_envelope"], style, color=color, label=label, ms=5)
        axes[1].plot(range(9), [scenario["prefix_variance"][-1] for scenario in audit["scenarios"]],
                     style, color=color, label=label, ms=5)
    axes[0].set(xlabel="Sampling step", ylabel="Worst mean latent variance",
                title="Envelope over all 9 allowed masks", xticks=x)
    axes[1].set(xlabel="Same missing-sample mask for each route", ylabel="Terminal mean latent variance",
                title="No min-max gain in this fixture", xticks=range(9))
    axes[1].set_xticklabels(["none", "1/r0", "1/r1", "2/r0", "2/r1", "3/r0", "3/r1", "4/r0", "4/r1"], rotation=45)
    for ax in axes:
        ax.grid(alpha=0.22)
    axes[0].legend(fontsize=8.5)
    fig.suptitle("Exact finite-set comparison: 3,211 routes x 9 no/one-miss masks", fontsize=13)
    save(fig, "robust_prefix_envelopes")


def main():
    metrics = json.loads((ROOT / "metrics.json").read_text(encoding="utf-8"))
    repeated_plot()
    stress_plot(metrics)
    robust_plot(metrics)
    print("Saved 3 scientific figures as PNG + SVG from existing numeric artifacts.")


if __name__ == "__main__":
    main()
