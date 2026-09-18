"""Figures for the ECC 2025 source profile, drawn only from recorded runs.

Each figure mirrors the *kind* of plot the paper shows (Figs. 2, 3, 4 and 6, pp. 307-311),
on this project's recorded ground truth and seed. They are qualitative companions to the
pre-declared criteria, never overlays on the paper's curves: the paper's seeds and field
are unpublished, so every figure carries that limit in its title.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fieldwork-matplotlib"))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

__all__ = ["render_ecc_pair", "render_ecc_summary"]

LABELS = {"constraint_only": "E0 constraint-only (10)", "hierarchical": "E1 hierarchical (17)"}
COLORS = {"constraint_only": "#c0392b", "hierarchical": "#1f6fb2"}
ROBOT_COLORS = ("#e67e22", "#16a085", "#8e44ad")
LIMIT = "project ground truth and seed; qualitative, not the paper's field"
STYLE: dict[Any, Any] = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.color": "#dddddd",
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "savefig.facecolor": "white",
}
SNAPSHOT_TIMES = ("320", "640", "1000")


def _check_pair(e0: Mapping[str, Any], e1: Mapping[str, Any]) -> None:
    if e0.get("profile") != "ecc2025" or e1.get("profile") != "ecc2025":
        raise ValueError("expected two ecc2025 profile records")
    if (e0.get("controller"), e1.get("controller")) != ("constraint_only", "hierarchical"):
        raise ValueError("expected the constraint-only run first and the hierarchical run second")
    keys = ("seed", "signal_variance", "start_center", "duration_s")
    if any(e0["config"][key] != e1["config"][key] for key in keys):
        raise ValueError("the two runs must share seed, scale, start and duration")


def _extent(run: Mapping[str, Any]) -> tuple[float, float, float, float]:
    left, right, bottom, top = run["paper_values"]["field_m"]
    return float(left), float(right), float(bottom), float(top)


def _grid(run: Mapping[str, Any], values: Sequence[float]) -> np.ndarray:
    count = round(len(values) ** 0.5)
    return np.asarray(values, dtype=np.float64).reshape(count, count)


def _field_box(axis: Any, run: Mapping[str, Any]) -> None:
    left, right, bottom, top = _extent(run)
    axis.plot([left, right, right, left, left], [bottom, bottom, top, top, bottom], "k-", lw=0.8)


def _trajectory_window(run: Mapping[str, Any], start: float, stop: float) -> np.ndarray:
    frames = [frame for frame in run["trajectory"] if start <= frame["time_s"] <= stop]
    if not frames:
        return np.empty((0, len(run["trajectory"][0]["positions"]), 2))
    return np.asarray([frame["positions"] for frame in frames], dtype=np.float64)


def _suffix(run: Mapping[str, Any]) -> str:
    config = run["config"]
    start = config["start_center"]
    return (
        f"seed {config['seed']}, k(x,x) = {config['signal_variance']:g}, "
        f"start ({start[0]:g}, {start[1]:g})"
    )


def _failed_note(run: Mapping[str, Any]) -> str:
    if run["status"] == "completed":
        return ""
    return f" [FAILED @ {run['completed_time_s']:g} s]"


def _trajectories(e0: Mapping[str, Any], e1: Mapping[str, Any], path: Path) -> None:
    left, right, bottom, top = _extent(e0)
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 5.2), constrained_layout=True)
    background = _grid(e0, e0["field"]["values"])
    for axis, run in zip(axes, (e0, e1), strict=True):
        image = axis.imshow(
            background,
            origin="lower",
            extent=(left, right, bottom, top),
            cmap="Greys",
            alpha=0.45,
        )
        _field_box(axis, run)
        for window, style, label in (
            ((0.0, 360.0), "-", "t in [0, 360] s"),
            ((640.0, 1000.0), "--", "t in [640, 1000] s"),
        ):
            path_xy = _trajectory_window(run, *window)
            width = 1.2 if style == "-" else 1.6
            for robot in range(path_xy.shape[1]):
                axis.plot(
                    path_xy[:, robot, 0],
                    path_xy[:, robot, 1],
                    style,
                    color=ROBOT_COLORS[robot % len(ROBOT_COLORS)],
                    lw=width,
                )
            # Legend proxy in neutral colour: line style encodes the window, colour the robot.
            axis.plot([], [], style, color="#333333", lw=width, label=label)
        starts = np.asarray(run["trajectory"][0]["positions"])
        ends = np.asarray(run["trajectory"][-1]["positions"])
        axis.scatter(starts[:, 0], starts[:, 1], marker="s", color="k", s=18, label="start")
        axis.scatter(ends[:, 0], ends[:, 1], marker="o", color="k", s=18, label="end")
        axis.set_xlim(left - 5, right + 5)
        axis.set_ylim(bottom - 5, max(top, float(starts[:, 1].max())) + 5)
        axis.set_aspect("equal")
        axis.set_title(LABELS[run["controller"]] + _failed_note(run))
        axis.set_xlabel("x [m]")
        axis.set_ylabel("y [m]")
        axis.legend(loc="lower right", fontsize=7)
    fig.colorbar(image, ax=axes, shrink=0.7, label="ground-truth field value")
    fig.suptitle(
        f"Executed paths (the paper shows them as sampled trails in Figs. 2 and 4a) — "
        f"{_suffix(e0)}\n{LIMIT}",
        fontsize=9,
    )
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _series(e0: Mapping[str, Any], e1: Mapping[str, Any], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.8), constrained_layout=True)
    reference = e0["epochs"]
    times = np.asarray([entry["time_s"] for entry in reference])
    line = np.maximum(np.asarray([entry["line"] for entry in reference]), 0.0)
    axes[0].plot(times, line, color="#555555", lw=1.0, ls=":", label="J[0] - l gamma, eq. (5)")
    for run in (e0, e1):
        epochs = run["epochs"]
        axes[0].plot(
            [entry["time_s"] for entry in epochs],
            [entry["J"] for entry in epochs],
            color=COLORS[run["controller"]],
            label=LABELS[run["controller"]] + _failed_note(run),
        )
        axes[1].semilogy(
            [entry["time_s"] for entry in epochs],
            [entry["mse"] for entry in epochs],
            color=COLORS[run["controller"]],
            label=LABELS[run["controller"]] + _failed_note(run),
        )
    axes[0].set_title("Objective J, cf. Figs. 3 and 6")
    axes[0].set_xlabel("t [s]")
    axes[0].set_ylabel("J = sum of latent variance on F_d")
    axes[0].set_ylim(bottom=0.0)
    axes[1].set_title("Mean-squared error on F_d, cf. Fig. 6")
    axes[1].set_xlabel("t [s]")
    axes[1].set_ylabel("MSE (log scale)")
    for axis in axes:
        axis.legend(fontsize=7)
    fig.suptitle(f"{_suffix(e0)} — {LIMIT}", fontsize=9)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _snapshots(e0: Mapping[str, Any], e1: Mapping[str, Any], path: Path) -> None:
    left, right, bottom, top = _extent(e0)
    signal = float(e0["config"]["signal_variance"])
    fig, axes = plt.subplots(2, 3, figsize=(10.0, 6.8), constrained_layout=True, squeeze=False)
    image = None
    for row, run in enumerate((e0, e1)):
        for column, moment in enumerate(SNAPSHOT_TIMES):
            axis = axes[row][column]
            axis.set_xlim(left, right)
            axis.set_ylim(bottom, top)
            axis.set_aspect("equal")
            axis.set_title(f"{LABELS[run['controller']]}, t = {moment} s", fontsize=8)
            snapshot = run["snapshots"].get(moment)
            if snapshot is None:
                axis.text(0.5, 0.5, "not reached", ha="center", transform=axis.transAxes)
                continue
            image = axis.imshow(
                _grid(run, snapshot["variance"]),
                origin="lower",
                extent=(left, right, bottom, top),
                cmap="viridis",
                vmin=0.0,
                vmax=signal,
            )
            basis = np.asarray(snapshot["basis"]).reshape(-1, 2)
            axis.scatter(basis[:, 0], basis[:, 1], s=2, color="white", alpha=0.6)
            robots = np.asarray(snapshot["positions"])
            axis.scatter(robots[:, 0], robots[:, 1], s=30, color="#e74c3c", edgecolor="k")
    if image is not None:
        fig.colorbar(image, ax=axes, shrink=0.6, label="latent variance")
    fig.suptitle(
        f"Posterior variance and dictionary, cf. Figs. 2 and 4a — {_suffix(e0)}\n{LIMIT}",
        fontsize=9,
    )
    fig.savefig(path, dpi=140)
    plt.close(fig)


def render_ecc_pair(
    e0: Mapping[str, Any], e1: Mapping[str, Any], destination: Path, stem: str
) -> list[Path]:
    """Render trajectory, objective/error and variance-snapshot figures for one pair."""
    _check_pair(e0, e1)
    destination.mkdir(parents=True, exist_ok=True)
    paths = [
        destination / f"{stem}_trajectories.png",
        destination / f"{stem}_objective_error.png",
        destination / f"{stem}_variance.png",
    ]
    with plt.rc_context(STYLE):
        _trajectories(e0, e1, paths[0])
        _series(e0, e1, paths[1])
        _snapshots(e0, e1, paths[2])
    return paths


def render_ecc_summary(validation: Mapping[str, Any], destination: Path) -> Path:
    """Paired final J and final MSE for every seed and configuration of a batch."""
    results = validation.get("results")
    if not results:
        raise ValueError("expected a validation record with results")
    names = list(dict.fromkeys(row["configuration"] for row in results))
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "summary_final_J_mse.png"
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(2, len(names), figsize=(3.0 * len(names), 5.6), squeeze=False)
        for column, name in enumerate(names):
            rows = [row for row in results if row["configuration"] == name]
            for row_index, (key, label) in enumerate(
                (("final_J", "final J"), ("final_mse", "final MSE"))
            ):
                axis = axes[row_index][column]
                for row in rows:
                    values = (row["E0"][key], row["E1"][key])
                    failed = bool(row.get("failed_runs"))
                    axis.plot((0, 1), values, color="#999999", lw=0.8, ls="--" if failed else "-")
                    axis.scatter(0, values[0], color=COLORS["constraint_only"], s=16, zorder=3)
                    axis.scatter(1, values[1], color=COLORS["hierarchical"], s=16, zorder=3)
                axis.set_xticks((0, 1), ("E0", "E1"))
                axis.set_xlim(-0.4, 1.4)
                highest = max(max(row["E0"][key], row["E1"][key]) for row in rows)
                axis.set_ylim(0.0, 1.08 * highest if highest > 0 else 1.0)
                axis.ticklabel_format(axis="y", useOffset=False, style="plain")
                if column == 0:
                    axis.set_ylabel(label)
                if row_index == 0:
                    axis.set_title(name.replace("_", " "), fontsize=8)
        fig.suptitle("Paired seeds per configuration (dashed: a run failed) — " + LIMIT, fontsize=9)
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
    return path
