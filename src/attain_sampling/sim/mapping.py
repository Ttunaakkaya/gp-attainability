"""Independent GP mapping demo with paired disturbances and executed trajectories.

This module is an independent application, not an ECC2025 reproduction. Collision
handling checks straight segments of the sampled kinematic model. The optional M1
QP is an independent holonomic controller, not a physical safety certificate.
"""

from __future__ import annotations

import math
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from attain_sampling.attainability.budget import MissionBudget, mission_budget
from attain_sampling.attainability.policy import PolicySettings, manage_plan
from attain_sampling.attainability.rollout import NominalStepper, StepOutcome
from attain_sampling.control.qp import QPSettings, solve_tracking_qp
from attain_sampling.gp.exact import ExactGP
from attain_sampling.gp.protocol import CovarianceBelief
from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.planning.primitive_dp import plan_primitive_dp
from attain_sampling.planning.timed_dp import DPSettings, plan_timed_dp
from attain_sampling.random import derive_seed_manifest, indexed_normal
from attain_sampling.sim import usv

FloatArray = NDArray[np.float64]
METHODS = ("sweep", "greedy", "adaptive")
AVAILABLE_METHODS = (*METHODS, "dp", "p")
PLANNING_METHODS = ("dp", "p")
MODELS = ("holonomic", "usv", "usv_curvature")
# Models the timed planners (B3, P) support. The original "usv" allows turning on the
# spot and has no heading-state planner; the M7 curvature model has one.
PLANNING_MODELS = ("holonomic", "usv_curvature")


@dataclass(frozen=True, slots=True)
class MappingConfig:
    """Small CPU-only mapping scenario; lengths in metres, times in seconds."""

    domain: tuple[float, float] = (60.0, 40.0)
    robot_count: int = 3
    duration_s: float = 90.0
    dt: float = 0.5
    sample_period_s: float = 5.0
    grid_shape: tuple[int, int] = (24, 16)
    seed: int = 7
    noise_std: float = 0.15
    dropout_prob: float = 0.0
    drift_strength: float = 0.0
    max_speed: float = 2.0
    min_separation: float = 2.0
    model: str = "holonomic"
    max_turn_rate: float = 0.45
    length_scale: float = 8.0
    signal_variance: float = 1.0
    controller: str = "filter"
    qp_alpha: float = 1.0
    qp_polygon_sides: int = 16
    qp_max_iter: int = 10000
    qp_acceptance_tol: float = 1e-7
    dp_horizon_steps: int = 4
    dp_grid_shape: tuple[int, int] = (9, 7)
    dp_travel_weight: float = 0.01
    dp_motion_primitives: bool = True
    p_controller_rollout: bool = True
    p_retain_plan: bool = True
    p_event_triggers: bool = True
    p_deviation_trigger_m: float = 1.5
    p_intervention_trigger_mps: float = 0.25
    p_switch_margin: float = 0.01
    p_max_rollout_candidates: int = 6
    target_mean_variance: float | None = None
    gp_backend: str = "exact"
    sogp_max_basis: int = 64
    sogp_novelty_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        positive = (
            self.duration_s,
            self.dt,
            self.sample_period_s,
            self.max_speed,
            self.min_separation,
            self.max_turn_rate,
            self.length_scale,
            self.signal_variance,
        )
        if any(not math.isfinite(v) or v <= 0 for v in positive):
            raise ValueError("durations, motion bounds and kernel parameters must be finite > 0")
        if len(self.domain) != 2 or any(not math.isfinite(v) or v <= 0 for v in self.domain):
            raise ValueError("domain must contain two positive finite lengths")
        if (
            not isinstance(self.robot_count, int)
            or isinstance(self.robot_count, bool)
            or self.robot_count not in (2, 3, 4)
        ):
            raise ValueError("robot_count must be 2, 3 or 4")
        if len(self.grid_shape) != 2 or any(
            isinstance(v, bool) or not isinstance(v, int) or v < 2 for v in self.grid_shape
        ):
            raise ValueError("grid_shape must contain two integers >= 2")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if not math.isfinite(self.noise_std) or self.noise_std < 0:
            raise ValueError("noise_std must be finite and non-negative")
        if not math.isfinite(self.dropout_prob) or not 0 <= self.dropout_prob <= 1:
            raise ValueError("dropout_prob must lie in [0, 1]")
        if not math.isfinite(self.drift_strength) or self.drift_strength < 0:
            raise ValueError("drift_strength must be finite and non-negative")
        if self.model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}")
        if not isinstance(self.dp_motion_primitives, bool):
            raise ValueError("dp_motion_primitives must be a boolean")
        if self.controller not in ("filter", "qp"):
            raise ValueError("controller must be 'filter' or 'qp'")
        if self.controller == "qp" and self.model != "holonomic":
            raise ValueError("M1 QP supports holonomic robots only; USV uses the reference filter")
        QPSettings(
            alpha=self.qp_alpha,
            polygon_sides=self.qp_polygon_sides,
            max_iter=self.qp_max_iter,
            acceptance_tol=self.qp_acceptance_tol,
        )
        DPSettings(
            horizon_steps=self.dp_horizon_steps,
            grid_shape=self.dp_grid_shape,
            travel_weight=self.dp_travel_weight,
        )
        PolicySettings(
            controller_rollout=self.p_controller_rollout,
            retain_plan=self.p_retain_plan,
            event_triggers=self.p_event_triggers,
            deviation_trigger_m=self.p_deviation_trigger_m,
            intervention_trigger_mps=self.p_intervention_trigger_mps,
            switch_margin=self.p_switch_margin,
            max_rollout_candidates=self.p_max_rollout_candidates,
            target_mean_variance=self.target_mean_variance,
        )
        if self.gp_backend not in ("exact", "sogp"):
            raise ValueError("gp_backend must be 'exact' or 'sogp'")
        if (
            isinstance(self.sogp_max_basis, bool)
            or not isinstance(self.sogp_max_basis, int)
            or not 1 <= self.sogp_max_basis <= 512
        ):
            raise ValueError("sogp_max_basis must be an integer in [1, 512]")
        if (
            isinstance(self.sogp_novelty_tolerance, bool)
            or not math.isfinite(self.sogp_novelty_tolerance)
            or not 1e-12 <= self.sogp_novelty_tolerance < 1
        ):
            raise ValueError("sogp_novelty_tolerance must be finite in [1e-12, 1)")
        for duration in (self.duration_s, self.sample_period_s):
            if duration < self.dt or not math.isclose(
                duration / self.dt, round(duration / self.dt), abs_tol=1e-9
            ):
                raise ValueError("duration and sample period must be integer multiples of dt")
        if self.domain[1] / self.robot_count < self.min_separation:
            raise ValueError("domain is too narrow for separated initial robot positions")
        if self.model == "usv_curvature":
            inset = _usv_inset(self)
            if min(self.domain) <= 2 * inset + 1.0:
                raise ValueError("domain is too small for the USV turning radius")
            starts = initial_positions(self)
            if (
                usv.loiter_assignment(
                    starts,
                    np.zeros(self.robot_count),
                    radius=usv_turn_radius(self),
                    domain=self.domain,
                    min_separation=self.min_separation,
                )
                is None
            ):
                raise ValueError(
                    "initial USV positions have no private loiter circles; "
                    "enlarge the domain or reduce robots"
                )


def evaluate_field(points: FloatArray, config: MappingConfig) -> FloatArray:
    """Seeded smooth ground truth, accessed only by sensors and evaluation."""

    rng = np.random.default_rng(derive_seed_manifest(config.seed).field_seed)
    extent = np.asarray(config.domain, dtype=float)
    centers = rng.uniform(0.12, 0.88, size=(6, 2)) * extent
    widths = rng.uniform(0.09, 0.22, size=(6, 2)) * extent
    amplitudes = np.array([1.3, -1.1, 0.8, -0.9, 1.0, -0.7])
    distances = (points[:, None, :] - centers[None, :, :]) / widths[None, :, :]
    bumps = np.exp(-0.5 * np.sum(distances**2, axis=2)) @ amplitudes
    normalized = points / extent
    waves = 0.25 * np.sin(2 * np.pi * normalized[:, 0]) * np.cos(2 * np.pi * normalized[:, 1])
    return np.asarray(bumps + waves, dtype=float)


