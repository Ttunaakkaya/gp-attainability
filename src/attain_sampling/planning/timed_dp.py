"""Bounded, independent coarse Bellman candidate generation for M2.

The deterministic surrogate state is (cell, remaining sample epochs). Rewards
are frozen single-sample integrated latent-variance reductions, normalized by
the GP signal variance; travel is measured in metres and normalized by the
whole team's available travel over this planning horizon. Backward Bellman
recursion solves that surrogate, *not* the GP belief-MDP. Earlier robots' routes
condition later robots' rewards, and several robot orders are searched.

Final ranking uses joint conditional variance of chronological multi-robot samples,
never the sum of frozen rewards. With SOGP this freezes the current approximate
posterior, not future pruning. Travel breaks variance ties only.
Nominal straight-line reachability/separation checks do not include the QP,
future disturbances, USV dynamics, or a guarantee of task attainability.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from numbers import Integral, Real
from typing import Any

import numpy as np

from attain_sampling.gp.protocol import CovarianceBelief, FloatArray
from attain_sampling.planning.clock import remaining_sample_times

_GEOMETRY_TOLERANCE = 1e-7
# (rewards, travel_cost, feasible, start_node) -> (route, surrogate value or None)
_RouteSearch = Callable[
    [FloatArray, FloatArray, np.ndarray, int], tuple[list[int] | None, float | None]
]


def _real(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _integer(value: Any, name: str, lower: int, upper: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if not lower <= result <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return result


@dataclass(frozen=True, slots=True)
class DPSettings:
    """Explicit search bounds; no hidden training or combinatorial team search."""

    horizon_steps: int = 4
    grid_shape: tuple[int, int] = (9, 7)
    travel_weight: float = 0.01
    include_greedy_candidates: bool = False

    def __post_init__(self) -> None:
        horizon = _integer(self.horizon_steps, "horizon_steps", 1, 16)
        if not isinstance(self.grid_shape, (tuple, list)) or len(self.grid_shape) != 2:
            raise ValueError("grid_shape must contain two integers")
        shape = tuple(_integer(size, "grid_shape entry", 2, 200) for size in self.grid_shape)
        if shape[0] * shape[1] > 400:
            raise ValueError("grid_shape must have at most 400 cells")
        weight = _real(self.travel_weight, "travel_weight")
        if not isinstance(self.include_greedy_candidates, bool):
            raise ValueError("include_greedy_candidates must be a boolean")
        object.__setattr__(self, "horizon_steps", horizon)
        object.__setattr__(self, "grid_shape", shape)
        object.__setattr__(self, "travel_weight", weight)


_DEFAULT_SETTINGS = DPSettings()


def _points(value: Any, name: str) -> FloatArray:
    raw = np.asarray(value)
    if np.iscomplexobj(raw) or raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must contain real coordinates")
    result = np.asarray(raw, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 2 or not len(result):
        raise ValueError(f"{name} must have nonempty shape (n, 2)")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain finite coordinates")
    return result.copy()


def _sample_times(now: float, end: float, period: float, horizon: int) -> list[float]:
    """Global clock epochs only: an off-grid mission end is never a new sample.

    The enumeration itself lives in :mod:`attain_sampling.planning.clock` so the
    M4 remaining-mission budget reads exactly the same epochs as this horizon.
    """
    return remaining_sample_times(now, end, period, limit=horizon)


def _robot_orders(robot_count: int, plan_version: int) -> list[list[int]]:
    orders: list[list[int]] = []
    for rotation in (plan_version % robot_count, (plan_version + 1) % robot_count):
        forward = [(rotation + index) % robot_count for index in range(robot_count)]
        for order in (forward, forward[::-1]):
            if order not in orders:
                orders.append(order)
    return orders


def _grid(domain: FloatArray, shape: tuple[int, int]) -> tuple[FloatArray, np.ndarray]:
    nx, ny = shape
    x, y = np.meshgrid(np.linspace(0, domain[0], nx), np.linspace(0, domain[1], ny))
    nodes = np.column_stack((x.ravel(), y.ravel()))
    indices = np.column_stack(np.unravel_index(np.arange(nx * ny), (ny, nx)))
    # Includes stay. Non-neighbor grid jumps are not enabled even when reachable.
    adjacency = np.max(np.abs(indices[:, None] - indices[None, :]), axis=2) <= 1
    return nodes, adjacency


def _bellman(
    rewards: FloatArray,
    travel_cost: FloatArray,
    feasible: np.ndarray,
    start_node: int,
) -> tuple[list[int] | None, float | None]:
    """Backward finite-horizon recursion, with deterministic low-index ties.

    J[t,i] = max_j(reward[j] - cost[i,j] + J[t+1,j]); J[H,i] = 0.
    The feasible transition relation may depend on the epoch due to already
    assigned robots' reservations. An empty search is not an impossibility claim.
    """
    horizon, node_count, _ = feasible.shape
    value = np.zeros(node_count, dtype=np.float64)
    policy = np.full((horizon, node_count), -1, dtype=np.int64)
    for epoch in range(horizon - 1, -1, -1):
        scores = rewards[None, :] - travel_cost + value[None, :]
        scores = np.where(feasible[epoch], scores, -np.inf)
        choices = np.argmax(scores, axis=1)
        value = scores[np.arange(node_count), choices]
        policy[epoch] = np.where(np.isfinite(value), choices, -1)
    if not np.isfinite(value[start_node]):
        return None, None
    path: list[int] = []
    node = start_node
    for epoch in range(horizon):
        node = int(policy[epoch, node])
        if node < 0:
            raise RuntimeError("Bellman policy contains an unreachable selected state")
        path.append(node)
    return path, float(value[start_node])


def _greedy_path(
    rewards: FloatArray,
    travel_cost: FloatArray,
    feasible: np.ndarray,
    start_node: int,
) -> tuple[list[int] | None, float | None]:
    """Myopic one-step route over the *same* frozen surrogate as :func:`_bellman`.

    Rewards stay frozen along the robot's own route exactly as in the Bellman
    search, so the only difference between the two candidates is the absence of
    lookahead. M4 needs that separation to tell the value of the planning horizon
    apart from the value of execution-aware plan management. There is no Bellman
    value to report, and an empty search is not an impossibility claim.
    """
    horizon, _, _ = feasible.shape
    path: list[int] = []
    node = start_node
    for epoch in range(horizon):
        scores = np.where(feasible[epoch, node], rewards - travel_cost[node], -np.inf)
        choice = int(np.argmax(scores))
        if not np.isfinite(scores[choice]):
            return None, None
        node = choice
        path.append(node)
    return path, None


def _transition_masks(
    nodes: FloatArray,
    grid_adjacency: np.ndarray,
    robot: int,
    starts: FloatArray,
    assigned: dict[int, list[int]],
    durations: FloatArray,
    max_speed: float,
    min_separation: float,
) -> np.ndarray:
    grid_count = len(grid_adjacency)
    node_count = len(nodes)
    own_start = grid_count + robot
    displacement = nodes[None, :, :] - nodes[:, None, :]
    distance = np.linalg.norm(displacement, axis=2)
    adjacency = np.zeros((node_count, node_count), dtype=bool)
    adjacency[:grid_count, :grid_count] = grid_adjacency
    # The actual start has reachable connectors, not an artificial snap to grid.
    adjacency[own_start, :grid_count] = True
    adjacency[:grid_count, own_start] = True
    adjacency[own_start, own_start] = True
    feasible = np.asarray(
        adjacency[None] & (distance[None] <= max_speed * durations[:, None, None] + 1e-12)
    )
    for earlier, earlier_path in assigned.items():
        previous = starts[earlier]
        for epoch, target_index in enumerate(earlier_path):
            target = nodes[target_index]
            relative_start = nodes[:, None, :] - previous
            relative_delta = displacement - (target - previous)
            denominator = np.sum(relative_delta * relative_delta, axis=2)
            numerator = -np.sum(relative_start * relative_delta, axis=2)
            fraction = np.divide(
                numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0
            )
            closest = relative_start + np.clip(fraction, 0, 1)[:, :, None] * relative_delta
            separation = np.linalg.norm(closest, axis=2)
            feasible[epoch] &= separation >= min_separation - _GEOMETRY_TOLERANCE
            previous = target
    return feasible


def _condition_nodes(
    covariance: FloatArray, cross: FloatArray, node: int, noise: float, signal: float
) -> None:
    denominator = float(covariance[node, node] + noise)
    if not math.isfinite(denominator) or denominator <= 0:
        raise FloatingPointError("non-positive conditional noisy sample variance")
    column = covariance[:, node].copy()
    query_column = cross[:, node].copy()
    cross -= np.outer(query_column, column) / denominator
    covariance -= np.outer(column, column) / denominator
    covariance[:] = (covariance + covariance.T) * 0.5
    diagonal = np.diag(covariance).copy()
    if (
        not np.all(np.isfinite(cross))
        or not np.all(np.isfinite(covariance))
        or np.any(diagonal < -1e-8 * signal)
    ):
        raise FloatingPointError("non-finite or materially negative conditioned covariance")
    np.fill_diagonal(covariance, np.maximum(diagonal, 0))


def _nominal_checks(
    starts: FloatArray,
    targets: FloatArray,
    durations: FloatArray,
    domain: FloatArray,
    max_speed: float,
    min_separation: float,
) -> dict[str, Any]:
    previous = starts
    minimum: float | None = None
    peak_speed = 0.0
    bounds_violation = float(max(0.0, -np.min(starts), np.max(starts - domain)))
    for epoch, positions in enumerate(targets):
        motion = positions - previous
        peak_speed = max(
            peak_speed, float(np.max(np.linalg.norm(motion, axis=1) / durations[epoch]))
        )
        bounds_violation = max(
            bounds_violation, float(-np.min(positions)), float(np.max(positions - domain))
        )
        for first in range(len(starts)):
            for second in range(first + 1, len(starts)):
                relative = previous[first] - previous[second]
                delta = motion[first] - motion[second]
                denominator = float(delta @ delta)
                fraction = (
                    float(np.clip(-(relative @ delta) / denominator, 0, 1)) if denominator else 0.0
                )
                distance = float(np.linalg.norm(relative + fraction * delta))
                minimum = distance if minimum is None else min(minimum, distance)
        previous = positions
    if minimum is None and len(starts) > 1:
        minimum = min(
            float(np.linalg.norm(starts[first] - starts[second]))
            for first in range(len(starts))
            for second in range(first + 1, len(starts))
        )
    separation_violation = max(0.0, min_separation - minimum) if minimum is not None else 0.0
    speed_violation = max(0.0, peak_speed - max_speed)
    return {
        "accepted": bool(
            max(bounds_violation, separation_violation, speed_violation) <= _GEOMETRY_TOLERANCE
        ),
        "scope": "nominal_synchronized_straight_segments_without_controller_rollout",
        "geometry_tolerance_m": _GEOMETRY_TOLERANCE,
        "speed_tolerance_mps": _GEOMETRY_TOLERANCE,
        "max_speed_mps": peak_speed,
        "max_speed_violation_mps": speed_violation,
        "max_bounds_violation_m": bounds_violation,
        "min_pair_distance_m": minimum,
        "max_separation_violation_m": separation_violation,
    }


def plan_timed_dp(
    gp: CovarianceBelief,
    positions: FloatArray,
    query: FloatArray,
    *,
    domain: tuple[float, float],
    max_speed: float,
    min_separation: float,
    sample_period_s: float,
    now_s: float,
    mission_end_s: float,
    plan_version: int,
    settings: DPSettings = _DEFAULT_SETTINGS,
    grid_inset: float = 0.0,
) -> dict[str, Any]:
    """Plan from received-data belief and actual positions, without mutating either.

    Return a JSON-safe time-stamped joint plan and current/all-prefix forecasts.
    Every future sample is assumed received at its nominal location. The horizon
    is bounded and may end before the common mission deadline; no continuation
    to the deadline is silently invented. Final ranking is terminal mean latent
    variance with normalized travel used only within 1e-10 * signal_variance.
    """
    started = time.perf_counter()
    if not isinstance(settings, DPSettings):
        raise ValueError("settings must be DPSettings")
    starts = _points(positions, "positions")
    queries = _points(query, "query")
    if len(starts) > 4:
        raise ValueError("the bounded M2 planner supports one to four robots")
    raw_domain = np.asarray(domain)
    if raw_domain.shape != (2,):
        raise ValueError("domain must contain two positive side lengths")
    bounds = np.asarray([_real(value, "domain entry", positive=True) for value in domain])
    speed = _real(max_speed, "max_speed", positive=True)
    separation = _real(min_separation, "min_separation")
    period = _real(sample_period_s, "sample_period_s", positive=True)
    now = _real(now_s, "now_s")
    end = _real(mission_end_s, "mission_end_s")
    version = _integer(plan_version, "plan_version", 0, 2**53 - 1)
    inset = _real(grid_inset, "grid_inset")
    if np.any(bounds <= 2 * inset):
        raise ValueError("grid_inset leaves no room for planning cells")
    if end < now:
        raise ValueError("mission_end_s must not precede now_s")
    if np.any(starts < -_GEOMETRY_TOLERANCE) or np.any(starts > bounds + _GEOMETRY_TOLERANCE):
        raise ValueError("actual positions lie outside the domain tolerance")
    for first in range(len(starts)):
        for second in range(first + 1, len(starts)):
            if np.linalg.norm(starts[first] - starts[second]) < separation - _GEOMETRY_TOLERANCE:
                raise ValueError("actual positions violate the initial separation tolerance")
    if not math.isfinite(speed * period):
        raise ValueError("per-epoch travel budget must be finite")
    times = _sample_times(now, end, period, settings.horizon_steps)
    durations = np.diff(np.asarray([now, *times], dtype=np.float64))
    current = gp.predict(queries, variance="latent").variance
    current_mean = float(np.mean(current))
    current_max = float(np.max(current))
    if not math.isfinite(current_mean) or not math.isfinite(current_max):
        raise FloatingPointError("GP current latent variance must be finite")
    forecast = [{"time_s": now, "mean_variance": current_mean, "max_variance": current_max}]
    candidates: list[dict[str, Any]] = []
    chosen_targets = np.empty((0, len(starts), 2), dtype=np.float64)
    chosen_checks = _nominal_checks(starts, chosen_targets, durations, bounds, speed, separation)
    selected: str | None = None
    covariance_started = time.perf_counter()
    covariance_wall = 0.0
    if times:
        grid, grid_adjacency = _grid(bounds - 2 * inset, settings.grid_shape)
        grid = grid + inset
        nodes = np.vstack((grid, starts))
        base_covariance = gp.posterior_covariance(nodes)
        base_cross = gp.posterior_covariance(queries, nodes)
        covariance_wall = time.perf_counter() - covariance_started
        total_travel_budget = len(starts) * speed * (times[-1] - now)
        if not math.isfinite(total_travel_budget) or total_travel_budget <= 0:
            raise ValueError("planning travel budget must be positive and finite")
        pair_distances = np.linalg.norm(nodes[:, None] - nodes[None, :], axis=2)
        travel_cost = settings.travel_weight * pair_distances / total_travel_budget
        if not np.all(np.isfinite(travel_cost)):
            raise ValueError("normalized Bellman travel cost must be finite")
        raw_candidates: list[tuple[str, str, list[int], FloatArray, list[float | None], float]] = []
        searches: list[tuple[str, str, _RouteSearch]] = [
            ("bellman", "frozen_reward_bellman", _bellman)
        ]
        if settings.include_greedy_candidates:
            searches.append(("greedy", "frozen_reward_greedy", _greedy_path))
        for prefix, generator, search in searches:
            for order_index, order in enumerate(_robot_orders(len(starts), version)):
                candidate_started = time.perf_counter()
                covariance, cross = base_covariance.copy(), base_cross.copy()
                assigned: dict[int, list[int]] = {}
                surrogate_values: list[float | None] = [None] * len(starts)
                candidate_id = f"{prefix}-order-{order_index}"
                for robot in order:
                    denominator = np.diag(covariance) + gp.noise_variance + gp.jitter
                    if np.any(denominator <= 0) or not np.all(np.isfinite(denominator)):
                        raise FloatingPointError("invalid noisy node variance for Bellman rewards")
                    rewards = np.mean(cross * cross, axis=0) / denominator / gp.signal_variance
                    if not np.all(np.isfinite(rewards)):
                        raise FloatingPointError("non-finite Bellman information rewards")
                    feasible = _transition_masks(
                        nodes, grid_adjacency, robot, starts, assigned, durations, speed, separation
                    )
                    path, value = search(rewards, travel_cost, feasible, len(grid) + robot)
                    if path is None:
                        candidates.append(
                            {
                                "candidate_id": candidate_id,
                                "generator": generator,
                                "robot_order": order,
                                "status": "rejected",
                                "rejection_reason": (
                                    "no_route_in_this_ordered_coarse_reservation_search"
                                ),
                                "failed_robot": robot,
                                "selected": False,
                                "generation_wall_s": time.perf_counter() - candidate_started,
                            }
                        )
                        break
                    assigned[robot] = path
                    surrogate_values[robot] = value
                    for index in path:
                        _condition_nodes(
                            covariance,
                            cross,
                            index,
                            gp.noise_variance + gp.jitter,
                            gp.signal_variance,
                        )
                else:
                    targets = np.asarray(
                        [
                            [nodes[assigned[robot][epoch]] for robot in range(len(starts))]
                            for epoch in range(len(times))
                        ]
                    )
                    raw_candidates.append(
                        (
                            candidate_id,
                            generator,
                            order,
                            targets,
                            surrogate_values,
                            time.perf_counter() - candidate_started,
                        )
                    )
        raw_candidates.append(
            (
                "nominal-hold",
                "nominal_hold",
                [],
                np.repeat(starts[None], len(times), axis=0),
                [],
                0.0,
            )
        )
        for (
            candidate_id,
            generator,
            order,
            targets,
            surrogate_values,
            generation_wall,
        ) in raw_candidates:
            evaluation_started = time.perf_counter()
            checks = _nominal_checks(starts, targets, durations, bounds, speed, separation)
            if not checks["accepted"]:
                raise FloatingPointError("generated plan failed independent nominal geometry check")
            terminal = gp.fantasy_variance(queries, targets.reshape(-1, 2))
            movements = np.diff(np.concatenate((starts[None], targets)), axis=0)
            travel = float(np.sum(np.linalg.norm(movements, axis=2)))
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "generator": generator,
                    "robot_order": order,
                    "status": "accepted",
                    "rejection_reason": None,
                    "selected": False,
                    "surrogate_values_by_robot": surrogate_values,
                    "terminal_mean_variance": float(np.mean(terminal)),
                    "terminal_max_variance": float(np.max(terminal)),
                    "joint_information_gain": current_mean - float(np.mean(terminal)),
                    "travel_m": travel,
                    "normalized_travel": travel / total_travel_budget,
                    "targets_by_epoch": targets.tolist(),
                    "nominal_checks": checks,
                    "generation_wall_s": generation_wall,
                    "joint_evaluation_wall_s": time.perf_counter() - evaluation_started,
                }
            )
        accepted = [candidate for candidate in candidates if candidate["status"] == "accepted"]
        minimum_variance = min(candidate["terminal_mean_variance"] for candidate in accepted)
        tied = [
            candidate
            for candidate in accepted
            if candidate["terminal_mean_variance"] <= minimum_variance + 1e-10 * gp.signal_variance
        ]
        chosen = min(
            tied, key=lambda candidate: (candidate["normalized_travel"], candidate["candidate_id"])
        )
        chosen["selected"] = True
        selected = chosen["candidate_id"]
        chosen_targets = np.asarray(chosen["targets_by_epoch"], dtype=np.float64)
        chosen_checks = chosen["nominal_checks"]
        for epoch, sample_time in enumerate(times):
            variance = gp.fantasy_variance(queries, chosen_targets[: epoch + 1].reshape(-1, 2))
            forecast.append(
                {
                    "time_s": sample_time,
                    "mean_variance": float(np.mean(variance)),
                    "max_variance": float(np.max(variance)),
                }
            )
    identity = {
        "plan_version": version,
        "generated_at_s": now,
        "mission_end_s": end,
        "belief_observation_count": gp.observation_count,
        "starts": starts.tolist(),
        "targets_by_epoch": chosen_targets.tolist(),
        "sample_times_s": times,
        "forecast": forecast,
        "settings": asdict(settings),
    }
    # Preserve historical exact-GP plan identities; sparse plans also identify
    # their approximation rather than inheriting an exact-forecast label.
    if gp.backend_name != "exact":
        identity.update({"gp_backend": gp.backend_name, "forecast_scope": gp.forecast_scope})
    if inset:
        identity["grid_inset_m"] = inset
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()[:12]
    result = {
        **identity,
        "plan_id": f"dp-{version:06d}-{digest}",
        "status": "planned" if times else "no_remaining_samples",
        "horizon_end_s": times[-1] if times else now,
        "horizon_steps": len(times),
        "selected_candidate_id": selected,
        "candidates": candidates,
        "nominal_checks": chosen_checks,
        "planning_scope": (
            "independent_coarse_frozen_reward_bellman_candidates_exact_joint_selection"
            if gp.backend_name == "exact"
            else "independent_coarse_frozen_reward_bellman_candidates_approximate_joint_selection"
        ),
        "forecast_scope": gp.forecast_scope,
        "gp_backend": gp.backend_name,
        "state": "coarse_cell_and_remaining_sample_epochs",
        "candidate_selection": (
            "joint_terminal_mean_latent_variance_then_travel_within_variance_tolerance"
        ),
        "selection_variance_tolerance": 1e-10 * gp.signal_variance,
        "surrogate_reward": (
            "single_sample_mean_latent_variance_reduction_divided_by_signal_variance"
        ),
        "surrogate_travel_cost": "travel_weight_times_metres_divided_by_team_horizon_travel_budget",
        "claim_limits": [
            "not_a_full_belief_mdp_or_global_route_optimum",
            "not_a_controller_rollout_or_robust_safety_certificate",
            "no_task_impossibility_or_recovery_certificate",
            "short_horizon_forecast_is_not_a_mission_terminal_forecast",
        ],
        "posterior_covariance_wall_s": covariance_wall,
        "planning_wall_s": time.perf_counter() - started,
    }
    # This checks that failure diagnostics can never leak NaN/Infinity into logs.
    json.dumps(result, allow_nan=False)
    return result
