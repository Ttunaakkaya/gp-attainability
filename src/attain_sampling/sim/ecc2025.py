"""ECC 2025 closed-loop source profile: constraint-only (E0) and hierarchical (E1).

Anchor: Suenaga, Hanif, Uto and Hatanaka, ECC 2025, pp. 304-311. This profile assembles
the audited pieces — the paper's SOGP (T03/T04), the decay-rate row (T01/T02/T05/T07), the
per-robot QP (T05/T06) and the cell Bellman planner (T08) — with the Table I values (T09),
and runs the two controllers the paper compares:

* **E0**, eq. (10): the constraint-only controller, ``u_nom = 0``. The paper reports that
  it drives the objective off the requested decay and lets a robot stall in a
  low-variance region while high-variance regions remain (Fig. 2, p. 307; text p. 308).
* **E1**, eq. (17) with Algorithm 1: the hierarchical controller, whose nominal input
  ``kappa (x_ci - p_i)`` follows cell waypoints from eq. (16). The paper reports a lower
  final objective and a mean-squared error that converges close to zero (p. 310, Fig. 6).

What this profile can claim
---------------------------
The paper publishes no random seeds and no ground-truth parameters, so its curves cannot
be matched numerically. This profile reproduces the *setup* from the text and compares
the two controllers *qualitatively* against pre-declared criteria. It never labels a run
as a numerical reproduction.

Readings and project choices
----------------------------
Every setting the paper does not state is chosen here, recorded in each result, and never
inferred from a neighbouring value:

* **Ground truth.** A sum of 40 Gaussian bumps (centres uniform on ``F``, widths 6-14 m,
  amplitudes 15-45), fixed before any controller was run so its value range resembles
  Fig. 4b; it is not the paper's field.
* **Evaluation set.** A 30 x 30 cell-centred grid on ``F`` (900 points, p. 308).
* **Start.** p. 310 says only that the robots start outside the field. The default puts
  three robots 5 m apart at the starting square ``(0, 75)`` read off Figs. 2 and 4a; those
  figures place the other robots nearer or on the top edge, so an edge start is run as a
  recorded sensitivity.
* **Clock.** Euler integration with ``dt = 0.1 s``; the first sample is at ``t_1 = t_s``
  because the paper indexes data from ``l = 1``; within one epoch robots are assimilated in
  index order.
* **Controller.** ``alpha_ca`` linear with gain 1, a 2 m/s speed polygon, no workspace
  constraint (see :mod:`attain_sampling.control.ecc_qp`).
* **I_i0.** The paper defines it at ``t = t_1``, but ``h_Ji`` is needed from ``t = 0``; it
  is evaluated once at the start. With ``alpha_J = 1e-4`` its effect on ``xi_i2`` is small.
* **Replanning.** The text (p. 309) and the timer input to the planner in Fig. 5
  recompute the path after every sample; Algorithm 1 (p. 310) only replans when the
  waypoint list is empty. The text is followed: each sample clears and recomputes the
  route; an exhausted route between samples is recomputed as in Algorithm 1.
* **Scale.** ``signal_variance = 1`` follows Theorem 1. Figs. 3 and 6 start at
  ``J[0] ~ 3600`` on 900 points, which requires ``k(x,x) ~ 4``; ``signal_variance = 4`` is
  offered as a recorded figure-scale sensitivity, with ``omega`` kept absolute.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

from attain_sampling.control.ecc_qp import EccQPSettings, solve_robot_qp
from attain_sampling.control.rate_constraint import (
    DecayConstraintRow,
    EpochDecayCache,
    voronoi_owner,
)
from attain_sampling.gp.protocol import FloatArray
from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.planning.cell_mdp import (
    CellRepresentatives,
    cell_representatives,
    plan_cell_route,
)
from attain_sampling.random import indexed_normal
from attain_sampling.sim.mapping import segment_min_separation
from attain_sampling.sources.ecc2025 import parameters, require_unlocked

__all__ = [
    "Controller",
    "EccProfileConfig",
    "ground_truth",
    "run_ecc_profile",
]

Controller = Literal["constraint_only", "hierarchical"]
CONTROLLERS: tuple[Controller, ...] = ("constraint_only", "hierarchical")


@dataclass(frozen=True, slots=True)
class EccProfileConfig:
    """One ECC profile run. Paper values come from the audited ledger, not from here."""

    controller: Controller
    seed: int = 7
    duration_s: float = 1000.0
    signal_variance: float = 1.0
    dt: float = 0.1
    max_speed: float = 2.0
    alpha_ca: float = 1.0
    polygon_sides: int = 16
    max_waypoints: int = 8
    grid_count: int = 30
    field_components: int = 40
    start_center: tuple[float, float] = (0.0, 75.0)
    start_spacing_m: float = 5.0
    trajectory_every_s: float = 1.0

    def __post_init__(self) -> None:
        if self.controller not in CONTROLLERS:
            raise ValueError(f"controller must be one of {CONTROLLERS}")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        for name in (
            "duration_s",
            "signal_variance",
            "dt",
            "max_speed",
            "alpha_ca",
            "start_spacing_m",
            "trajectory_every_s",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a real number")
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name, lower in (
            ("polygon_sides", 3),
            ("max_waypoints", 1),
            ("grid_count", 2),
            ("field_components", 1),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")
        period = float(parameters()["t_s"])
        for name, value in (("duration_s", self.duration_s), ("sample period", period)):
            ratio = float(value) / self.dt
            if not math.isclose(ratio, round(ratio), abs_tol=1e-9):
                raise ValueError(f"{name} must be an integer multiple of dt")
        if self.start_spacing_m < float(parameters()["d_ca"]):
            raise ValueError("start_spacing_m must respect the paper's d_ca")


def ground_truth(seed: int, components: int) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Return ``(centres, widths, amplitudes)`` of the recorded Gaussian-mixture field."""
    rng = np.random.default_rng([seed, 2025])
    left, right, bottom, top = parameters()["field_m"]
    centres = np.column_stack(
        (rng.uniform(left, right, components), rng.uniform(bottom, top, components))
    )
    widths = rng.uniform(6.0, 14.0, components)
    amplitudes = rng.uniform(15.0, 45.0, components)
    return centres, widths, amplitudes