def usv_turn_radius(config: MappingConfig) -> float:
    """Minimum turning radius of the M7 curvature-limited USV."""
    return usv.turn_radius(config.max_speed, config.max_turn_rate)


def _usv_inset(config: MappingConfig) -> float:
    """Planning targets stay this far from the edge so a turning circle fits inside."""
    return usv_turn_radius(config) + 0.5


def initial_positions(config: MappingConfig) -> FloatArray:
    """Common start for every policy.

    The curvature USV starts a turning radius away from the left edge, in two staggered
    columns, so that every robot has a private loiter circle from the first step.
    """
    ys = (np.arange(config.robot_count) + 0.35) * config.domain[1] / config.robot_count
    if config.model != "usv_curvature":
        xs = np.full(config.robot_count, min(3.0, config.domain[0] * 0.1))
        return np.column_stack((xs, ys))
    radius = usv_turn_radius(config)
    xs = radius + 1.0 + (np.arange(config.robot_count) % 2) * (2 * radius + config.min_separation)
    return np.column_stack((xs, ys))


def _reference_path(
    positions: FloatArray,
    headings: FloatArray,
    targets: FloatArray,
    steps: int,
    config: MappingConfig,
) -> list[FloatArray]:
    """Nominal geometric path to the commanded targets, one point per control step.

    Holonomic robots follow straight lines. The curvature USV follows its shortest
    forward path, so deviation triggers compare against a path it can actually fly.
    """
    if config.model != "usv_curvature":
        return [positions + (targets - positions) * offset / steps for offset in range(steps + 1)]
    fractions = np.arange(steps + 1) / steps
    radius = usv_turn_radius(config)
    per_robot = [
        usv.sample_point_path(
            positions[robot], float(headings[robot]), targets[robot], radius, fractions
        )
        for robot in range(len(positions))
    ]
    return [
        np.asarray([robot_path[offset] for robot_path in per_robot]) for offset in range(steps + 1)
    ]


def segment_min_separation(start: FloatArray, end: FloatArray) -> float:
    """Exact closest pair separation along simultaneous linear timestep segments."""

    minimum = math.inf
    for i in range(len(start)):
        for j in range(i):
            relative = start[i] - start[j]
            velocity = (end[i] - start[i]) - (end[j] - start[j])
            speed2 = float(velocity @ velocity)
            fraction = float(np.clip(-(relative @ velocity) / speed2, 0, 1)) if speed2 else 0.0
            minimum = min(minimum, float(np.linalg.norm(relative + fraction * velocity)))
    return minimum


def safe_displacement(
    positions: FloatArray, displacement: FloatArray, config: MappingConfig
) -> tuple[FloatArray, bool, float]:
    """Common backtracking preserves segment separation and the rectangular bounds."""

    if segment_min_separation(positions, positions) < config.min_separation - 1e-9:
        raise ValueError("initial state violates minimum separation")
    extent = np.asarray(config.domain)
    if np.any(positions < 0) or np.any(positions > extent):
        raise ValueError("initial state lies outside domain")
    scale = 1.0
    for _ in range(25):
        proposed = positions + scale * displacement
        separation = segment_min_separation(positions, proposed)
        if (
            np.all(proposed >= 0)
            and np.all(proposed <= extent)
            and separation >= config.min_separation - 1e-10
        ):
            return proposed, scale < 1, separation
        scale *= 0.5
    return positions.copy(), True, segment_min_separation(positions, positions)


def _wrap(angles: FloatArray) -> FloatArray:
    return np.asarray((angles + np.pi) % (2 * np.pi) - np.pi, dtype=float)


class ControlFailure(RuntimeError):
    """A rejected command is never propagated or replaced by a hidden fallback."""

    def __init__(self, event: dict[str, Any]) -> None:
        self.event = event
        super().__init__(str(event.get("failure_reason") or event.get("status")))


def _advance(
    positions: FloatArray,
    headings: FloatArray,
    targets: FloatArray,
    config: MappingConfig,
    tick: int,
    *,
    disturbed: bool,
    control_events: list[dict[str, Any]] | None = None,
    phase: str = "preview",
    tracking_time_s: float | None = None,
    plan_id: str | None = None,
) -> tuple[FloatArray, FloatArray, bool, float, FloatArray]:
    control_started = time.perf_counter()
    delta = targets - positions
    distance = np.linalg.norm(delta, axis=1)
    direction = delta / np.maximum(distance[:, None], 1e-12)
    if tracking_time_s is not None and (
        not math.isfinite(tracking_time_s) or tracking_time_s < config.dt - 1e-10
    ):
        raise ValueError("tracking time must be finite and at least one control interval")
    # Timed DP requests arrival at the sampling deadline, not early arrival and
    # waiting. Feedback/QP can change this nominal geometric schedule.
    speed = np.minimum(config.max_speed, distance / (tracking_time_s or config.dt))
    innovations = np.zeros_like(positions)
    if disturbed and config.drift_strength:
        for robot in range(len(positions)):
            for axis in range(2):
                innovations[robot, axis] = indexed_normal(
                    config.seed, robot, tick, stream=f"motion-{axis}"
                )
    if config.model == "usv_curvature":
        return _advance_usv_curvature(
            positions,
            headings,
            targets,
            config,
            tick,
            innovations=innovations if disturbed else None,
            control_events=control_events,
            phase=phase,
            tracking_time_s=tracking_time_s,
            plan_id=plan_id,
            started=control_started,
        )
    if config.model == "usv":
        desired_heading = np.arctan2(delta[:, 1], delta[:, 0])
        desired_heading = np.where(distance > 1e-8, desired_heading, headings)
        yaw = _wrap(desired_heading - headings)
        yaw += config.drift_strength * innovations[:, 0] * config.dt
        yaw = np.clip(yaw, -config.max_turn_rate * config.dt, config.max_turn_rate * config.dt)
        next_headings = _wrap(headings + yaw)
        # Turn before advancing; reduce propulsion while pointing away from the goal.
        alignment = np.maximum(0, np.cos(_wrap(desired_heading - next_headings)))
        velocity = (
            speed[:, None]
            * alignment[:, None]
            * np.column_stack((np.cos(next_headings), np.sin(next_headings)))
        )
    else:
        velocity = speed[:, None] * direction + config.drift_strength * innovations
        velocity *= np.minimum(
            1.0, config.max_speed / np.maximum(np.linalg.norm(velocity, axis=1), 1e-12)
        )[:, None]
        next_headings = np.where(
            np.linalg.norm(velocity, axis=1) > 1e-10,
            np.arctan2(velocity[:, 1], velocity[:, 0]),
            headings,
        )
    requested_velocity = velocity.copy()
    if config.controller == "qp":
        result = solve_tracking_qp(
            positions,
            requested_velocity,
            domain=config.domain,
            max_speed=config.max_speed,
            min_separation=config.min_separation,
            dt=config.dt,
            settings=QPSettings(
                alpha=config.qp_alpha,
                polygon_sides=config.qp_polygon_sides,
                max_iter=config.qp_max_iter,
                acceptance_tol=config.qp_acceptance_tol,
            ),
        )
        event = {
            **result.log,
            "backend": "qp",
            "phase": phase,
            "plan_id": plan_id,
            "tracking_time_s": tracking_time_s,
            "tick": tick,
            "time_s": tick * config.dt,
            "success": result.success,
            "positions_before": positions.tolist(),
            "requested_velocity": requested_velocity.tolist(),
            "applied_velocity": None if result.velocity is None else result.velocity.tolist(),
            "wall_s": time.perf_counter() - control_started,
        }
        if control_events is not None:
            control_events.append(event)
        if not result.success or result.velocity is None:
            raise ControlFailure(event)
        velocity = result.velocity
        next_positions = positions + velocity * config.dt
        separation = segment_min_separation(positions, next_positions)
        intervention = bool(
            np.linalg.norm(velocity - requested_velocity) > config.qp_acceptance_tol
        )
        next_headings = np.where(
            np.linalg.norm(velocity, axis=1) > 1e-10,
            np.arctan2(velocity[:, 1], velocity[:, 0]),
            headings,
        )
    else:
        next_positions, intervention, separation = safe_displacement(
            positions, velocity * config.dt, config
        )
        if control_events is not None:
            control_events.append(
                {
                    "backend": "filter",
                    "phase": phase,
                    "plan_id": plan_id,
                    "tracking_time_s": tracking_time_s,
                    "tick": tick,
                    "time_s": tick * config.dt,
                    "success": True,
                    "status": "backtracked" if intervention else "accepted",
                    "positions_before": positions.tolist(),
                    "requested_velocity": requested_velocity.tolist(),
                    "applied_velocity": ((next_positions - positions) / config.dt).tolist(),
                    "wall_s": time.perf_counter() - control_started,
                    "solve_s": None,
                    "iterations": None,
                    "primal_residual": None,
                    "dual_residual": None,
                    "max_constraint_violation": None,
                    "segment_min_separation": separation,
                }
            )
    turn_rates = _wrap(next_headings - headings) / config.dt
    return next_positions, next_headings, intervention, separation, turn_rates


