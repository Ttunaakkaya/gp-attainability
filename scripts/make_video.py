"""M8 presentation video: about 100 s rendered only from recorded runs and result figures.

Sequence: a title card, the four guided showcases replayed from their pinned recordings
(``scripts/make_showcases.py``), the held-out result figures (``scripts/figures_m8.py``)
and a closing card. Every caption is either a showcase card's text, which that script
computed from the recording, or a number read here from the frozen analyses. Nothing is
simulated here.

Usage::

    python scripts/make_video.py                    # outputs/m8/FIELDWORK_m8_demo.mp4
    python scripts/make_video.py --fps 10 --output some.mp4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import textwrap
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOWCASES = ROOT / "outputs" / "showcases"
FIGURES = ROOT / "reports" / "figures" / "m8"
ANALYSES = {
    "m6": ROOT / "outputs/m6-20260916/heldout/batch-20260916T224142922453Z-609588/analysis.json",
    "m7v2": ROOT
    / "outputs/m7v2-20260917/heldout/batch-20260917T152510157339Z-7f95f2/analysis.json",
}
# The dashboard's dark palette, so the video looks like the demo it introduces.
BG = "#101a24"
PANEL = "#16232e"
TEXT = "#edf2f1"
MUTED = "#91a3af"
FAINT = "#6f8696"
AMBER = "#e8c25a"
NAMES = {
    "sweep": "B0 sweep",
    "greedy": "B1 nominal greedy",
    "adaptive": "B2 adaptive greedy",
    "dp": "B3 periodic DP",
    "p": "P execution-aware",
}
COLORS = {"dp": "#b7a0f5", "p": AMBER, "adaptive": "#5bd8bb"}
ROBOTS = ("#ffdf94", "#c3a5f0", "#8de8e5", "#ffa29c")
UNCERTAINTY = LinearSegmentedColormap.from_list(
    "std", [(29 / 255, 36 / 255, 66 / 255), (71 / 255, 62 / 255, 110 / 255),
            (135 / 255, 86 / 255, 130 / 255), (205 / 255, 126 / 255, 135 / 255),
            (1.0, 219 / 255, 175 / 255)]
)  # fmt: skip
WIDTH, HEIGHT, DPI = 12.8, 7.2, 100


def _load_showcases() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    manifest = json.loads((SHOWCASES / "showcases.json").read_text(encoding="utf-8"))
    loaded = []
    for entry in manifest["showcases"]:
        data = (SHOWCASES / entry["comparison"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit(f"showcase {entry['id']} no longer matches its manifest")
        loaded.append((entry, json.loads(data)))
    return loaded


def _at(items: list[dict[str, Any]], moment: float) -> int:
    index = 0
    for position, item in enumerate(items):
        if item["time_s"] <= moment + 1e-8:
            index = position
    return index


def _arc_points(start: np.ndarray, heading: float, length: float, curvature: float) -> list:
    points = []
    for step in range(1, 13):
        part = length * step / 12
        half = 0.5 * curvature * part
        chord = part * (math.sin(half) / half if abs(half) > 1e-12 else 1.0)
        points.append(
            start + chord * np.array([math.cos(heading + half), math.sin(heading + half)])
        )
    return points


def _plan_route(run: dict[str, Any], plan: dict[str, Any], robot: int) -> np.ndarray:
    """The plan as flown: exact primitive arcs on the USV, straight segments otherwise."""
    anchor = np.asarray((plan.get("start_positions") or plan["starts"])[robot], dtype=float)
    targets = [np.asarray(t[robot], dtype=float) for t in plan.get("targets_by_epoch") or []]
    config = run["config"]
    if config["model"] != "usv_curvature":
        return np.asarray([anchor, *targets])
    radius = config["max_speed"] / config["max_turn_rate"]
    heading = (plan.get("start_headings") or [None] * (robot + 1))[robot]
    if heading is None:
        records = [m for m in run["motion"] if m["time_s"] <= plan["generated_at_s"] + 1e-8]
        pose = records[-1] if records else None
        if (
            pose is not None
            and np.linalg.norm(np.asarray(pose["positions"][robot]) - anchor) < 1e-6
        ):
            heading = pose["headings"][robot]
    points, position, previous = [anchor], anchor, plan["generated_at_s"]
    for target, time in zip(targets, plan["sample_times_s"], strict=False):
        match = None
        if heading is not None:
            budget = config["max_speed"] * (time - previous)
            for fraction in (1.0, 0.5, 0.0):
                for turn in (1.0, 0.0, -1.0):
                    length, curvature = fraction * budget, turn / radius
                    end = _arc_points(position, heading, length, curvature)[-1]
                    if match is None and np.linalg.norm(end - target) < 1e-3:
                        match = (length, curvature)
        if match is not None:
            points += _arc_points(position, heading, *match)
            heading += match[1] * match[0]
        else:
            points.append(target)
            heading = None
        position, previous = target, time
    return np.asarray(points)


def _plan_at(run: dict[str, Any], moment: float) -> dict[str, Any] | None:
    known = [plan for plan in run.get("plans", []) if plan["generated_at_s"] <= moment + 1e-8]
    return max(known, key=lambda plan: plan["generated_at_s"]) if known else None


def draw_map(axis: Any, run: dict[str, Any], moment: float, title: str) -> None:
    """One recorded map at one moment: uncertainty, tracks, samples, plan in force."""
    config = run["config"]
    width, height = config["domain"]
    frame = run["frames"][_at(run["frames"], moment)]
    motions = [m for m in run["motion"] if m["time_s"] <= moment + 1e-8] or run["motion"][:1]
    axis.imshow(
        frame["std"],
        extent=(0, width, 0, height),
        origin="lower",
        cmap=UNCERTAINTY,
        vmin=0,
        vmax=config["signal_variance"] ** 0.5,
        interpolation="bilinear",
    )
    plan = _plan_at(run, moment) if run["method"] in ("dp", "p") else None
    control = (
        run["controls"][motions[-1]["control_event_index"]]
        if motions[-1].get("control_event_index") is not None
        else {}
    )
    for robot in range(config["robot_count"]):
        color = ROBOTS[robot % len(ROBOTS)]
        track = np.asarray([m["positions"][robot] for m in motions])
        if plan is not None:
            route = _plan_route(run, plan, robot)
            axis.plot(route[:, 0], route[:, 1], color=color, lw=1.1, ls=(0, (1.5, 2.5)), alpha=0.8)
            for epoch, time in enumerate(plan["sample_times_s"]):
                if time <= moment + 1e-8:
                    continue
                target = plan["targets_by_epoch"][epoch][robot]
                axis.plot(*target, "s", ms=4.5, mfc="none", mec=color, mew=1)
                if run["method"] == "p" and plan.get("predicted_sample_sites"):
                    site = plan["predicted_sample_sites"][epoch][robot]
                    axis.plot(*site, "o", ms=5, mfc="none", mec=color, mew=1.2)
        axis.plot(track[:, 0], track[:, 1], color=color, lw=1.8)
        axis.plot(track[-1, 0], track[-1, 1], "o", ms=8, color=PANEL, mec=color, mew=1.8)
        if (control.get("loitering") or [False] * 4)[robot]:
            axis.add_patch(
                plt.Circle(track[-1], 2.4, fill=False, ec="#d8e6e3", lw=1, ls=(0, (2, 2)))
            )
    seen = [
        s
        for s in run["samples"]
        if s["time_s"] <= moment + 1e-8 and s.get("actual_position") is not None
    ]
    received = [s for s in seen if s["received"]]
    lost = np.asarray([s["actual_position"] for s in seen if not s["received"]]).reshape(-1, 2)
    if received:
        points = np.asarray([s["actual_position"] for s in received])
        colors = [ROBOTS[s["robot_id"] % len(ROBOTS)] for s in received]
        axis.scatter(points[:, 0], points[:, 1], s=7, c=colors, alpha=0.85, linewidths=0)
    axis.scatter(lost[:, 0], lost[:, 1], s=26, marker="x", c="#ffb298", linewidths=1.3)
    axis.set_xlim(0, width)
    axis.set_ylim(0, height)
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_color("#2a3a47")
    color = COLORS.get(run["method"], TEXT)
    axis.set_title(
        f"{title}   ·   RMSE {frame['rmse']:.3f}   ·   {frame['samples_received']} samples",
        color=color,
        fontsize=12,
        loc="left",
        pad=6,
    )


def _canvas() -> tuple[Any, Any]:
    figure = plt.figure(figsize=(WIDTH, HEIGHT), dpi=DPI, facecolor=BG)
    return figure, figure.canvas


def _frame(figure: Any) -> np.ndarray:
    figure.canvas.draw()
    image = np.asarray(figure.canvas.buffer_rgba())[:, :, :3].copy()
    plt.close(figure)
    return image


def _wrap(text: str, width: int = 118) -> str:
    return "\n".join(textwrap.wrap(text, width))


def card(title: str, lines: list[str], kicker: str = "") -> np.ndarray:
    figure, _ = _canvas()
    if kicker:
        figure.text(0.07, 0.80, kicker, color=AMBER, fontsize=13, weight="bold")
    figure.text(0.07, 0.72, _wrap(title, 52), color=TEXT, fontsize=30, va="top", linespacing=1.2)
    y = 0.50
    for line in lines:
        wrapped = _wrap(line, 95)
        figure.text(0.07, y, wrapped, color=MUTED, fontsize=15, va="top", linespacing=1.4)
        y -= 0.048 * len(wrapped.splitlines()) + 0.035
    return _frame(figure)


def showcase_frame(
    index: int, entry: dict[str, Any], comparison: dict[str, Any], moment: float, caption: str
) -> np.ndarray:
    runs = {run["method"]: run for run in comparison["runs"]}
    shown = ["dp", "p"] if entry["compare"] else [entry["focus"]]
    figure, _ = _canvas()
    figure.text(
        0.035,
        0.955,
        f"SHOWCASE {index + 1} OF 4  ·  DEVELOPMENT SEED {entry['config']['seed']}  ·  "
        "AN ILLUSTRATION, NOT EVIDENCE",
        color=AMBER,
        fontsize=10.5,
        weight="bold",
    )
    figure.text(0.035, 0.905, entry["title"], color=TEXT, fontsize=21)
    figure.text(
        0.965,
        0.905,
        f"t = {moment:4.1f} s of {comparison['config']['duration_s']:.0f} s",
        color=MUTED,
        fontsize=14,
        ha="right",
    )
    if len(shown) == 2:
        axes = [
            figure.add_axes((0.035, 0.25, 0.455, 0.6)),
            figure.add_axes((0.51, 0.25, 0.455, 0.6)),
        ]
    else:
        axes = [figure.add_axes((0.2, 0.25, 0.6, 0.6))]
    for axis, method in zip(axes, shown, strict=True):
        axis.set_facecolor(PANEL)
        draw_map(axis, runs[method], moment, NAMES[method])
    figure.text(
        0.035,
        0.205,
        "background: remaining uncertainty (dark = low)  ·  solid: actual tracks  ·  dotted: plan "
        "in force  ·  squares: commanded cells  ·  circles: P's rollout  ·  x: lost sample",
        color=FAINT,
        fontsize=9.5,
    )
    figure.text(
        0.035, 0.165, _wrap(caption, 128), color=TEXT, fontsize=13.5, va="top", linespacing=1.4
    )
    return _frame(figure)


def figure_frame(path: Path, title: str, caption: str) -> np.ndarray:
    figure, _ = _canvas()
    figure.text(0.035, 0.94, "HELD-OUT RESULTS  ·  FROZEN PROTOCOLS, 40 UNSEEN TASKS PER BLOCK",
                color=AMBER, fontsize=10.5, weight="bold")  # fmt: skip
    figure.text(0.035, 0.89, title, color=TEXT, fontsize=20)
    image = plt.imread(path)
    axis = figure.add_axes((0.035, 0.17, 0.93, 0.68))
    axis.imshow(image)
    axis.axis("off")
    figure.text(
        0.035, 0.12, _wrap(caption, 130), color=TEXT, fontsize=13.5, va="top", linespacing=1.4
    )
    return _frame(figure)


def _numbers() -> dict[str, Any]:
    main = {
        k: json.loads(p.read_text(encoding="utf-8"))["analysis"]["main"]
        for k, p in ANALYSES.items()
    }
    blocks = [main[k][s]["primary"] for k in main for s in main[k]]
    tied = sum(b["ci_low"] <= 0 <= b["ci_high"] for b in blocks)
    ratios = [
        main[k][s]["methods"]["p"]["planning_s"]["median"]
        / main[k][s]["methods"]["dp"]["planning_s"]["median"]
        for k in main
        for s in main[k]
    ]
    return {"tied": tied, "blocks": len(blocks), "low": min(ratios), "high": max(ratios)}


def render(output: Path, fps: int) -> dict[str, Any]:
    showcases = _load_showcases()
    numbers = _numbers()
    writer = imageio.get_writer(str(output), fps=fps, codec="libx264", macro_block_size=16)
    seconds = 0.0

    def hold(image: np.ndarray, duration: float) -> None:
        nonlocal seconds
        for _ in range(max(1, round(duration * fps))):
            writer.append_data(image)
        seconds += duration

    try:
        hold(
            card(
                "Does tracking the gap between plan and execution help multi-robot GP mapping?",
                [
                    "An independent simulator: sparse online GP, Bellman planning and constrained "
                    "control, after Suenaga, Hanif, Uto and Hatanaka (ECC 2025).",
                    "Four recorded showcases, then the held-out results. Every number in this "
                    "video comes from a saved run.",
                ],
                "FIELDWORK  ·  M8",
            ),
            7,
        )
        replay = {"nominal": 12.0, "loss": 14.0, "usv": 14.0, "no_gain": 10.0}
        for index, (entry, comparison) in enumerate(showcases):
            duration = float(comparison["config"]["duration_s"])
            key = float(entry["key_time_s"])
            steps = max(2, round(replay[entry["id"]] * fps))
            for step in range(steps):
                moment = duration * step / (steps - 1)
                caption = " ".join(entry["look_for"][:2]) if moment < key else entry["key_moment"]
                image = showcase_frame(index, entry, comparison, moment, caption)
                writer.append_data(image)
                seconds += 1 / fps
                if abs(moment - key) < duration / (steps - 1) / 2 and key < duration:
                    hold(showcase_frame(index, entry, comparison, key, entry["key_moment"]), 4)
            facts = "  ·  ".join(f"{label}: {value}" for label, value in entry["facts"][:2])
            hold(showcase_frame(index, entry, comparison, duration, facts), 3)
        hold(
            figure_frame(
                FIGURES / "01_primary_p_minus_b3.png",
                "P against the periodic replanner B3",
                f"The 95% interval of P − B3 includes zero in {numbers['tied']} of "
                f"{numbers['blocks']} blocks: no measurable map-error benefit, on either vehicle. "
                f"P plans {numbers['low']:.1f}–{numbers['high']:.0f} times longer than B3.",
            ),
            9,
        )
        hold(
            figure_frame(
                FIGURES / "05_comparator_defect.png",
                "A win that was a bug, caught in the raw records",
                "The first USV study favoured P. The comparator's planner stranded robots near "
                "the edges. Reported as run, fixed, and re-tested on new tasks: the advantage "
                "disappeared.",
            ),
            9,
        )
        hold(
            card(
                "What worked, and what did not",
                [
                    "Worked: rollout, retention and events lower the variance and the arrival "
                    "error on a turn-constrained boat.",
                    "Did not: field error, early warning of target misses, cost. The simple "
                    "adaptive greedy baseline was the strongest method.",
                    "Next: forecasts that expect lost measurements. Code, protocols, raw "
                    "records and this video are reproducible from the repository.",
                ],
                "SUMMARY",
            ),
            8,
        )
    finally:
        writer.close()
    return {"seconds": round(seconds, 1), "fps": fps, **numbers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output", type=Path, default=ROOT / "outputs" / "m8" / "FIELDWORK_m8_demo.mp4"
    )
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({"font.family": ["Segoe UI", "DejaVu Sans"], "savefig.facecolor": BG}):
        summary = render(args.output, args.fps)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    record = {
        **summary,
        "video": args.output.name,
        "sha256": digest,
        "showcases": json.loads((SHOWCASES / "showcases.json").read_text(encoding="utf-8"))[
            "generated_at"
        ],
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{args.output} · {summary['seconds']} s at {args.fps} fps")


if __name__ == "__main__":
    main()
