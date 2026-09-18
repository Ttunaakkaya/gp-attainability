"""Motion-primitive Bellman candidates for the turn-constrained USV (M7).

Masterplan v2 §7 asks the USV planner to carry heading information or suitable motion
primitives. This planner uses primitives, so every planned state is an exact vehicle
state and no heading is ever rounded:

* each epoch applies one primitive: an arc of the epoch's full or half travel budget
  turning fully left, going straight or turning fully right, or a stop;
* the reachable states over the horizon form a tree (seven children per node); a
  node is admissible if its whole arc stays inside the field (exact bounds) and it
  ends with a turning circle inside the field, the same single-robot invariant the
  controller keeps, so a robot can always continue along that circle;
* rewards are M2's frozen single-sample reductions of mean latent variance, travel is
  normalised by the team's horizon budget, and the backward Bellman recursion runs on
  the tree; a greedy route over the same surrogate is offered as in M4;
* earlier robots' chosen routes condition later robots' rewards, and their straight
  chords are reserved, over several robot orders; final ranking is the joint terminal
  variance of the chronological samples, exactly as in M2.

The primitive set is a surrogate: routes that curve less than fully, or change speed
inside an epoch, are not searched. A primitive route is flyable by construction (its
length is within budget), and the executing controller certifies the actual arcs; this
is not a controller rollout and not a statement about routes outside the set.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict
from typing import Any

import numpy as np

from attain_sampling.gp.protocol import CovarianceBelief, FloatArray
from attain_sampling.planning.timed_dp import (
    _GEOMETRY_TOLERANCE,
    DPSettings,
    _integer,
    _points,
    _real,
    _robot_orders,
    _sample_times,
)
from attain_sampling.sim.usv import arc_bounds, integrate_arc, viable

__all__ = ["PRIMITIVES", "plan_primitive_dp"]

# Containment is exact (the arc's bounding box), with the same tolerance as the
# turning-circle test. A sampled check with a sub-interval margin was stricter than
# the controller and left robots near an edge with only the stop (D057).
_CONTAINMENT_TOLERANCE = 1e-9

# (fraction of the epoch's travel budget, turn direction); the stop comes last.
PRIMITIVES: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),
    (1.0, 0.0),
    (1.0, -1.0),
    (0.5, 1.0),
    (0.5, 0.0),
    (0.5, -1.0),
    (0.0, 0.0),
)


def _segment_gap(
    start_a: FloatArray, end_a: FloatArray, start_b: FloatArray, end_b: FloatArray
) -> FloatArray:
    relative = start_a - start_b
    delta = (end_a - start_a) - (end_b - start_b)
    squared = np.sum(delta * delta, axis=-1)
    fraction = np.divide(
        -np.sum(relative * delta, axis=-1), squared, out=np.zeros_like(squared), where=squared > 0
    )
    closest = relative + np.clip(fraction, 0.0, 1.0)[..., None] * delta
    return np.asarray(np.linalg.norm(closest, axis=-1))


class _Tree:
    """All primitive routes of one robot over the horizon, level by level."""

    def __init__(
        self,
        start: FloatArray,
        heading: float,
        budgets: FloatArray,
        *,
        radius: float,
        bounds: FloatArray,
    ) -> None:
        count = len(PRIMITIVES)
        fractions = np.asarray([item[0] for item in PRIMITIVES])
        turns = np.asarray([item[1] for item in PRIMITIVES])
        self.positions: list[FloatArray] = [np.asarray(start, dtype=np.float64)[None]]
        self.headings: list[FloatArray] = [np.asarray([heading], dtype=np.float64)]
        self.valid: list[np.ndarray] = [np.asarray([True])]
        self.lengths: list[FloatArray] = [np.zeros(1)]
        for budget in budgets:
            parents_p = np.repeat(self.positions[-1], count, axis=0)
            parents_h = np.repeat(self.headings[-1], count)
            length = np.tile(fractions, len(self.positions[-1])) * float(budget)
            curvature = np.tile(turns, len(self.positions[-1])) / radius
            end, end_heading = integrate_arc(parents_p, parents_h, length, curvature)
            low, high = arc_bounds(parents_p, parents_h, length, curvature)
            inside = np.all(
                (low >= -_CONTAINMENT_TOLERANCE) & (high <= bounds + _CONTAINMENT_TOLERANCE),
                axis=1,
            )
            left, right = viable(end, end_heading, radius, (float(bounds[0]), float(bounds[1])))
            stopped = length == 0
            valid = np.repeat(self.valid[-1], count) & (stopped | (inside & (left | right)))
            self.positions.append(end)
            self.headings.append(end_heading)
            self.valid.append(valid)
            self.lengths.append(length)

    @property
    def depth(self) -> int:
        return len(self.positions) - 1

    def all_points(self) -> FloatArray:
        return np.vstack(self.positions[1:])

    def offsets(self) -> list[int]:
        sizes = [len(level) for level in self.positions[1:]]
        return [0, *np.cumsum(sizes).tolist()]


def _route_values(
    tree: _Tree,
    rewards: list[FloatArray],
    costs: list[FloatArray],
    admissible: list[np.ndarray],
    greedy: bool,
) -> tuple[list[int], float | None] | None:
    """Best child index path by backward Bellman (or forward greedy) on the tree."""
    count = len(PRIMITIVES)
    depth = tree.depth
    if greedy:
        route: list[int] = []
        node = 0
        for level in range(1, depth + 1):
            children = node * count + np.arange(count)
            scores = np.where(
                admissible[level][children],
                rewards[level][children] - costs[level][children],
                -np.inf,
            )
            best = int(np.argmax(scores))
            if not math.isfinite(float(scores[best])):
                return None
            node = int(children[best])
            route.append(node)
        return route, None
    value = np.zeros(len(tree.positions[depth]))
    value = np.where(admissible[depth], value, -np.inf)
    choices: list[np.ndarray] = []
    for level in range(depth, 0, -1):
        gain = np.where(admissible[level], rewards[level] - costs[level] + value, -np.inf).reshape(
            -1, count
        )
        best = np.argmax(gain, axis=1)
        choices.append(best)
        value = gain[np.arange(len(gain)), best]
    if not math.isfinite(float(value[0])):
        return None
    choices.reverse()
    route = []
    node = 0
    for level in range(depth):
        node = node * count + int(choices[level][node])
        route.append(node)
    return route, float(value[0])


def _checks(
    starts: FloatArray,
    targets: FloatArray,
    lengths: FloatArray,
    budgets: FloatArray,
    bounds: FloatArray,
    min_separation: float,
) -> dict[str, Any]:
    robots = len(starts)
    excess = float(np.max(lengths - budgets[:, None])) if len(targets) else 0.0
    bounds_violation = (
        float(max(0.0, -np.min(targets), np.max(targets - bounds))) if len(targets) else 0.0
    )
    minimum: float | None = None
    previous = starts
    for positions in targets:
        for first in range(robots):
            for second in range(first + 1, robots):
                gap = float(
                    _segment_gap(
                        previous[first], positions[first], previous[second], positions[second]
                    )
                )
                minimum = gap if minimum is None else min(minimum, gap)
        previous = positions
    shortfall = max(0.0, min_separation - minimum) if minimum is not None else 0.0
    return {
        "accepted": bool(
            max(excess, 0.0) <= _GEOMETRY_TOLERANCE
            and bounds_violation <= _GEOMETRY_TOLERANCE
            and shortfall <= _GEOMETRY_TOLERANCE
        ),
        "scope": (
            "primitive_arc_lengths_within_budget_and_straight_chord_reservations_"
            "without_controller_rollout"
        ),
        "max_path_length_excess_m": max(excess, 0.0),
        "max_bounds_violation_m": bounds_violation,
        "min_pair_distance_m": minimum,
        "max_separation_violation_m": shortfall,
    }


def plan_primitive_dp(
    gp: CovarianceBelief,
    positions: FloatArray,
    headings: FloatArray,
    query: FloatArray,
    *,
    domain: tuple[float, float],
    max_speed: float,
    min_separation: float,
    turn_radius: float,
    sample_period_s: float,
    now_s: float,
    mission_end_s: float,
    plan_version: int,
    settings: DPSettings,
) -> dict[str, Any]:
    """Primitive-tree counterpart of :func:`plan_timed_dp`, with the same record shape."""
    started = time.perf_counter()
    if not isinstance(settings, DPSettings):
        raise ValueError("settings must be DPSettings")
    starts = _points(positions, "positions")
    angles = np.asarray(headings, dtype=np.float64)
    if angles.shape != (len(starts),) or not np.all(np.isfinite(angles)):
        raise ValueError("headings must supply one finite angle per robot")
    queries = _points(query, "query")
    if len(starts) > 4:
        raise ValueError("the bounded planner supports one to four robots")
    bounds = np.asarray([_real(value, "domain entry", positive=True) for value in domain])
    speed = _real(max_speed, "max_speed", positive=True)
    separation = _real(min_separation, "min_separation")
    radius = _real(turn_radius, "turn_radius", positive=True)
    period = _real(sample_period_s, "sample_period_s", positive=True)
    now = _real(now_s, "now_s")
    end = _real(mission_end_s, "mission_end_s")
    version = _integer(plan_version, "plan_version", 0, 2**53 - 1)
    if end < now:
        raise ValueError("mission_end_s must not precede now_s")
    if np.any(starts < -_GEOMETRY_TOLERANCE) or np.any(starts > bounds + _GEOMETRY_TOLERANCE):
        raise ValueError("actual positions lie outside the domain tolerance")
    if settings.horizon_steps > 6:
        raise ValueError("the primitive tree supports horizons of at most six epochs")
    times = _sample_times(now, end, period, settings.horizon_steps)
    durations = np.diff(np.asarray([now, *times], dtype=np.float64))
    budgets = speed * durations
    current = gp.predict(queries, variance="latent").variance
    current_mean = float(np.mean(current))
    forecast = [
        {"time_s": now, "mean_variance": current_mean, "max_variance": float(np.max(current))}
    ]
    candidates: list[dict[str, Any]] = []
    chosen_targets = np.empty((0, len(starts), 2), dtype=np.float64)
    chosen_lengths = np.empty((0, len(starts)), dtype=np.float64)
    chosen_checks = _checks(starts, chosen_targets, chosen_lengths, budgets, bounds, separation)
    selected: str | None = None
    covariance_wall = 0.0
    count = len(PRIMITIVES)
    if times:
        total_travel_budget = len(starts) * speed * (times[-1] - now)
        if not math.isfinite(total_travel_budget) or total_travel_budget <= 0:
            raise ValueError("planning travel budget must be positive and finite")
        trees = [
            _Tree(starts[robot], float(angles[robot]), budgets, radius=radius, bounds=bounds)
            for robot in range(len(starts))
        ]
        covariance_started = time.perf_counter()
        prior_cross = []
        prior_diagonal = []
        for tree in trees:
            points = tree.all_points()
            prior_cross.append(gp.posterior_covariance(queries, points))
            prior_diagonal.append(gp.predict(points, variance="latent").variance)
        covariance_wall = time.perf_counter() - covariance_started
        noise = gp.noise_variance + gp.jitter

        unconditioned: dict[int, list[FloatArray]] = {}

        def robot_rewards(robot: int, conditioning: FloatArray) -> list[FloatArray]:
            """Frozen single-sample rewards per tree level, given earlier robots' samples."""
            if not len(conditioning) and robot in unconditioned:
                return unconditioned[robot]
            tree = trees[robot]
            points = tree.all_points()
            cross = prior_cross[robot]
            diagonal = prior_diagonal[robot]
            if len(conditioning):
                gram = gp.posterior_covariance(conditioning) + noise * np.eye(len(conditioning))
                to_queries = gp.posterior_covariance(queries, conditioning)
                to_points = gp.posterior_covariance(conditioning, points)
                solved = np.linalg.solve(gram, to_points)
                cross = cross - to_queries @ solved
                diagonal = diagonal - np.sum(to_points * solved, axis=0)
            diagonal = np.maximum(diagonal, 0.0)
            values = np.mean(cross * cross, axis=0) / (diagonal + noise) / gp.signal_variance
            if not np.all(np.isfinite(values)):
                raise FloatingPointError("non-finite Bellman information rewards")
            offsets = tree.offsets()
            levels = [np.zeros(1)] + [
                values[offsets[level] : offsets[level + 1]] for level in range(tree.depth)
            ]
            if not len(conditioning):
                unconditioned[robot] = levels
            return levels

        raw: list[tuple[str, str, list[int], FloatArray, FloatArray, list[float | None], float]]
        raw = []
        searches = [("bellman", "primitive_tree_bellman", False)]
        if settings.include_greedy_candidates:
            searches.append(("greedy", "primitive_tree_greedy", True))
        for prefix, generator, greedy in searches:
            for order_index, order in enumerate(_robot_orders(len(starts), version)):
                candidate_started = time.perf_counter()
                routes: dict[int, list[int]] = {}
                surrogate_values: list[float | None] = [None] * len(starts)
                conditioning = np.empty((0, 2))
                failed: int | None = None
                for robot in order:
                    tree = trees[robot]
                    rewards = robot_rewards(robot, conditioning)
                    costs = [
                        settings.travel_weight * level_lengths / total_travel_budget
                        for level_lengths in tree.lengths
                    ]
                    admissible = [valid.copy() for valid in tree.valid]
                    for level in range(1, tree.depth + 1):
                        parents = np.repeat(tree.positions[level - 1], count, axis=0)
                        children = tree.positions[level]
                        for earlier, route in routes.items():
                            before_node = route[level - 2] if level > 1 else None
                            before = (
                                trees[earlier].positions[level - 1][before_node]
                                if before_node is not None
                                else starts[earlier]
                            )
                            after = trees[earlier].positions[level][route[level - 1]]
                            gap = _segment_gap(parents, children, before, after)
                            admissible[level] &= gap >= separation - _GEOMETRY_TOLERANCE
                    found = _route_values(tree, rewards, costs, admissible, greedy)
                    if found is None:
                        failed = robot
                        break
                    route_nodes, value = found
                    routes[robot] = route_nodes
                    surrogate_values[robot] = value
                    chosen = np.asarray(
                        [tree.positions[level + 1][node] for level, node in enumerate(route_nodes)]
                    )
                    conditioning = np.vstack((conditioning, chosen))
                candidate_id = f"{prefix}-order-{order_index}"
                if failed is not None:
                    candidates.append(
                        {
                            "candidate_id": candidate_id,
                            "generator": generator,
                            "robot_order": order,
                            "status": "rejected",
                            "rejection_reason": "no_route_in_this_ordered_primitive_tree_search",
                            "failed_robot": failed,
                            "selected": False,
                            "generation_wall_s": time.perf_counter() - candidate_started,
                        }
                    )
                    continue
                targets = np.asarray(
                    [
                        [
                            trees[robot].positions[level + 1][routes[robot][level]]
                            for robot in range(len(starts))
                        ]
                        for level in range(len(times))
                    ]
                )
                lengths = np.asarray(
                    [
                        [
                            trees[robot].lengths[level + 1][routes[robot][level]]
                            for robot in range(len(starts))
                        ]
                        for level in range(len(times))
                    ]
                )
                raw.append(
                    (
                        candidate_id,
                        generator,
                        order,
                        targets,
                        lengths,
                        surrogate_values,
                        time.perf_counter() - candidate_started,
                    )
                )
        raw.append(
            (
                "nominal-hold",
                "nominal_hold",
                [],
                np.repeat(starts[None], len(times), axis=0),
                np.zeros((len(times), len(starts))),
                [],
                0.0,
            )
        )
        for candidate_id, generator, order, targets, lengths, surrogate_values, wall in raw:
            evaluation_started = time.perf_counter()
            checks = _checks(starts, targets, lengths, budgets, bounds, separation)
            if not checks["accepted"]:
                raise FloatingPointError("generated primitive plan failed its own geometry check")
            terminal = gp.fantasy_variance(queries, targets.reshape(-1, 2))
            travel = float(np.sum(lengths))
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
                    "primitive_lengths_by_epoch": lengths.tolist(),
                    "nominal_checks": checks,
                    "generation_wall_s": wall,
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
        chosen_candidate = min(
            tied, key=lambda candidate: (candidate["normalized_travel"], candidate["candidate_id"])
        )
        chosen_candidate["selected"] = True
        selected = chosen_candidate["candidate_id"]
        chosen_targets = np.asarray(chosen_candidate["targets_by_epoch"], dtype=np.float64)
        chosen_checks = chosen_candidate["nominal_checks"]
        for epoch, sample_time in enumerate(times):
            variance = gp.fantasy_variance(queries, chosen_targets[: epoch + 1].reshape(-1, 2))
            forecast.append(
                {
                    "time_s": sample_time,
                    "mean_variance": float(np.mean(variance)),
                    "max_variance": float(np.max(variance)),
                }
            )
    motion_model = {
        "model": "usv_curvature",
        "turn_radius_m": radius,
        "primitives": [list(item) for item in PRIMITIVES],
    }
    identity = {
        "plan_version": version,
        "generated_at_s": now,
        "mission_end_s": end,
        "belief_observation_count": gp.observation_count,
        "starts": starts.tolist(),
        "start_headings": angles.tolist(),
        "targets_by_epoch": chosen_targets.tolist(),
        "sample_times_s": times,
        "forecast": forecast,
        "settings": asdict(settings),
        "motion_model": motion_model,
        "gp_backend": gp.backend_name,
        "forecast_scope": gp.forecast_scope,
    }
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
        "planning_scope": "independent_motion_primitive_tree_bellman_candidates_"
        + ("exact" if gp.backend_name == "exact" else "approximate")
        + "_joint_selection",
        "state": "exact_vehicle_pose_reachable_by_primitives_and_remaining_sample_epochs",
        "candidate_selection": (
            "joint_terminal_mean_latent_variance_then_travel_within_variance_tolerance"
        ),
        "selection_variance_tolerance": 1e-10 * gp.signal_variance,
        "surrogate_reward": (
            "single_sample_mean_latent_variance_reduction_divided_by_signal_variance"
        ),
        "surrogate_travel_cost": (
            "travel_weight_times_primitive_arc_metres_divided_by_team_horizon_budget"
        ),
        "claim_limits": [
            "not_a_full_belief_mdp_or_global_route_optimum",
            "only_the_seven_primitives_per_epoch_are_searched",
            "not_a_controller_rollout_or_robust_safety_certificate",
            "no_task_impossibility_or_recovery_certificate",
            "short_horizon_forecast_is_not_a_mission_terminal_forecast",
        ],
        "posterior_covariance_wall_s": covariance_wall,
        "planning_wall_s": time.perf_counter() - started,
    }
    json.dumps(result, allow_nan=False)
    return result
