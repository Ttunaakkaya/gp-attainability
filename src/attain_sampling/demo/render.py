"""Figures and a short video rendered solely from recorded simulation data."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

import imageio.v2 as imageio

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "fieldwork-matplotlib"))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

METHOD_LABELS = {
    "sweep": "Lawnmower sweep",
    "greedy": "Nominal greedy",
    "adaptive": "B2 execution-aware greedy",
    "dp": "B3 periodic DP",
    "p": "P execution-aware",
}
METHOD_COLORS = {
    "sweep": "#a7b3cd",
    "greedy": "#ffbc78",
    "adaptive": "#40d8c7",
    "dp": "#b7a0f5",
    "p": "#e8c25a",
}
PLANNING_METHODS = ("dp", "p")
ROBOT_COLORS = ("#57e1d0", "#ffb578", "#bb9aff", "#89c6ff")
STYLE: dict[Any, Any] = {
    "figure.facecolor": "#101825",
    "axes.facecolor": "#162233",
    "axes.edgecolor": "#506077",
    "axes.labelcolor": "#dce5ef",
    "text.color": "#edf2f8",
    "xtick.color": "#a3b1c4",
    "ytick.color": "#a3b1c4",
    "grid.color": "#344357",
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "savefig.facecolor": "#101825",
}


def load_comparison(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not value.get("runs"):
        raise ValueError("expected a schema-v1 comparison with recorded runs")
    return value


def _recorded_end(run: dict[str, Any]) -> float:
    """Use actual records, never a requested horizon, for the replay endpoint."""
    records = run.get("motion") or run["frames"]
    return float(records[-1]["time_s"])


def _failed(run: dict[str, Any]) -> bool:
    # Schema-v1 artifacts predating M1 recorded completed missions only.
    return bool(run.get("status", "failed" if run.get("failure") else "completed") != "completed")


def _run_label(run: dict[str, Any]) -> str:
    label = METHOD_LABELS[run["method"]]
    if _failed(run):
        label += f" [FAILED @ {_recorded_end(run):g} s]"
    return label


def _replay_state(
    run: dict[str, Any], moment: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select recorded prefixes; a failed mission never gets synthetic padding."""
    moment = min(moment, _recorded_end(run))
    frames = [frame for frame in run["frames"] if frame["time_s"] <= moment + 1e-8]
    records = run.get("motion") or run["frames"]
    motions = [move for move in records if move["time_s"] <= moment + 1e-8]
    return frames or [run["frames"][0]], motions or [records[0]]


def _replay_plan(run: dict[str, Any], moment: float) -> dict[str, Any] | None:
    """Return only a plan already known at the recorded cursor, without lookahead."""
    cursor = min(moment, _recorded_end(run))
    eligible = [plan for plan in run.get("plans", []) if plan["generated_at_s"] <= cursor + 1e-8]
    if not eligible:
        return None
    # An arriving motion can reference the previous plan at the update epoch.
    return cast(dict[str, Any], max(eligible, key=lambda plan: plan["generated_at_s"]))