def _advance_usv_curvature(
    positions: FloatArray,
    headings: FloatArray,
    targets: FloatArray,
    config: MappingConfig,
    tick: int,
    *,
    innovations: FloatArray | None,
    control_events: list[dict[str, Any]] | None,
    phase: str,
    tracking_time_s: float | None,
    plan_id: str | None,
    started: float,
) -> tuple[FloatArray, FloatArray, bool, float, FloatArray]:
    """Guidance plus the certified arc filter of :mod:`attain_sampling.sim.usv`.

    The disturbance is a yaw-rate tracking error of ``drift_strength`` rad/s at full
    speed, applied to the commanded curvature within the vehicle's authority and
    before the filter, exactly like the holonomic velocity-tracking disturbance.
    """
    radius = usv_turn_radius(config)
    speeds, curvatures, _ = usv.guidance(
        positions,
        headings,
        targets,
        radius=radius,
        max_speed=config.max_speed,
        dt=config.dt,
        tracking_time_s=tracking_time_s,
    )
    if innovations is not None and config.drift_strength:
        curvatures = np.clip(
            curvatures + config.drift_strength * innovations[:, 0] / config.max_speed,
            -1.0 / radius,
            1.0 / radius,
        )
    requested_end, _ = usv.integrate_arc(positions, headings, speeds * config.dt, curvatures)
    requested_velocity = (requested_end - positions) / config.dt
    event: dict[str, Any] = {
        "backend": "arc_filter",
        "phase": phase,
        "plan_id": plan_id,
        "tracking_time_s": tracking_time_s,
        "tick": tick,
        "time_s": tick * config.dt,
        "positions_before": positions.tolist(),
        "headings_before": headings.tolist(),
        "requested_velocity": requested_velocity.tolist(),
        "requested_speeds": speeds.tolist(),
        "requested_curvatures": curvatures.tolist(),
        "turn_radius_m": radius,
        "solve_s": None,
        "iterations": None,
        "primal_residual": None,
        "dual_residual": None,
        "max_constraint_violation": None,
    }
    try:
        step = usv.filter_step(
            positions,
            headings,
            speeds,
            curvatures,
            radius=radius,
            domain=config.domain,
            min_separation=config.min_separation,
            dt=config.dt,
        )
    except (ValueError, RuntimeError) as error:
        event.update(
            {
                "success": False,
                "status": "arc_filter_rejected_state",
                "failure_reason": f"{type(error).__name__}: {error}",
                "applied_velocity": None,
                "wall_s": time.perf_counter() - started,
            }
        )
        if control_events is not None:
            control_events.append(event)
        raise ControlFailure(event) from error
    next_positions = step.positions
    separation = segment_min_separation(positions, next_positions)
    event.update(
        {
            "success": True,
            "status": "modified" if step.intervention else "accepted",
            "applied_velocity": ((next_positions - positions) / config.dt).tolist(),
            "applied_speeds": step.speeds.tolist(),
            "applied_curvatures": step.curvatures.tolist(),
            "speed_scales": step.scales.tolist(),
            "loitering": step.loitering.tolist(),
            "certified_arc_separation": step.certified_separation,
            "segment_min_separation": separation,
            "wall_s": time.perf_counter() - started,
        }
    )
    if control_events is not None:
        control_events.append(event)
    turn_rates = _wrap(step.headings - headings) / config.dt
    return next_positions, step.headings, step.intervention, separation, turn_rates


def _new_gp(config: MappingConfig) -> ExactGP | SparseOnlineGP:
    if config.gp_backend == "sogp":
        return SparseOnlineGP(
            length_scale=config.length_scale,
            signal_variance=config.signal_variance,
            noise_variance=config.noise_std**2,
            max_basis=config.sogp_max_basis,
            novelty_tolerance=config.sogp_novelty_tolerance,
        )
    return ExactGP(
        length_scale=config.length_scale,
        signal_variance=config.signal_variance,
        noise_variance=config.noise_std**2,
    )


def _gp_telemetry(gp: ExactGP | SparseOnlineGP) -> dict[str, Any]:
    sparse = gp if isinstance(gp, SparseOnlineGP) else None
    return {
        "backend": gp.backend_name,
        "observation_count": gp.observation_count,
        "dictionary_size": sparse.dictionary_size if sparse else None,
        "max_basis": sparse.max_basis if sparse else None,
        "admitted_count": sparse.admitted_count if sparse else None,
        "projected_count": sparse.projected_count if sparse else None,
        "pruned_count": sparse.pruned_count if sparse else None,
        "state_nbytes": sparse.state_nbytes if sparse else None,
    }


def _select_targets(
    gp: CovarianceBelief,
    positions: FloatArray,
    headings: FloatArray,
    grid: FloatArray,
    config: MappingConfig,
    steps: int,
) -> FloatArray:
    """Sequential joint fantasy scoring avoids redundant candidate information gains."""

    # USV scores use endpoint rollouts through the same turn-limited controller.
    # Candidate rollouts are independent; selected goals receive a joint safety
    # preview before their predicted measurement variance is recorded.
    angles = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    directions = np.vstack((np.zeros((1, 2)), np.column_stack((np.cos(angles), np.sin(angles)))))
    radius = config.max_speed * config.dt * steps
    margin = _usv_inset(config) if config.model == "usv_curvature" else 0.0
    candidates = np.clip(
        positions[:, None, :] + radius * directions[None, :, :],
        margin,
        np.asarray(config.domain) - margin,
    )
    sample_candidates = candidates.copy()
    if config.model != "holonomic":
        for robot in range(config.robot_count):
            for candidate_index, target in enumerate(candidates[robot]):
                candidate_position = positions[robot : robot + 1].copy()
                candidate_heading = headings[robot : robot + 1].copy()
                for tick in range(steps):
                    candidate_position, candidate_heading, _, _, _ = _advance(
                        candidate_position,
                        candidate_heading,
                        target[None, :],
                        config,
                        tick,
                        disturbed=False,
                    )
                sample_candidates[robot, candidate_index] = candidate_position[0]
    flattened = sample_candidates.reshape(-1, 2)
    cross = gp.posterior_covariance(grid, flattened)
    covariance = gp.posterior_covariance(flattened)
    noise_variance = gp.noise_variance + gp.jitter
    selected = positions.copy()
    selected_samples = positions.copy()
    for robot in range(config.robot_count):
        indices = np.arange(robot * len(directions), (robot + 1) * len(directions))
        gains = np.mean(cross[:, indices] ** 2, axis=0) / (
            np.maximum(np.diag(covariance)[indices], 0) + noise_variance
        )
        # Avoid choosing a measurement that is too close to an already selected
        # target. The motion layer independently checks every executed segment.
        if robot:
            distances = np.linalg.norm(
                sample_candidates[robot, :, None, :] - selected_samples[None, :robot, :],
                axis=2,
            )
            gains[np.any(distances < config.min_separation, axis=1)] = -math.inf
        candidate_index = int(np.argmax(gains))
        choice = int(indices[candidate_index])
        selected[robot] = candidates[robot, candidate_index]
        selected_samples[robot] = flattened[choice]
        denominator = max(float(covariance[choice, choice]), 0) + noise_variance
        column = covariance[:, choice].copy()
        cross -= np.outer(cross[:, choice].copy(), column) / denominator
        covariance -= np.outer(column, column) / denominator
    return selected