def _field(points: FloatArray, truth: tuple[FloatArray, FloatArray, FloatArray]) -> FloatArray:
    centres, widths, amplitudes = truth
    squared = np.sum((points[:, None, :] - centres[None, :, :]) ** 2, axis=2)
    return np.asarray(np.exp(-squared / (2.0 * widths[None, :] ** 2)) @ amplitudes)


def _evaluation_grid(count: int) -> FloatArray:
    left, right, bottom, top = parameters()["field_m"]
    xs = left + (np.arange(count) + 0.5) * (right - left) / count
    ys = bottom + (np.arange(count) + 0.5) * (top - bottom) / count
    xx, yy = np.meshgrid(xs, ys)
    return np.column_stack((xx.ravel(), yy.ravel()))


def _starts(config: EccProfileConfig, count: int) -> FloatArray:
    offsets = (np.arange(count) - (count - 1) / 2.0) * config.start_spacing_m
    centre = np.asarray(config.start_center, dtype=np.float64)
    return np.column_stack((centre[0] + offsets, np.full(count, centre[1])))


class _Planner:
    """Algorithm 1's waypoint bookkeeping over the cells each robot owns."""

    def __init__(self, count: int, config: EccProfileConfig) -> None:
        self.config = config
        self.routes: list[list[FloatArray]] = [[] for _ in range(count)]
        self.targets: list[FloatArray | None] = [None] * count
        self.owned: list[CellRepresentatives | None] = [None] * count
        self.solves = 0
        self.truncations = 0
        self.route_lengths: list[int] = []

    def assign(self, reps: CellRepresentatives, positions: FloatArray) -> None:
        owner = voronoi_owner(reps.points, positions)
        for robot in range(len(positions)):
            mask = owner == robot
            self.owned[robot] = (
                CellRepresentatives(
                    points=reps.points[mask],
                    variances=reps.variances[mask],
                    counts=reps.counts[mask],
                )
                if np.any(mask)
                else None
            )
            self.routes[robot] = []

    def _plan(self, robot: int, position: FloatArray) -> None:
        cells = self.owned[robot]
        if cells is None or not len(cells.points):
            self.routes[robot] = []
            return
        if len(cells.points) == 1:
            self.routes[robot] = [cells.points[0].copy()]
            return
        plan = plan_cell_route(
            cells,
            position,
            discount=float(parameters()["rho"]),
            max_waypoints=self.config.max_waypoints,
        )
        self.solves += 1
        self.truncations += int(plan.truncated_by_revisit)
        self.route_lengths.append(len(plan.cell_indices))
        self.routes[robot] = [point.copy() for point in plan.waypoints]

    def next_destination(self, robot: int, position: FloatArray) -> FloatArray | None:
        if not self.routes[robot]:
            self._plan(robot, position)
        self.targets[robot] = self.routes[robot].pop(0) if self.routes[robot] else None
        return self.targets[robot]