def render_figures(comparison: dict[str, Any], destination: Path) -> list[Path]:
    paths = [destination / "comparison.png", destination / "final_maps.png"]
    if any(path.exists() for path in paths):
        raise FileExistsError("figure export already exists; choose a new destination")
    destination.mkdir(parents=True, exist_ok=True)
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(2, 2, figsize=(12.8, 8), layout="constrained")
        specifications = (
            ("rmse", "Field RMSE", "field units"),
            ("mean_variance", "Mean latent variance", "field units squared"),
            ("path_length", "Executed fleet path length", "m"),
            ("samples_received", "Successful measurements", "count"),
        )
        for ax, (metric, title, units) in zip(axes.flat, specifications, strict=True):
            for run in comparison["runs"]:
                frames = run["frames"]
                ax.plot(
                    [frame["time_s"] for frame in frames],
                    [frame[metric] for frame in frames],
                    color=METHOD_COLORS[run["method"]],
                    label=_run_label(run),
                    linewidth=2,
                )
            ax.set(title=title, xlabel="Simulation time (s)", ylabel=units)
            ax.grid(alpha=0.5)
        axes[0, 0].legend(fontsize=9)
        fig.suptitle(
            f"GP Mapping Lab | {comparison['scenario']} | seed {comparison['config']['seed']}\n"
            "Paired independent simulation — failed curves end at the last recorded state",
            fontsize=14,
        )
        fig.savefig(paths[0], dpi=130)
        plt.close(fig)

        row_count = len(comparison["runs"])
        fig, axes = plt.subplots(row_count, 4, figsize=(15, max(6, 3 * row_count)), squeeze=False)
        truth = np.asarray(comparison["runs"][0]["field"]["truth"])
        value_min, value_max = float(truth.min()), float(truth.max())
        error_max = max(
            float(np.max(np.abs(run["frames"][-1]["error"]))) for run in comparison["runs"]
        )
        std_max = comparison["config"]["signal_variance"] ** 0.5
        for row, run in enumerate(comparison["runs"]):
            frame = run["frames"][-1]
            extent = (0, run["config"]["domain"][0], 0, run["config"]["domain"][1])
            for column, (values, title, cmap, lower, upper) in enumerate(
                (
                    (truth, "True field", "viridis", value_min, value_max),
                    (frame["mean"], "Posterior mean", "viridis", value_min, value_max),
                    (frame["std"], "Latent standard deviation", "magma", 0, std_max),
                    (np.abs(frame["error"]), "Absolute error", "inferno", 0, error_max),
                )
            ):
                ax = axes[row, column]
                im = ax.imshow(
                    values, origin="lower", extent=extent, cmap=cmap, vmin=lower, vmax=upper
                )
                if row == 0:
                    ax.set_title(title)
                for robot in range(run["config"]["robot_count"]):
                    route = np.asarray(
                        [
                            motion["positions"][robot]
                            for motion in (run.get("motion") or run["frames"])
                        ]
                    )
                    ax.plot(route[:, 0], route[:, 1], color=ROBOT_COLORS[robot], lw=1.3)
                    ax.scatter(*route[-1], color=ROBOT_COLORS[robot], s=30, edgecolors="#102030")
                ax.set(xlabel="x (m)", ylabel="y (m)")
                if column == 0:
                    ax.set_ylabel(_run_label(run) + "\ny (m)", fontsize=9)
                fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
        fig.suptitle(
            "Last recorded mapping states | failed missions are partial, not final scores",
            fontsize=14,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.savefig(paths[1], dpi=110)
        plt.close(fig)
    return paths


def render_video(
    comparison: dict[str, Any], output: Path, *, seconds: float = 30, fps: int = 12
) -> Path:
    if seconds <= 0 or not np.isfinite(seconds) or not 1 <= fps <= 60:
        raise ValueError("video duration must be finite/positive and fps in [1,60]")
    if int(seconds * fps) < 1:
        raise ValueError("video must contain at least one frame")
    if output.exists():
        raise FileExistsError(f"video already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    runs = comparison["runs"]
    replay_end = max(_recorded_end(run) for run in runs)
    times = np.linspace(0, replay_end, int(seconds * fps))
    with plt.rc_context(STYLE):
        fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
        columns = max(2, len(runs))
        grid = fig.add_gridspec(2, columns, height_ratios=(2, 1), hspace=0.42, wspace=0.35)
        maps = [
            fig.add_subplot(grid[0, :] if len(runs) == 1 else grid[0, i]) for i in range(len(runs))
        ]
        chart = fig.add_subplot(grid[1, : columns - 1])
        score = fig.add_subplot(grid[1, columns - 1])
        score.axis("off")
        curves = []
        images = []
        routes: list[list[Any]] = []
        markers: list[list[Any]] = []
        plan_routes: list[list[Any]] = []
        titles = []
        for ax, run in zip(maps, runs, strict=True):
            extent = (0, run["config"]["domain"][0], 0, run["config"]["domain"][1])
            images.append(
                ax.imshow(
                    run["frames"][0]["std"],
                    extent=extent,
                    origin="lower",
                    cmap="magma",
                    vmin=0,
                    vmax=comparison["config"]["signal_variance"] ** 0.5,
                )
            )
            titles.append(
                ax.set_title(METHOD_LABELS[run["method"]], fontsize=9 if len(runs) >= 4 else 11)
            )
            ax.set(xlabel="x (m)", ylabel="y (m)")
            lines, dots, planned_lines = [], [], []
            for robot in range(run["config"]["robot_count"]):
                (line,) = ax.plot([], [], color=ROBOT_COLORS[robot], lw=1.7)
                (dot,) = ax.plot([], [], "o", color=ROBOT_COLORS[robot], ms=7, mec="#101825")
                lines.append(line)
                dots.append(dot)
                (planned_line,) = ax.plot(
                    [], [], color=ROBOT_COLORS[robot], lw=1, ls=":", alpha=0.65
                )
                planned_lines.append(planned_line)
            routes.append(lines)
            markers.append(dots)
            plan_routes.append(planned_lines)
            (curve,) = chart.plot(
                [], [], color=METHOD_COLORS[run["method"]], lw=2, label=_run_label(run)
            )
            curves.append(curve)
        chart.set(
            xlabel="Simulation time (s)",
            ylabel="Field RMSE",
            xlim=(0, max(1.0, replay_end)),
            ylim=(0, max(1e-8, max(f["rmse"] for r in runs for f in r["frames"])) * 1.12),
        )
        chart.grid(alpha=0.5)
        chart.legend(fontsize=8, loc="upper right")
        cursor = chart.axvline(0, color="#697c91", lw=1)
        heading = fig.suptitle("GP MAPPING LAB", fontsize=20, x=0.07, ha="left", y=0.98)
        fig.text(
            0.07,
            0.925,
            "Latent std: dark = 0, light = "
            f"{comparison['config']['signal_variance'] ** 0.5:g}"
            " · actual robot tracks · paired noise and dropout",
            color="#a3b1c4",
            fontsize=10,
        )
        fig.text(
            0.07,
            0.015,
            "Independent synthetic simulation | "
            + (
                "SOGP approximate posterior"
                if comparison["config"].get("gp_backend") == "sogp"
                else "fixed exact GP"
            )
            + " | no physical safety certificate"
            + (
                " | planner dotted paths: commanded cells, not guaranteed arrivals"
                if any(r["method"] in PLANNING_METHODS for r in runs)
                else ""
            ),
            color="#a3b1c4",
            fontsize=9,
        )
        readout = score.text(
            0, 1, "", va="top", fontsize=8 if len(runs) >= 4 else 9, linespacing=1.15
        )
        fig.subplots_adjust(top=0.84, bottom=0.12, left=0.07, right=0.97)
        with imageio.get_writer(
            str(output), fps=fps, codec="libx264", macro_block_size=16
        ) as raw_writer:
            writer = cast(Any, raw_writer)
            for moment in times:
                rows = []
                for i, run in enumerate(runs):
                    frames, motions = _replay_state(run, moment)
                    frame = frames[-1]
                    images[i].set_data(frame["std"])
                    plan = _replay_plan(run, moment) if run["method"] in PLANNING_METHODS else None
                    for robot in range(run["config"]["robot_count"]):
                        route = np.asarray([move["positions"][robot] for move in motions])
                        routes[i][robot].set_data(route[:, 0], route[:, 1])
                        markers[i][robot].set_data([route[-1, 0]], [route[-1, 1]])
                        if plan is not None:
                            _, anchors = _replay_state(run, plan["generated_at_s"])
                            starts = (
                                plan.get("start_positions")
                                or plan.get("starts")
                                or anchors[-1]["positions"]
                            )
                            planned_route = np.asarray(
                                [starts[robot]]
                                + [targets[robot] for targets in plan["targets_by_epoch"]]
                            )
                            plan_routes[i][robot].set_data(planned_route[:, 0], planned_route[:, 1])
                        else:
                            plan_routes[i][robot].set_data([], [])
                    curves[i].set_data([f["time_s"] for f in frames], [f["rmse"] for f in frames])
                    reached_end = moment >= _recorded_end(run) - 1e-8
                    state_note = (
                        f"FAILED @ {_recorded_end(run):g} s · partial"
                        if _failed(run) and reached_end
                        else f"Mean var {frame['mean_variance']:.3f} · "
                        f"samples {frame['samples_received']}"
                    )
                    titles[i].set_text(f"{METHOD_LABELS[run['method']]}\n{state_note}")
                    outcome = " [partial]" if _failed(run) and reached_end else ""
                    rows.append(
                        f"{METHOD_LABELS[run['method']]}\n"
                        f"RMSE {frame['rmse']:.3f}   path {frame['path_length']:.0f} m{outcome}"
                    )
                    if plan is not None:
                        rows[-1] += (
                            f"\nPlan {plan.get('plan_version', plan['plan_id'])} @ "
                            f"{plan['generated_at_s']:g} s; end {plan['mission_end_s']:g} s"
                        )
                cursor.set_xdata([moment, moment])
                heading.set_text(f"GP MAPPING LAB    /    {moment:05.1f} s")
                readout.set_text(
                    f"{comparison['scenario'].upper()} · SEED {comparison['config']['seed']}"
                    f"\n{comparison['config']['model'].upper()}\n\n" + "\n".join(rows)
                )
                fig.canvas.draw()
                writer.append_data(np.asarray(cast(Any, fig.canvas).buffer_rgba())[:, :, :3])
        plt.close(fig)
    return output