def _sweep_routes(config: MappingConfig, starts: FloatArray) -> list[FloatArray]:
    width, height = config.domain
    routes = []
    for robot in range(config.robot_count):
        stripe_low = height * robot / config.robot_count
        stripe_high = height * (robot + 1) / config.robot_count
        margin = (
            _usv_inset(config)
            if config.model == "usv_curvature"
            else min(2.0, width * 0.08, (stripe_high - stripe_low) * 0.2)
        )
        ys = np.linspace(starts[robot, 1], stripe_high - margin, 3)
        route: list[list[float]] = []
        for row, y in enumerate(ys):
            route.append([width - margin if row % 2 == 0 else margin, float(y)])
            if row < len(ys) - 1:
                route.append([route[-1][0], float(ys[row + 1])])
        routes.append(np.array(route))
    return routes


def _preview(
    positions: FloatArray,
    headings: FloatArray,
    targets: FloatArray,
    config: MappingConfig,
    start_tick: int,
    steps: int,
    *,
    routes: list[FloatArray] | None = None,
    route_indices: list[int] | None = None,
    control_events: list[dict[str, Any]] | None = None,
) -> tuple[list[FloatArray], list[FloatArray], FloatArray]:
    path, goals = [positions.copy()], []
    current = positions.copy()
    orientation = headings.copy()
    for offset in range(steps):
        if routes is not None and route_indices is not None:
            for robot, route in enumerate(routes):
                index = route_indices[robot]
                if np.linalg.norm(current[robot] - route[index]) <= config.max_speed * config.dt:
                    index = min(index + 1, len(route) - 1)
                    route_indices[robot] = index
                targets[robot] = route[index]
        goals.append(targets.copy())
        current, orientation, _, _, _ = _advance(
            current,
            orientation,
            targets,
            config,
            start_tick + offset + 1,
            disturbed=False,
            control_events=control_events,
        )
        path.append(current.copy())
    return path, goals, orientation


def _control_summary(controls: list[dict[str, Any]]) -> dict[str, Any]:
    executed = [event for event in controls if event["phase"] == "execution"]
    previewed = [event for event in controls if event["phase"] == "preview"]
    # M4 candidate rollouts are a third phase: they are neither applied motion nor
    # open-loop preplanning. Their wall time already sits inside planning_s.
    rolled = [event for event in controls if event["phase"] == "candidate_rollout"]
    durations = [float(event["wall_s"]) for event in executed]
    qp = [event for event in executed if event["backend"] == "qp"]
    return {
        "control_s": sum(durations),
        "control_preview_s": sum(float(event["wall_s"]) for event in previewed),
        "control_rollout_s": sum(float(event["wall_s"]) for event in rolled),
        "rollout_control_calls": len(rolled),
        "rollout_qp_solves": sum(event["backend"] == "qp" for event in rolled),
        "rollout_qp_failures": sum(
            event["backend"] == "qp" and not event["success"] for event in rolled
        ),
        "control_median_s": float(np.median(durations)) if durations else None,
        "control_p95_s": float(np.quantile(durations, 0.95)) if durations else None,
        "control_max_s": max(durations) if durations else None,
        "qp_solves": len(qp),
        "qp_failures": sum(not event["success"] for event in qp),
        "preview_qp_solves": sum(event["backend"] == "qp" for event in previewed),
        "preview_qp_failures": sum(
            event["backend"] == "qp" and not event["success"] for event in previewed
        ),
    }


def _timed_dp_plan(
    gp: CovarianceBelief,
    positions: FloatArray,
    headings: FloatArray,
    grid: FloatArray,
    config: MappingConfig,
    tick: int,
    version: int,
    failures: list[dict[str, Any]],
    *,
    include_greedy: bool = False,
    backend: str = "timed_dp",
) -> dict[str, Any]:
    """Preserve a planner rejection as partial evidence, not an impossibility result."""
    started = time.perf_counter()
    settings = DPSettings(
        horizon_steps=config.dp_horizon_steps,
        grid_shape=config.dp_grid_shape,
        travel_weight=config.dp_travel_weight,
        include_greedy_candidates=include_greedy,
    )
    try:
        if config.model == "usv_curvature" and config.dp_motion_primitives:
            return plan_primitive_dp(
                gp,
                positions,
                headings,
                grid,
                domain=config.domain,
                max_speed=config.max_speed,
                min_separation=config.min_separation,
                turn_radius=usv_turn_radius(config),
                sample_period_s=config.sample_period_s,
                now_s=tick * config.dt,
                mission_end_s=config.duration_s,
                plan_version=version,
                settings=settings,
            )
        return plan_timed_dp(
            gp,
            positions,
            grid,
            domain=config.domain,
            max_speed=config.max_speed,
            min_separation=config.min_separation,
            sample_period_s=config.sample_period_s,
            now_s=tick * config.dt,
            mission_end_s=config.duration_s,
            plan_version=version,
            settings=settings,
            grid_inset=_usv_inset(config) if config.model == "usv_curvature" else 0.0,
        )
    except (ValueError, FloatingPointError) as error:
        event = {
            "phase": "planning",
            "backend": backend,
            "tick": tick,
            "time_s": tick * config.dt,
            "success": False,
            "failure_reason": f"{type(error).__name__}: {error}",
            "status": "planner_rejected",
            "attempted_plan_version": version,
            "positions_before": positions.tolist(),
            "belief_observation_count": gp.observation_count,
            "wall_s": time.perf_counter() - started,
            "claim_limit": "planner/numerical failure, not mission impossibility",
        }
        failures.append(event)
        raise ControlFailure(event) from error


def _policy_settings(config: MappingConfig) -> PolicySettings:
    return PolicySettings(
        controller_rollout=config.p_controller_rollout,
        retain_plan=config.p_retain_plan,
        event_triggers=config.p_event_triggers,
        deviation_trigger_m=config.p_deviation_trigger_m,
        intervention_trigger_mps=config.p_intervention_trigger_mps,
        switch_margin=config.p_switch_margin,
        max_rollout_candidates=config.p_max_rollout_candidates,
        target_mean_variance=config.target_mean_variance,
    )


def _nominal_stepper(
    config: MappingConfig, control_events: list[dict[str, Any]] | None
) -> NominalStepper:
    """Expose the executing controller as a disturbance-free candidate stepper.

    A rollout uses the same controller the mission executes, so a rejection means
    *this candidate* is not executable from here. It is reported as a rejected
    candidate rather than propagated as a mission failure, and it is never replaced
    by a hidden hold or clipped command. Rejecting every candidate still fails the
    mission explicitly; it never proves the mission target is unreachable.
    """

    def step(
        positions: FloatArray,
        headings: FloatArray,
        targets: FloatArray,
        *,
        tick: int,
        tracking_time_s: float,
    ) -> StepOutcome:
        try:
            moved, turned, intervention, separation, _ = _advance(
                positions,
                headings,
                targets,
                config,
                tick,
                disturbed=False,
                control_events=control_events,
                phase="candidate_rollout",
                tracking_time_s=tracking_time_s,
            )
        except ControlFailure as failure:
            reason = failure.event.get("failure_reason") or failure.event.get("status")
            return StepOutcome(
                accepted=False,
                positions=positions,
                headings=headings,
                intervention=False,
                min_separation=math.nan,
                failure_reason=str(reason),
            )
        return StepOutcome(
            accepted=True,
            positions=moved,
            headings=turned,
            intervention=intervention,
            min_separation=separation,
        )

    return step


