"""The ECC 2025 coarse-cell MDP and its Bellman path planner (M5, source profile).

Anchor: Suenaga, Hanif, Uto and Hatanaka, ECC 2025, pp. 304-311. Ledger topic T08.

What the paper states
---------------------
p. 308 — the field is partitioned into ``n_c`` cells with ``n_c < m``; each cell ``C_b``
has a representative variance and point over ``C_b,d = F_d cap C_b``::

    sigma^2_c,b = sum_{x in C_b,d} sigma^2(x) / |C_b,d|      (a mean)
    x_c,b       = sum_{x in C_b,d} x / |C_b,d|               (the centroid)
    B_i[l]      = { b | x_c,b in V_i(p(t_l)) }

p. 308 — the MDP ``(B_i, A_i, T_i, R_i)`` has all inter-cell transitions
``A_i = {a_bb'}`` and a deterministic transition ``T_i(b, a_bb', b') = 1``.

p. 309 — reward and Bellman recursion::

    R_i(b, a_bb') = sigma^2_c,b' / || x_c,b' - x_c,b ||
    V_i(b)        = max_{a_bb'} [ R_i(b, a_bb') + rho V_i(b') ],   pi_i(b) = argmax

with ``rho = 0.9`` (Table I, p. 310). The policy yields "a series of representative points
of the cells to be visited from the nearest starting point ``x_0i`` to robot ``i``".

Recorded project choices
------------------------
The paper does not state the horizon or termination rule of (16), so these are ours and
are reported in every result:

* **Self-transitions are excluded.** ``R_i(b, a_bb)`` divides by ``||x_c,b - x_c,b|| = 0``
  and is undefined; ``A_i`` is taken as the strict pairs ``b != b'``.
* **Solution method.** (16) is an infinite-horizon discounted fixed point, so it is solved
  by value iteration to a declared tolerance with an iteration cap, not by a fixed horizon.
  ``rho < 1`` makes the update a contraction, so the fixed point is unique.
* **Waypoint count.** The policy has no terminal state and may cycle between two valuable
  cells; Algorithm 1 (p. 310) relies on replanning after each sample instead. We unroll a
  bounded number of policy steps and stop early if the route revisits a cell.

Limits
------
This is a coarse surrogate over frozen cell variances, not a belief-MDP: the rewards do
not update as the route is walked, so repeated visits are over-valued by construction —
the paper's own replanning is what compensates. Nothing here is a claim that the route is
optimal for the GP objective.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from attain_sampling.gp.protocol import FloatArray

__all__ = [
    "CellPlan",
    "CellRepresentatives",
    "bellman_policy",
    "cell_representatives",
    "plan_cell_route",
]


def _finite_points(value: Any, name: str) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError(f"{name} must have shape (n, 2)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    return array


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


@dataclass(frozen=True, slots=True)
class CellRepresentatives:
    """Per-cell representative point and variance over the evaluation points it holds."""

    points: FloatArray
    variances: FloatArray
    counts: np.ndarray

    def as_dict(self) -> dict[str, Any]:
        return {
            "points": self.points.tolist(),
            "variances": self.variances.tolist(),
            "counts": self.counts.tolist(),
            "definition": "mean latent variance and centroid over F_d cap C_b (p. 308)",
        }


def cell_representatives(
    queries: FloatArray,
    variance: FloatArray,
    *,
    origin: tuple[float, float],
    cell_size: float,
    shape: tuple[int, int],
) -> CellRepresentatives:
    """Build ``sigma^2_c,b`` and ``x_c,b`` for a square partition (p. 308).

    Cells holding no evaluation point are dropped rather than given an invented value, so
    ``points`` contains only cells the paper's definition can actually evaluate.
    """
    points = _finite_points(queries, "queries")
    values = np.asarray(variance, dtype=np.float64)
    if values.shape != (len(points),):
        raise ValueError("variance must supply one value per evaluation point")
    if not np.all(np.isfinite(values)):
        raise ValueError("variance must be finite")
    side = _positive(cell_size, "cell_size")
    if len(shape) != 2 or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in shape
    ):
        raise ValueError("shape must contain two positive integers")
    base = np.asarray(origin, dtype=np.float64)
    if base.shape != (2,) or not np.all(np.isfinite(base)):
        raise ValueError("origin must contain two finite coordinates")

    columns = np.clip(((points[:, 0] - base[0]) / side).astype(np.int64), 0, shape[0] - 1)
    rows = np.clip(((points[:, 1] - base[1]) / side).astype(np.int64), 0, shape[1] - 1)
    flat = rows * shape[0] + columns
    total = shape[0] * shape[1]
    counts = np.bincount(flat, minlength=total)
    occupied = np.flatnonzero(counts)
    if not len(occupied):
        raise ValueError("no evaluation point falls inside the declared partition")
    sums = np.zeros((total, 2), dtype=np.float64)
    np.add.at(sums, flat, points)
    variance_sums = np.bincount(flat, weights=values, minlength=total)
    held = counts[occupied].astype(np.float64)
    return CellRepresentatives(
        points=sums[occupied] / held[:, None],
        variances=variance_sums[occupied] / held,
        counts=counts[occupied],
    )


def bellman_policy(
    representatives: CellRepresentatives,
    *,
    discount: float,
    tolerance: float = 1e-10,
    max_iterations: int = 10_000,
) -> tuple[FloatArray, np.ndarray]:
    """Solve eq. (16) by value iteration; returns ``(values, policy)``.

    Self-transitions are excluded because their reward divides by zero. Ties go to the
    lowest cell index so a route is reproducible.
    """
    rho = _positive(discount, "discount")
    if rho >= 1.0:
        raise ValueError("discount must be below one for the recursion to contract")
    tol = _positive(tolerance, "tolerance")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValueError("max_iterations must be an integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    points = representatives.points
    count = len(points)
    if count < 2:
        raise ValueError("the Bellman recursion needs at least two cells")
    distance = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        reward = np.where(distance > 0.0, representatives.variances[None, :] / distance, -np.inf)
    np.fill_diagonal(reward, -np.inf)
    if not np.any(np.isfinite(reward)):
        raise ValueError("no cell pair has a positive separation")
    values = np.zeros(count, dtype=np.float64)
    for _ in range(max_iterations):
        scores = reward + rho * values[None, :]
        updated = np.max(scores, axis=1)
        if not np.all(np.isfinite(updated)):
            raise FloatingPointError("Bellman values became non-finite")
        shift = float(np.max(np.abs(updated - values)))
        values = updated
        if shift <= tol:
            break
    else:  # pragma: no cover - guarded by the contraction property
        raise FloatingPointError("value iteration did not converge within max_iterations")
    policy = np.argmax(reward + rho * values[None, :], axis=1)
    return values, np.asarray(policy, dtype=np.int64)


@dataclass(frozen=True, slots=True)
class CellPlan:
    """A route of representative points, with the provenance needed to read it."""

    waypoints: FloatArray
    cell_indices: tuple[int, ...]
    values: FloatArray
    start_cell: int
    truncated_by_revisit: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "waypoints": self.waypoints.tolist(),
            "cell_indices": list(self.cell_indices),
            "start_cell": self.start_cell,
            "truncated_by_revisit": self.truncated_by_revisit,
            "scope": (
                "coarse frozen-variance surrogate over representative points; not a "
                "belief-MDP solution and not an optimum for the GP objective"
            ),
            "project_choices": [
                "self-transitions excluded (reward divides by zero)",
                "infinite-horizon fixed point solved by value iteration",
                "bounded policy unroll, stopped on revisit",
            ],
        }


def plan_cell_route(
    representatives: CellRepresentatives,
    position: FloatArray,
    *,
    discount: float,
    max_waypoints: int = 8,
    tolerance: float = 1e-10,
) -> CellPlan:
    """Unroll the policy from the cell nearest the robot (p. 309).

    The route stops at ``max_waypoints`` or when the policy revisits a cell, because the
    recursion has no terminal state and the frozen rewards would otherwise cycle.
    """
    robot = np.asarray(position, dtype=np.float64).reshape(2)
    if not np.all(np.isfinite(robot)):
        raise ValueError("position must be finite")
    if isinstance(max_waypoints, bool) or not isinstance(max_waypoints, int):
        raise ValueError("max_waypoints must be an integer")
    if not 1 <= max_waypoints <= 1024:
        raise ValueError("max_waypoints must lie in [1, 1024]")
    values, policy = bellman_policy(representatives, discount=discount, tolerance=tolerance)
    start = int(np.argmin(np.linalg.norm(representatives.points - robot[None, :], axis=1)))
    route: list[int] = []
    seen = {start}
    current = start
    truncated = False
    for _ in range(max_waypoints):
        nxt = int(policy[current])
        if nxt in seen:
            truncated = True
            break
        route.append(nxt)
        seen.add(nxt)
        current = nxt
    waypoints = representatives.points[route] if route else np.empty((0, 2), dtype=np.float64)
    return CellPlan(
        waypoints=np.asarray(waypoints, dtype=np.float64),
        cell_indices=tuple(route),
        values=values,
        start_cell=start,
        truncated_by_revisit=truncated,
    )