def run_ecc_profile(config: EccProfileConfig) -> dict[str, Any]:
    """Run one controller on the audited ECC setup and return a JSON-safe record."""
    for claim in ("ecc_controller_reproduction", "ecc_planner_reproduction"):
        require_unlocked(claim)
    started = time.perf_counter()
    paper = parameters()
    robots = int(paper["n"])
    period = float(paper["t_s"])
    gamma = float(paper["gamma"])
    alpha_j = float(paper["alpha_J"])
    kappa = float(paper["kappa"])
    tolerance = float(paper["epsilon_tol"])
    scale = float(paper["L"])
    noise = float(paper["sigma_eps"]) ** 2
    signal = float(config.signal_variance)
    left, _, bottom, _ = paper["field_m"]
    cell = float(paper["cell_m"])

    truth = ground_truth(config.seed, config.field_components)
    queries = _evaluation_grid(config.grid_count)
    field_values = _field(queries, truth)
    positions = _starts(config, robots)
    model = SparseOnlineGP(
        length_scale=scale,
        signal_variance=signal,
        noise_variance=noise,
        max_basis=int(paper["n_d_max"]),
        # omega is absolute on the novelty, whose scale follows k(x,x).
        novelty_tolerance=float(paper["omega"]) / signal,
    )
    settings = EccQPSettings(
        epsilon_opt=float(paper["epsilon_opt"]),
        d_ca=float(paper["d_ca"]),
        alpha_ca=config.alpha_ca,
        max_speed=config.max_speed,
        polygon_sides=config.polygon_sides,
    )
    cache = EpochDecayCache(
        basis=np.empty((0, 2)),
        queries=queries,
        length_scale=scale,
        noise_variance=noise,
        signal_variance=signal,
    )
    owner = voronoi_owner(queries, positions)

    def local_row(
        source: EpochDecayCache, robot: int, where: FloatArray, elapsed: float, initial: float
    ) -> DecayConstraintRow:
        return source.row(
            position=where,
            selection=owner == robot,
            gamma=gamma,
            robot_count=robots,
            sample_period_s=period,
            elapsed_s=elapsed,
            initial_local=initial,
            alpha_j=alpha_j,
        )

    initial_local = [
        local_row(cache, robot, positions[robot], 0.0, 0.0).local_objective
        for robot in range(robots)
    ]
    j0 = signal * len(queries)
    shape = (int(round((paper["field_m"][1] - left) / cell)),) * 2

    def representatives(variance: FloatArray) -> CellRepresentatives:
        return cell_representatives(
            queries, variance, origin=(left, bottom), cell_size=cell, shape=shape
        )

    planner = _Planner(robots, config) if config.controller == "hierarchical" else None
    if planner is not None:
        planner.assign(representatives(np.full(len(queries), signal)), positions)
        for robot in range(robots):
            planner.next_destination(robot, positions[robot])

    steps = round(config.duration_s / config.dt)
    per_sample = round(period / config.dt)
    per_trajectory = max(1, round(config.trajectory_every_s / config.dt))
    epochs: list[dict[str, Any]] = [
        {
            "l": 0,
            "time_s": 0.0,
            "J": j0,
            "line": j0,
            "meets_eq5": True,
            "mse": float(np.mean(field_values**2)),
            "dictionary_size": 0,
        }
    ]
    trajectory: list[dict[str, Any]] = [{"time_s": 0.0, "positions": positions.tolist()}]
    samples: list[dict[str, Any]] = []
    snapshots: dict[str, Any] = {}
    distance = np.zeros(robots)
    window_early = np.zeros(robots)
    window_late = np.zeros(robots)
    minimum_separation = segment_min_separation(positions, positions)
    max_speed = 0.0
    slack_values: list[float] = []
    rate_met_steps = 0
    qp_wall = 0.0
    row_wall = 0.0
    failure: dict[str, Any] | None = None
    last_step = 0

    for step in range(steps):
        now = step * config.dt
        owner = voronoi_owner(queries, positions)
        velocities = np.zeros((robots, 2))
        for robot in range(robots):
            nominal = np.zeros(2)
            if planner is not None:
                target = planner.targets[robot]
                if target is not None and np.linalg.norm(positions[robot] - target) <= tolerance:
                    target = planner.next_destination(robot, positions[robot])
                if target is not None:
                    nominal = kappa * (target - positions[robot])
            timer = time.perf_counter()
            row = local_row(cache, robot, positions[robot], now, initial_local[robot])
            row_wall += time.perf_counter() - timer
            result = solve_robot_qp(
                robot=robot, positions=positions, row=row, nominal=nominal, settings=settings
            )
            qp_wall += result.wall_s
            if not result.success or result.velocity is None:
                finite_violation = math.isfinite(result.max_violation)
                failure = {
                    "time_s": now,
                    "robot": robot,
                    "status": result.status,
                    "max_violation": result.max_violation if finite_violation else None,
                    "claim_limit": "controller rejection on this run, not a property of the paper",
                }
                if not finite_violation:
                    failure["max_violation_note"] = (
                        "constraint residual unavailable: non-finite solver diagnostic "
                        f"({result.max_violation!r}); null does not mean zero violation"
                    )
                break
            velocities[robot] = result.velocity
            slack_values.append(float(result.slack or 0.0))
            rate_met_steps += int(result.rate_satisfied_without_slack)
        if failure is not None:
            break
        moved = positions + config.dt * velocities
        minimum_separation = min(minimum_separation, segment_min_separation(positions, moved))
        travel = np.linalg.norm(moved - positions, axis=1)
        distance += travel
        if now < 360.0:
            window_early += travel
        if now >= 640.0:
            window_late += travel
        max_speed = max(max_speed, float(np.max(np.linalg.norm(velocities, axis=1))))
        positions = moved
        last_step = step + 1
        if last_step % per_trajectory == 0:
            trajectory.append({"time_s": last_step * config.dt, "positions": positions.tolist()})
        if last_step % per_sample:
            continue

        index = last_step // per_sample
        instant = last_step * config.dt
        values = _field(positions, truth)
        for robot in range(robots):
            noise_value = math.sqrt(noise) * indexed_normal(config.seed, robot, index)
            label = float(values[robot] + noise_value)
            model.update(positions[robot][None, :], np.asarray([label]))
            samples.append(
                {
                    "l": index,
                    "time_s": instant,
                    "robot": robot,
                    "position": positions[robot].tolist(),
                    "value": label,
                }
            )
        prediction = model.predict(queries, variance="latent")
        objective = float(np.sum(prediction.variance))
        line = j0 - gamma * index
        epochs.append(
            {
                "l": index,
                "time_s": instant,
                "J": objective,
                "line": line,
                "meets_eq5": objective <= line,
                "mse": float(np.mean((prediction.mean - field_values) ** 2)),
                "dictionary_size": model.dictionary_size,
            }
        )
        cache = EpochDecayCache(
            basis=model.dictionary_points,
            queries=queries,
            length_scale=scale,
            noise_variance=noise,
            signal_variance=signal,
        )
        if planner is not None:
            planner.assign(representatives(prediction.variance), positions)
            for robot in range(robots):
                planner.next_destination(robot, positions[robot])
        if any(math.isclose(instant, mark, abs_tol=1e-9) for mark in (320.0, 640.0, 1000.0)):
            snapshots[f"{instant:.0f}"] = {
                "variance": prediction.variance.tolist(),
                "mean": prediction.mean.tolist(),
                "positions": positions.tolist(),
                "basis": model.dictionary_points.tolist(),
            }

    final = epochs[-1]
    first_violation = next((entry["l"] for entry in epochs[1:] if not entry["meets_eq5"]), None)
    met_prefix = 0
    for entry in epochs[1:]:
        if not entry["meets_eq5"]:
            break
        met_prefix += 1
    prediction = model.predict(queries, variance="latent")
    uncovered = float(np.mean(prediction.variance > 0.5 * signal))
    stalled = [
        int(robot)
        for robot in range(robots)
        if window_early[robot] > 0 and window_late[robot] < 0.25 * window_early[robot]
    ]
    record: dict[str, Any] = {
        "schema_version": 1,
        "profile": "ecc2025",
        "controller": config.controller,
        "equation": "(10) constraint-only" if config.controller == "constraint_only" else "(17)",
        "status": "failed" if failure is not None else "completed",
        "failure": failure,
        "config": asdict(config),
        "paper_values": {key: value for key, value in paper.items()},
        "completed_time_s": last_step * config.dt,
        "epochs": epochs,
        "samples": samples,
        "trajectory": trajectory,
        "snapshots": snapshots,
        "field": {
            "queries": queries.tolist(),
            "values": field_values.tolist(),
            "parameters": [array.tolist() for array in truth],
        },
        "summary": {
            "J0": j0,
            "final_J": final["J"],
            "final_mse": final["mse"],
            "initial_mse": epochs[0]["mse"],
            "first_eq5_violation_epoch": first_violation,
            "eq5_met_prefix_epochs": met_prefix,
            "uncovered_fraction": uncovered,
            "path_length_m": distance.tolist(),
            "path_first_360s_m": window_early.tolist(),
            "path_last_360s_m": window_late.tolist(),
            "stalled_robots": stalled,
            "min_separation_m": minimum_separation,
            "max_speed_mps": max_speed,
            "rate_row_met_without_slack_fraction": (rate_met_steps / max(1, len(slack_values))),
            "median_slack": float(np.median(slack_values)) if slack_values else None,
            "dictionary_size": model.dictionary_size,
            "admitted": model.admitted_count,
            "projected": model.projected_count,
            "pruned": model.pruned_count,
            "planner_solves": planner.solves if planner is not None else 0,
            "planner_truncations": planner.truncations if planner is not None else 0,
            "median_route_length": (
                float(np.median(planner.route_lengths))
                if planner is not None and planner.route_lengths
                else None
            ),
            "qp_wall_s": qp_wall,
            "row_wall_s": row_wall,
            "runtime_s": time.perf_counter() - started,
        },
        "project_choices": [
            "ground truth: 40-bump Gaussian mixture fixed before any controller run",
            "evaluation set: 30 x 30 cell-centred grid on F",
            (
                f"start: three robots {config.start_spacing_m:g} m apart at "
                f"({config.start_center[0]:g}, {config.start_center[1]:g})"
            ),
            "dt = 0.1 s Euler; first sample at t_1 = t_s; robots assimilated in index order",
            "alpha_ca linear gain 1; 2 m/s speed polygon; no workspace constraint",
            "I_i0 evaluated at t = 0",
            "replan after every sample (text, p. 309), and when a route is exhausted",
            "self-transitions excluded; value iteration; route stopped on revisit",
            f"signal_variance = {signal:g} ({'Theorem 1' if signal == 1.0 else 'figure scale'})",
        ],
        "claim_limits": [
            "qualitative comparison only: the paper's seeds and ground truth are unpublished",
            "not a numerical reproduction of Figs. 2-6",
            "not a sampled-data safety certificate",
        ],
    }
    return record