def _managed_plan(
    gp: CovarianceBelief,
    positions: FloatArray,
    headings: FloatArray,
    grid: FloatArray,
    config: MappingConfig,
    tick: int,
    version: int,
    failures: list[dict[str, Any]],
    *,
    retained_plan: dict[str, Any] | None,
    trigger: str,
    controls: list[dict[str, Any]],
    previous_budget: MissionBudget | None,
) -> tuple[dict[str, Any], MissionBudget]:
    """Run the M4 decision: candidate search, execution-aware scoring and retention."""
    started = time.perf_counter()
    budget = mission_budget(
        now_s=tick * config.dt,
        mission_end_s=config.duration_s,
        sample_period_s=config.sample_period_s,
        robot_count=config.robot_count,
        max_speed=config.max_speed,
    )
    if previous_budget is not None and not budget.is_successor_of(previous_budget):
        raise RuntimeError("remaining mission budget must never be reset by replanning")
    candidates = _timed_dp_plan(
        gp,
        positions,
        headings,
        grid,
        config,
        tick,
        version,
        failures,
        include_greedy=True,
        backend="execution_aware",
    )
    try:
        plan = manage_plan(
            gp=gp,
            query=grid,
            positions=positions,
            headings=headings,
            budget=budget,
            dp_plan=candidates,
            retained_plan=retained_plan,
            stepper=_nominal_stepper(config, controls),
            start_tick=tick,
            dt=config.dt,
            domain=config.domain,
            min_separation=config.min_separation,
            trigger=trigger,
            plan_version=version,
            settings=_policy_settings(config),
            hold_scope=(
                "static_hold_geometric_check_stopped_curvature_usv_"
                "loiter_invariant_kept_by_the_arc_filter"
                if config.model == "usv_curvature"
                else "static_hold_geometric_check_holonomic_zero_velocity"
            ),
        )
    except (ValueError, FloatingPointError) as error:
        event = {
            "phase": "planning",
            "backend": "execution_aware",
            "tick": tick,
            "time_s": tick * config.dt,
            "success": False,
            "failure_reason": f"{type(error).__name__}: {error}",
            "status": "no_executable_candidate",
            "trigger": trigger,
            "attempted_plan_version": version,
            "positions_before": positions.tolist(),
            "belief_observation_count": gp.observation_count,
            "budget": budget.as_dict(),
            "wall_s": time.perf_counter() - started,
            "claim_limit": (
                "no candidate in this bounded set was executable here; "
                "not a proof that the mission target is unreachable"
            ),
        }
        failures.append(event)
        raise ControlFailure(event) from error
    plan["candidate_search"] = {
        "selected_candidate_id": candidates.get("selected_candidate_id"),
        "candidate_count": len(candidates.get("candidates") or []),
        "planning_wall_s": candidates.get("planning_wall_s"),
        "settings": candidates.get("settings"),
        "scope": candidates.get("planning_scope"),
    }
    plan["planning_wall_s"] = time.perf_counter() - started
    return plan, budget


def run_mapping(config: MappingConfig, method: str) -> dict[str, Any]:
    """Run a mission; rejected controls produce explicit partial failure evidence."""
    return _MissionExecution(config, method).finish()


@dataclass(frozen=True, slots=True)
class _MissionView:
    """Immutable observation of a fully processed physical tick, not a checkpoint."""

    status: Literal["running", "completed", "failed"]
    tick: int
    time_s: float
    positions: tuple[tuple[float, ...], ...]
    headings: tuple[float, ...]
    active_plan_id: str | None
    samples_attempted: int
    samples_received: int
    samples_assimilated: int


class _MissionExecution:
    """Own mission state and expose only complete physical ticks to diagnostic callers.

    Construction closes tick zero. ``read`` observes without predicting or planning,
    ``advance`` closes the next physical tick, and ``finish`` completes the same
    execution path. Views cannot mutate state; artifacts are independent copies.
    Caller pauses while running count in wall runtime, never in simulated time.
    Terminal processing freezes the outcome, including its timing fields.
    """

    def __init__(self, config: MappingConfig, method: str) -> None:
        self.config = config
        self.method = method
        # A nominal preview can fail before the first real observation.
        self.samples: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.motion: list[dict[str, Any]] = []
        self.received = self.attempted = 0
        self.planning_started: float | None = None
        self.active_plan_id: str | None = None
        self.active_plan: dict[str, Any] | None = None
        self.reached_tick = 0
        self.status: Literal["running", "completed", "failed"] = "running"
        self._result: dict[str, Any] | None = None
        try:
            self._start()
            self._process_epoch(0)
        except ControlFailure as exc:
            self._finish_failure(exc)

    def read(self) -> _MissionView:
        """Read immutable diagnostic values without predicting or planning."""
        return _MissionView(
            status=self.status,
            tick=self.reached_tick,
            time_s=self.reached_tick * self.config.dt,
            positions=tuple(tuple(float(value) for value in point) for point in self.positions),
            headings=tuple(float(value) for value in self.headings),
            active_plan_id=self.active_plan_id,
            samples_attempted=self.attempted,
            samples_received=self.received,
            samples_assimilated=self.actual_gp.observation_count,
        )

    def advance(self) -> _MissionView:
        """Execute one physical transition and all existing work due at its tick."""
        if self.status != "running":
            return self.read()
        try:
            self._move()
            if self.reached_tick == self.end_tick:
                if self.reached_tick % self.sample_ticks == 0:
                    self._collect(self.reached_tick, self.segment_path[-1])
                self._process_epoch(self.epoch + 1)
            if self.reached_tick == self.total_ticks:
                self._finalize(self._completed())
        except ControlFailure as exc:
            self._finish_failure(exc)
        return self.read()

    def finish(self) -> dict[str, Any]:
        """Complete once and return an independent copy of the terminal artifact."""
        while self.status == "running":
            self.advance()
        assert self._result is not None
        return deepcopy(self._result)

    def _finish_failure(self, failure: ControlFailure) -> None:
        if self.planning_started is not None:
            self.planning_s += time.perf_counter() - self.planning_started
            self.planning_started = None
        self._finalize(self._failed(failure))

    def _finalize(self, result: dict[str, Any]) -> None:
        result["summary"].update(_control_summary(result["controls"]))
        plans = result.get("plans", [])
        plan_times = [plan["planning_wall_s"] for plan in plans]
        result["summary"].update(
            {
                "plans_generated": len(plans),
                "dp_planning_s": sum(plan_times),
                "dp_planning_median_s": float(np.median(plan_times)) if plan_times else None,
                "dp_planning_p95_s": float(np.quantile(plan_times, 0.95)) if plan_times else None,
                "planning_failures": len(result.get("planning_failures", [])),
                "gp_backend": self.config.gp_backend,
                "gp_failures": len(result.get("gp_failures", [])),
                "samples_assimilated": result["gp_telemetry"]["observation_count"],
                "dp_failed_planning_s": sum(
                    event["wall_s"] for event in result.get("planning_failures", [])
                ),
            }
        )
        self.status = result["status"]
        self._result = result

    def _failed(self, failure: ControlFailure) -> dict[str, Any]:
        """Keep the last actually reached state, never pad a failed mission to its horizon."""
        starts = np.asarray(self.starts, dtype=float)
        motion = self.motion
        if not motion:
            motion = [
                {
                    "time_s": 0.0,
                    "positions": starts.tolist(),
                    "planned_positions": starts.tolist(),
                    "targets": starts.tolist(),
                    "headings": [0.0] * self.config.robot_count,
                    "speeds": [0.0] * self.config.robot_count,
                    "turn_rates": [0.0] * self.config.robot_count,
                    "safety_intervention": False,
                    "segment_min_separation": segment_min_separation(starts, starts),
                    "control_event_index": None,
                    "plan_id": None,
                }
            ]
        samples = self.samples
        reconstruction_started = time.perf_counter()
        # Retain the last committed belief. Replaying received-but-rejected values
        # could repeat a numerical failure or silently assimilate a failed batch.
        gp = self.actual_gp
        received = [sample for sample in samples if sample["received"]]
        field = self.field
        xx, yy = np.meshgrid(field["x"], field["y"])
        prediction = gp.predict(np.column_stack((xx.ravel(), yy.ravel())), variance="latent")
        reconstruction_gp_s = time.perf_counter() - reconstruction_started
        nx, ny = self.config.grid_shape
        mean = prediction.mean.reshape(ny, nx)
        variance = prediction.variance.reshape(ny, nx)
        error = mean - np.asarray(field["truth"])
        route = np.array([state["positions"] for state in motion])
        distances = np.sum(np.linalg.norm(np.diff(route, axis=0), axis=2), axis=0)
        last = motion[-1]
        minimum = min(state["segment_min_separation"] for state in motion)
        frames = list(self.frames)
        final = {
            "time_s": last["time_s"],
            "positions": last["positions"],
            "targets": last["targets"],
            "headings": last["headings"],
            "mean": mean.tolist(),
            "std": np.sqrt(variance).tolist(),
            "error": error.tolist(),
            "rmse": float(np.sqrt(np.mean(error**2))),
            "mean_variance": float(np.mean(variance)),
            "path_length": float(np.sum(distances)),
            "samples_received": len(received),
            "samples_attempted": len(samples),
            "min_separation": minimum,
            # No nominal completion prediction is claimed for a rejected plan.
            "planned_mean_variance": None,
            "plan_id": self.active_plan_id,
            "forecast_plan_id": None,
            "gp_telemetry": _gp_telemetry(gp),
        }
        if frames and frames[-1]["time_s"] == last["time_s"]:
            frames[-1] = final
        else:
            frames.append(final)
        controls = self.controls
        return {
            "schema_version": 1,
            "status": "failed",
            "method": self.method,
            "config": asdict(self.config),
            "failure": {
                "reason": str(failure),
                "phase": failure.event["phase"],
                "tick": failure.event["tick"],
                "time_s": failure.event["time_s"],
                "last_executed_time_s": last["time_s"],
                "details": failure.event,
            },
            "field": field,
            "initial_positions": starts.tolist(),
            "frames": frames,
            "motion": motion,
            "samples": samples,
            "controls": controls,
            "plans": self.plans,
            "plan_events": self.plan_events,
            "planning_failures": self.planning_failures,
            "gp_telemetry": _gp_telemetry(gp),
            "gp_updates": self.gp_updates,
            "gp_failures": self.gp_failures,
            "summary": {
                "rmse": final["rmse"],
                "mean_variance": final["mean_variance"],
                "max_variance": float(np.max(variance)),
                "path_length": final["path_length"],
                "path_length_per_robot": distances.tolist(),
                "samples_received": len(received),
                "samples_attempted": len(samples),
                "samples_lost": len(samples) - len(received),
                "runtime_s": time.perf_counter() - self.started,
                "planning_s": self.planning_s,
                "gp_s": self.gp_s + reconstruction_gp_s,
                "failure_reconstruction_gp_s": reconstruction_gp_s,
                "timing_scope": (
                    "partial mission; GP time includes last committed belief prediction"
                ),
                "min_separation": minimum,
                "max_speed_observed": max(max(m["speeds"]) for m in motion),
                "max_turn_rate_observed": max(max(abs(v) for v in m["turn_rates"]) for m in motion),
                "safety_interventions": sum(m["safety_intervention"] for m in motion),
                "control_interventions": sum(m["safety_intervention"] for m in motion),
                "completion_time_s": last["time_s"],
                "final_planned_mean_variance": None,
                "mean_sample_position_error": float(
                    np.mean(
                        [
                            np.linalg.norm(np.array(s["actual_position"]) - s["planned_position"])
                            for s in samples
                        ]
                    )
                )
                if samples
                else None,
            },
            "seed_manifest": self.seed_manifest,
            "scope": {
                "implementation": "independent; failed partial mission, not a completed result",
                "variance": "latent",
                "safety": "rejected control not applied; no fallback",
                "timing": "all attempted control events retained, including nominal preview",
                "gp": gp.backend_name,
                "gp_update_order": "ascending (sample_tick, robot_id), received samples only",
                "forecast": gp.forecast_scope,
            },
        }

    def _collect(self, tick: int, planned_positions: FloatArray) -> None:
        observed_x, observed_y = [], []
        received_batch: list[dict[str, Any]] = []
        true_values = evaluate_field(self.positions, self.config)
        for robot in range(self.config.robot_count):
            noise = self.config.noise_std * indexed_normal(
                self.manifest.measurement_noise_key, robot, tick
            )
            normal_coin = indexed_normal(self.config.seed, robot, tick, stream="dropout")
            uniform_coin = 0.5 * (1 + math.erf(normal_coin / math.sqrt(2)))
            success = uniform_coin >= self.config.dropout_prob
            value = float(true_values[robot] + noise)
            self.samples.append(
                {
                    "time_s": tick * self.config.dt,
                    "robot_id": robot,
                    "planned_position": planned_positions[robot].tolist(),
                    "actual_position": self.positions[robot].tolist(),
                    "received": success,
                    "assimilated": False,
                    "value": value if success else None,
                    "noise_innovation": noise,
                    "dropout_uniform": uniform_coin,
                    "plan_id": self.active_plan_id,
                }
            )
            self.attempted += 1
            if success:
                self.received += 1
                observed_x.append(self.positions[robot].copy())
                observed_y.append(value)
                received_batch.append(self.samples[-1])
        if observed_y:
            gp_started = time.perf_counter()
            try:
                self.actual_gp.update(np.array(observed_x), np.array(observed_y))
            except FloatingPointError as error:
                event = {
                    "phase": "gp_update",
                    "backend": self.config.gp_backend,
                    "tick": tick,
                    "time_s": tick * self.config.dt,
                    "success": False,
                    "status": "belief_update_rejected",
                    "failure_reason": f"{type(error).__name__}: {error}",
                    "received_sample_keys": [[s["time_s"], s["robot_id"]] for s in received_batch],
                    "belief_observation_count": self.actual_gp.observation_count,
                    "claim_limit": "numerical update failure, not mission impossibility",
                }
                self.gp_failures.append(event)
                raise ControlFailure(event) from error
            finally:
                self.gp_s += time.perf_counter() - gp_started
            for sample in received_batch:
                sample["assimilated"] = True
            if isinstance(self.actual_gp, SparseOnlineGP):
                for sample, event in zip(
                    received_batch, self.actual_gp.last_update_events, strict=True
                ):
                    self.gp_updates.append(
                        {
                            **event,
                            "time_s": tick * self.config.dt,
                            "tick": tick,
                            "robot_id": sample["robot_id"],
                        }
                    )

    def _activate_plan(
        self, plan: dict[str, Any], tick: int, *, execution_metrics: dict[str, float] | None = None
    ) -> FloatArray:
        """Record synchronous activation; callers update their future reference interval."""
        plan["previous_plan_id"] = self.active_plan_id
        plan["start_positions"] = self.positions.tolist()
        plan["belief_telemetry"] = _gp_telemetry(self.actual_gp)
        plan["received_sample_keys"] = [
            [sample["time_s"], sample["robot_id"]] for sample in self.samples if sample["received"]
        ]
        self.plans.append(plan)
        self.active_plan, self.active_plan_id = plan, plan["plan_id"]
        if self.method == "p":
            event = {
                "time_s": tick * self.config.dt,
                "tick": tick,
                "plan_id": self.active_plan_id,
                "previous_plan_id": plan["previous_plan_id"],
                **plan["decision"],
                "target_status": plan["target_risk"]["status"],
                "remaining_sample_epochs": plan["budget"]["remaining_sample_epochs"],
            }
            if execution_metrics is not None:
                event.update(execution_metrics)
            self.plan_events.append(event)
        return (
            np.asarray(plan["targets_by_epoch"][0], dtype=float)
            if plan["sample_times_s"]
            else self.positions.copy()
        )

    def _start(self) -> None:
        """Initialize the mission and receive the original tick-zero observations."""

        if self.method not in AVAILABLE_METHODS:
            raise ValueError(f"method must be one of {AVAILABLE_METHODS}")
        if self.method in PLANNING_METHODS and self.config.model not in PLANNING_MODELS:
            raise ValueError(
                "timed DP and M4 management support holonomic robots and the curvature USV only"
            )
        self.started = time.perf_counter()
        self.planning_s = 0.0
        self.gp_s = 0.0
        self.manifest = derive_seed_manifest(self.config.seed)
        nx, ny = self.config.grid_shape
        x = np.linspace(0, self.config.domain[0], nx)
        y = np.linspace(0, self.config.domain[1], ny)
        xx, yy = np.meshgrid(x, y)
        self.grid = np.column_stack((xx.ravel(), yy.ravel()))
        self.truth = evaluate_field(self.grid, self.config)
        self.positions = initial_positions(self.config)
        self.starts = self.positions.copy()
        self.headings = np.zeros(self.config.robot_count)
        self.total_ticks = round(self.config.duration_s / self.config.dt)
        self.sample_ticks = round(self.config.sample_period_s / self.config.dt)
        epoch_ticks = list(range(0, self.total_ticks + 1, self.sample_ticks))
        # A non-sampling-aligned horizon still receives a final visualisation, but no
        # extra sensor event: every method has exactly the same physical sample clock.
        self.boundaries = sorted(set([*epoch_ticks, self.total_ticks]))
        self.actual_gp = _new_gp(self.config)
        self.controls: list[dict[str, Any]] = []
        self.plans: list[dict[str, Any]] = []
        self.planning_failures: list[dict[str, Any]] = []
        self.gp_updates: list[dict[str, Any]] = []
        self.gp_failures: list[dict[str, Any]] = []
        self.active_plan_id = None
        self.active_plan = None
        self.plan_budget: MissionBudget | None = None
        self.plan_events: list[dict[str, Any]] = []
        self.forecast_plan_ids: dict[int, str] = {}
        self.field = {
            "x": x.tolist(),
            "y": y.tolist(),
            "truth": self.truth.reshape(ny, nx).tolist(),
        }
        self.seed_manifest = {
            **self.manifest.as_dict(),
            "dropout_key": self.config.seed,
            "motion_key": self.config.seed,
        }
        self.static_paths: dict[int, FloatArray] = {0: self.positions.copy()}
        self.static_goals: dict[int, FloatArray] = {}
        self.expected_variance: dict[int, float] = {}
        if self.method in ("sweep", "greedy"):
            self.planning_started = time.perf_counter()
            # B0/B1 are open-loop nominal baselines. Their covariance-only route
            # design uses the same fixed exact prior surrogate for both estimators.
            # Zero labels here never enter the real SOGP or its label-dependent
            # pruning. Only B2/B3 use the current received-data posterior to replan.
            nominal_gp = ExactGP(
                length_scale=self.config.length_scale,
                signal_variance=self.config.signal_variance,
                noise_variance=self.config.noise_std**2,
            )
            nominal_gp.update(self.positions, np.zeros(self.config.robot_count))
            self.expected_variance[0] = float(
                np.mean(nominal_gp.predict(self.grid, variance="latent").variance)
            )
            nominal_positions, nominal_headings = self.positions.copy(), self.headings.copy()
            routes = _sweep_routes(self.config, self.positions) if self.method == "sweep" else None
            route_indices = [0] * self.config.robot_count
            for start_tick, end_tick in zip(self.boundaries[:-1], self.boundaries[1:], strict=True):
                self.end_tick = end_tick
                steps = self.end_tick - start_tick
                targets = (
                    _select_targets(
                        nominal_gp,
                        nominal_positions,
                        nominal_headings,
                        self.grid,
                        self.config,
                        steps,
                    )
                    if self.method == "greedy"
                    else nominal_positions.copy()
                )
                path, goals, nominal_headings = _preview(
                    nominal_positions,
                    nominal_headings,
                    targets,
                    self.config,
                    start_tick,
                    steps,
                    routes=routes,
                    route_indices=route_indices,
                    control_events=self.controls,
                )
                for offset, point in enumerate(path):
                    self.static_paths[start_tick + offset] = point
                for offset, goal in enumerate(goals):
                    self.static_goals[start_tick + offset] = goal
                nominal_positions = path[-1]
                if self.end_tick % self.sample_ticks == 0:
                    nominal_gp.update(nominal_positions, np.zeros(self.config.robot_count))
                self.expected_variance[self.end_tick] = float(
                    np.mean(nominal_gp.predict(self.grid, variance="latent").variance)
                )
            self.planning_s += time.perf_counter() - self.planning_started
            self.planning_started = None

        self.interventions = 0
        self.distance_travelled = np.zeros(self.config.robot_count)
        self.minimum_separation = segment_min_separation(self.positions, self.positions)
        self.max_speed_observed = self.max_turn_observed = 0.0
        self.previous_targets = self.positions.copy()

        self._collect(0, self.positions)

    def _process_epoch(self, epoch: int) -> None:
        """Close prediction, outgoing planning, and frame recording at a boundary."""
        nx, ny = self.config.grid_shape
        self.epoch, self.tick = epoch, self.boundaries[epoch]
        gp_started = time.perf_counter()
        prediction = self.actual_gp.predict(self.grid, variance="latent")
        self.gp_s += time.perf_counter() - gp_started
        variance = np.maximum(prediction.variance, 0)
        error = prediction.mean - self.truth
        rmse = float(np.sqrt(np.mean(error**2)))
        self.segment_path: list[FloatArray] = []
        self.segment_goals: list[FloatArray] = []
        if self.epoch < len(self.boundaries) - 1:
            self.end_tick = self.boundaries[self.epoch + 1]
            steps = self.end_tick - self.tick
            if self.method in PLANNING_METHODS:
                self.planning_started = time.perf_counter()
                if self.method == "p":
                    epoch_time = self.tick * self.config.dt
                    lost_here = any(
                        not sample["received"]
                        and math.isclose(sample["time_s"], epoch_time, rel_tol=0, abs_tol=1e-9)
                        for sample in self.samples
                    )
                    trigger = (
                        "initial"
                        if self.active_plan is None
                        else "missed_measurement"
                        if lost_here
                        else "periodic_sampling_epoch"
                    )
                    plan, self.plan_budget = _managed_plan(
                        self.actual_gp,
                        self.positions,
                        self.headings,
                        self.grid,
                        self.config,
                        self.tick,
                        len(self.plans),
                        self.planning_failures,
                        retained_plan=self.active_plan,
                        trigger=trigger,
                        controls=self.controls,
                        previous_budget=self.plan_budget,
                    )
                else:
                    plan = _timed_dp_plan(
                        self.actual_gp,
                        self.positions,
                        self.headings,
                        self.grid,
                        self.config,
                        self.tick,
                        len(self.plans),
                        self.planning_failures,
                    )
                    plan["replacement_reason"] = "periodic_sampling_epoch"
                targets = self._activate_plan(plan, self.tick)
                # Both planners execute the geometric schedule toward the commanded
                # cell. Only P *scores* candidates at rolled-out arrival positions;
                # the actual QP and disturbance can still miss either.
                self.segment_path = _reference_path(
                    self.positions, self.headings, targets, steps, self.config
                )
                self.segment_goals = [targets.copy() for _ in range(steps)]
                self.expected_variance[self.end_tick] = (
                    float(plan["forecast"][1]["mean_variance"])
                    if plan["sample_times_s"]
                    else float(np.mean(variance))
                )
                if plan["sample_times_s"]:
                    self.forecast_plan_ids[self.end_tick] = plan["plan_id"]
                self.planning_s += time.perf_counter() - self.planning_started
                self.planning_started = None
            elif self.method == "adaptive":
                self.planning_started = time.perf_counter()
                targets = _select_targets(
                    self.actual_gp, self.positions, self.headings, self.grid, self.config, steps
                )
                self.segment_path, self.segment_goals, _ = _preview(
                    self.positions,
                    self.headings,
                    targets,
                    self.config,
                    self.tick,
                    steps,
                    control_events=self.controls,
                )
                if self.end_tick % self.sample_ticks == 0:
                    self.expected_variance[self.end_tick] = float(
                        np.mean(self.actual_gp.fantasy_variance(self.grid, self.segment_path[-1]))
                    )
                else:
                    self.expected_variance[self.end_tick] = float(np.mean(variance))
                self.planning_s += time.perf_counter() - self.planning_started
                self.planning_started = None
            else:
                self.segment_path = [
                    self.static_paths[t] for t in range(self.tick, self.end_tick + 1)
                ]
                self.segment_goals = [self.static_goals[t] for t in range(self.tick, self.end_tick)]
            self.previous_targets = self.segment_goals[0]
        self.frames.append(
            {
                "time_s": self.tick * self.config.dt,
                "positions": self.positions.tolist(),
                "targets": self.previous_targets.tolist(),
                "headings": self.headings.tolist(),
                "mean": prediction.mean.reshape(ny, nx).tolist(),
                "std": np.sqrt(variance).reshape(ny, nx).tolist(),
                "error": error.reshape(ny, nx).tolist(),
                "rmse": rmse,
                "mean_variance": float(np.mean(variance)),
                "path_length": float(np.sum(self.distance_travelled)),
                "samples_received": self.received,
                "samples_attempted": self.attempted,
                "min_separation": self.minimum_separation,
                "planned_mean_variance": self.expected_variance.get(
                    self.tick, float(np.mean(variance))
                ),
                "plan_id": self.active_plan_id,
                "forecast_plan_id": self.forecast_plan_ids.get(self.tick),
                "gp_telemetry": _gp_telemetry(self.actual_gp),
            }
        )
        if self.tick == 0:
            self.motion.append(
                {
                    "time_s": 0.0,
                    "planned_positions": self.starts.tolist(),
                    "positions": self.positions.tolist(),
                    "targets": self.previous_targets.tolist(),
                    "headings": self.headings.tolist(),
                    "speeds": [0.0] * self.config.robot_count,
                    "turn_rates": [0.0] * self.config.robot_count,
                    "safety_intervention": False,
                    "segment_min_separation": self.minimum_separation,
                    "control_event_index": None,
                    "plan_id": None,
                }
            )

    def _move(self) -> None:
        """Record accepted motion before any existing interior P decision."""
        offset = self.reached_tick - self.tick
        targets = self.segment_goals[offset]
        self.next_tick = self.reached_tick + 1
        next_positions, next_headings, intervention, separation, turn_rates = _advance(
            self.positions,
            self.headings,
            targets,
            self.config,
            self.next_tick,
            disturbed=True,
            control_events=self.controls,
            phase="execution",
            tracking_time_s=(
                (self.end_tick - self.next_tick + 1) * self.config.dt
                if self.method in PLANNING_METHODS
                else None
            ),
            plan_id=self.active_plan_id,
        )
        movement = np.linalg.norm(next_positions - self.positions, axis=1)
        self.distance_travelled += movement
        speeds = movement / self.config.dt
        self.max_speed_observed = max(self.max_speed_observed, float(np.max(speeds)))
        self.max_turn_observed = max(self.max_turn_observed, float(np.max(np.abs(turn_rates))))
        self.minimum_separation = min(self.minimum_separation, separation)
        self.interventions += int(intervention)
        self.positions, self.headings = next_positions, next_headings
        self.reached_tick = self.next_tick
        self.motion.append(
            {
                "time_s": self.next_tick * self.config.dt,
                "planned_positions": self.segment_path[offset + 1].tolist(),
                "positions": self.positions.tolist(),
                "targets": targets.tolist(),
                "headings": self.headings.tolist(),
                "speeds": speeds.tolist(),
                "turn_rates": turn_rates.tolist(),
                "safety_intervention": intervention,
                "segment_min_separation": separation,
                "control_event_index": len(self.controls) - 1,
                "plan_id": self.active_plan_id,
            }
        )
        # Event-triggered management (§9.3): re-decide inside the interval when
        # execution has already diverged, instead of waiting for the next epoch.
        if self.method == "p" and self.config.p_event_triggers and self.next_tick < self.end_tick:
            deviation = float(
                np.max(np.linalg.norm(self.positions - self.segment_path[offset + 1], axis=1))
            )
            # A *significant* intervention, not any constraint-layer adjustment:
            # the QP nudges almost every command, so the boolean flag would
            # re-decide on numerical noise rather than on real execution loss.
            applied = self.controls[-1]["applied_velocity"]
            correction = (
                float(
                    np.max(
                        np.linalg.norm(
                            np.asarray(applied, dtype=float)
                            - np.asarray(self.controls[-1]["requested_velocity"], dtype=float),
                            axis=1,
                        )
                    )
                )
                if applied is not None
                else 0.0
            )
            event_trigger = (
                "control_intervention"
                if correction > self.config.p_intervention_trigger_mps
                else "execution_deviation"
                if deviation > self.config.p_deviation_trigger_m
                else None
            )
            if event_trigger is not None:
                self.planning_started = time.perf_counter()
                plan, self.plan_budget = _managed_plan(
                    self.actual_gp,
                    self.positions,
                    self.headings,
                    self.grid,
                    self.config,
                    self.next_tick,
                    len(self.plans),
                    self.planning_failures,
                    retained_plan=self.active_plan,
                    trigger=event_trigger,
                    controls=self.controls,
                    previous_budget=self.plan_budget,
                )
                new_targets = self._activate_plan(
                    plan,
                    self.next_tick,
                    execution_metrics={
                        "deviation_m": deviation,
                        "control_correction_mps": correction,
                    },
                )
                remaining_steps = self.end_tick - self.next_tick
                reference = _reference_path(
                    self.positions, self.headings, new_targets, remaining_steps, self.config
                )
                for index in range(remaining_steps):
                    self.segment_goals[offset + 1 + index] = new_targets.copy()
                    self.segment_path[offset + 2 + index] = reference[index + 1]
                if plan["sample_times_s"]:
                    self.expected_variance[self.end_tick] = float(
                        plan["forecast"][1]["mean_variance"]
                    )
                    self.forecast_plan_ids[self.end_tick] = plan["plan_id"]
                self.planning_s += time.perf_counter() - self.planning_started
                self.planning_started = None

    def _completed(self) -> dict[str, Any]:
        final = self.frames[-1]
        final_variance = np.square(np.asarray(final["std"]))
        sample_errors = [
            np.linalg.norm(np.asarray(sample["actual_position"]) - sample["planned_position"])
            for sample in self.samples
        ]
        summary = {
            "rmse": final["rmse"],
            "mean_variance": final["mean_variance"],
            "max_variance": float(np.max(final_variance)),
            "path_length": float(np.sum(self.distance_travelled)),
            "path_length_per_robot": self.distance_travelled.tolist(),
            "samples_received": self.received,
            "samples_attempted": self.attempted,
            "samples_lost": self.attempted - self.received,
            "runtime_s": time.perf_counter() - self.started,
            "planning_s": self.planning_s,
            "gp_s": self.gp_s,
            "min_separation": self.minimum_separation,
            "max_speed_observed": self.max_speed_observed,
            "max_turn_rate_observed": self.max_turn_observed,
            "safety_interventions": self.interventions,
            "mean_sample_position_error": float(np.mean(sample_errors)),
            "final_planned_mean_variance": final["planned_mean_variance"],
            "completion_time_s": self.config.duration_s,
            "control_interventions": self.interventions,
        }
        return {
            "schema_version": 1,
            "status": "completed",
            "failure": None,
            "method": self.method,
            "config": asdict(self.config),
            "field": self.field,
            "initial_positions": self.starts.tolist(),
            "frames": self.frames,
            "motion": self.motion,
            "samples": self.samples,
            "summary": summary,
            "controls": self.controls,
            "plans": self.plans,
            "plan_events": self.plan_events,
            "planning_failures": self.planning_failures,
            "gp_telemetry": _gp_telemetry(self.actual_gp),
            "gp_updates": self.gp_updates,
            "gp_failures": self.gp_failures,
            "seed_manifest": {
                **self.manifest.as_dict(),
                "dropout_key": self.config.seed,
                "motion_key": self.config.seed,
            },
            "scope": {
                "implementation": "independent application; not paper reproduction",
                "variance": "latent",
                "gp": f"{self.config.gp_backend}, fixed hyperparameters; finite evaluation grid",
                "gp_update_order": "ascending (sample_tick, robot_id), received samples only",
                "forecast": (
                    "fixed_exact_prior_nominal_route_surrogate_not_future_sogp"
                    if self.method in ("sweep", "greedy") and self.config.gp_backend == "sogp"
                    else self.actual_gp.forecast_scope
                ),
                "greedy": (
                    "open-loop nominal-information route; assumes all scheduled samples succeed"
                ),
                "adaptive": "replans from executed positions and received data at sample epochs",
                "safety": (
                    "independent holonomic tracking QP: CBF plus segment-separating constraints; "
                    "hard inscribed speed polygon; numerical postchecks, no physical certificate"
                    if self.config.controller == "qp"
                    else "sampled piecewise-linear motion checked by common "
                    "displacement backtracking"
                ),
                "usv": (
                    "turn-rate-limited kinematic unicycle; zero-speed yaw allowed; no hydrodynamics"
                ),
                "disturbance": (
                    "drift_strength: velocity tracking-command std m/s for holonomic, "
                    "capped before "
                    "constraint control; yaw-rate std rad/s for USV; no unmodeled post-control wind"
                ),
                "planning": (
                    "M2 periodic timed DP: frozen-reward Bellman candidates, "
                    "joint GP final scoring; "
                    "actual posterior and remaining sample budget, no controller candidate rollout"
                    if self.method == "dp"
                    else "M4 execution-aware management: Bellman/greedy/retained/hold candidates "
                    "re-scored through a nominal controller rollout over equal remaining epochs"
                    if self.method == "p"
                    else "finite targets; USV endpoint rollouts; joint sequential fantasy gains"
                ),
                "planned_variance": (
                    "geometric scheduled sites with all future measurements received; "
                    "one selected joint-plan prefix, not guaranteed QP attainment"
                    if self.method == "dp"
                    else "rolled-out arrival sites with all future measurements received; "
                    "mission-end value uses an executable hold continuation and is an upper "
                    "candidate, never an attainability floor"
                    if self.method == "p"
                    else "nominal receipt at previewed endpoints; not a guarantee"
                ),
            },
        }
