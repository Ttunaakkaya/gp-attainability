"""The ECC 2025 per-robot QP, eqs. (10), (11) and (17) (M5, source profile).

Anchor: Suenaga, Hanif, Uto and Hatanaka, ECC 2025, pp. 307 and 309. Ledger topics T05, T06.

Each robot solves its own problem — the paper's "partially distributed" controller::

    (u_i, w_i) = argmin_{(u_i, w_i) in U x R}  eps_opt ||u_i - u_nom,i||^2 + |w_i|^2
    subject to  xi_i1^T u_i + xi_i2 >= w_i                               (rate, slack)
                (d h_ca,ij / d p_i)^T u_i + alpha_ca(h_ca,ij) >= 0   for all j   (eq. (9))

with ``h_ca,ij = ||p_i - p_j||^2 - d_ca^2``, so ``d h_ca,ij / d p_i = 2 (p_i - p_j)``. The
constraint-only controller (10) is the case ``u_nom,i = 0``; the hierarchical controller
(17) supplies ``u_nom,i = kappa (x_ci - p_i)``.

Recorded project choices
------------------------
The paper does not state these, so they are ours and are reported with every run:

* ``alpha_ca`` is linear, ``alpha_ca(h) = alpha_ca * h``.
* ``U`` is a speed bound, enforced as an inscribed regular polygon (conservative relative
  to the Euclidean disk), exactly as in the M1 controller.
* Each robot treats its neighbours as static, as eq. (11) is printed. If every robot does
  so, summing the two per-robot rows gives ``hdot_ca,ij + 2 alpha_ca h_ca,ij >= 0``: still a
  valid barrier condition, with a doubled gain.
* There is no workspace-containment constraint: the paper states none, and its robots
  start outside the field.

Solver
------
The paper solves its QPs with CVXOPT (p. 310), an interior-point method. The nominal term
``kappa (x_ci - p_i)`` with ``kappa = 15`` makes this tiny problem badly scaled next to a
near-zero ``xi_i1``; the first-order OSQP solver used by M1 stopped at its iteration limit
before reaching the acceptance tolerance. Clarabel, an interior-point solver already in
the lock file, is therefore used here. Every solution is still re-checked independently.

Limits
------
The barrier row is evaluated at the start of each control interval only. That is not a
sampled-data safety certificate, so separation is re-checked on the executed trajectory.
A rejected solve is reported, never replaced by a hidden command.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import clarabel
import numpy as np
from scipy import sparse

from attain_sampling.control.rate_constraint import DecayConstraintRow
from attain_sampling.gp.protocol import FloatArray

__all__ = ["EccQPResult", "EccQPSettings", "solve_robot_qp"]


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


@dataclass(frozen=True, slots=True)
class EccQPSettings:
    """Table I weights plus the project choices listed in the module docstring."""

    epsilon_opt: float
    d_ca: float
    alpha_ca: float = 1.0
    max_speed: float = 2.0
    polygon_sides: int = 16
    tolerance: float = 1e-7
    max_iter: int = 200

    def __post_init__(self) -> None:
        for name in ("epsilon_opt", "d_ca", "alpha_ca", "max_speed", "tolerance"):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        for name, lower in (("polygon_sides", 3), ("max_iter", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")


@dataclass(frozen=True, slots=True)
class EccQPResult:
    """Outcome of one robot's solve; ``velocity`` is None when the solve is rejected."""

    success: bool
    velocity: FloatArray | None
    slack: float | None
    status: str
    max_violation: float
    rate_satisfied_without_slack: bool
    wall_s: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "velocity": None if self.velocity is None else self.velocity.tolist(),
            "slack": self.slack,
            "status": self.status,
            "max_violation": self.max_violation,
            "rate_satisfied_without_slack": self.rate_satisfied_without_slack,
            "wall_s": self.wall_s,
        }


def _polygon(sides: int, radius: float) -> tuple[FloatArray, float]:
    angles = (2.0 * np.arange(sides) + 1.0) * math.pi / sides
    normals = np.column_stack((np.cos(angles), np.sin(angles)))
    return normals, radius * math.cos(math.pi / sides)


def solve_robot_qp(
    *,
    robot: int,
    positions: FloatArray,
    row: DecayConstraintRow,
    nominal: FloatArray,
    settings: EccQPSettings,
) -> EccQPResult:
    """Solve eq. (10) (``nominal = 0``) or eq. (17) for one robot."""
    started = time.perf_counter()
    fleet = np.asarray(positions, dtype=np.float64)
    if fleet.ndim != 2 or fleet.shape[1] != 2 or not np.all(np.isfinite(fleet)):
        raise ValueError("positions must be a finite (n, 2) array")
    if isinstance(robot, bool) or not isinstance(robot, int) or not 0 <= robot < len(fleet):
        raise ValueError("robot must index the positions array")
    target = np.asarray(nominal, dtype=np.float64).reshape(2)
    if not np.all(np.isfinite(target)):
        raise ValueError("nominal must be finite")
    if not isinstance(settings, EccQPSettings):
        raise ValueError("settings must be EccQPSettings")

    here = fleet[robot]
    others = np.delete(fleet, robot, axis=0)
    offsets = here[None, :] - others
    barrier = np.sum(offsets * offsets, axis=1) - settings.d_ca**2
    normals, bound = _polygon(settings.polygon_sides, settings.max_speed)

    # Every constraint is written as G x <= h over x = (u_x, u_y, w).
    rows = [np.array([-row.xi1[0], -row.xi1[1], 1.0])]
    bounds = [row.xi2]
    for offset, value in zip(offsets, barrier, strict=True):
        rows.append(np.array([-2.0 * offset[0], -2.0 * offset[1], 0.0]))
        bounds.append(settings.alpha_ca * value)
    for normal in normals:
        rows.append(np.array([normal[0], normal[1], 0.0]))
        bounds.append(bound)
    matrix = np.vstack(rows)
    limits = np.asarray(bounds, dtype=np.float64)

    # Conditioning, without changing the feasible set: unit-norm rows, and barrier rows
    # dropped only when no velocity inside the speed disk can reach them. A far neighbour
    # otherwise contributes coefficients ~1e2 against bounds ~1e4, which stalled the
    # interior-point iterations. The post-check below still uses every original row.
    norms = np.linalg.norm(matrix[:, :2], axis=1)
    barrier_rows = np.arange(1, 1 + len(offsets))
    implied = np.zeros(len(matrix), dtype=bool)
    implied[barrier_rows] = limits[barrier_rows] > settings.max_speed * norms[barrier_rows]
    keep = ~implied
    scale = np.linalg.norm(matrix[keep], axis=1)
    scale[scale == 0.0] = 1.0
    solve_matrix = matrix[keep] / scale[:, None]
    solve_limits = limits[keep] / scale

    eps = settings.epsilon_opt
    hessian = sparse.triu(sparse.diags([2.0 * eps, 2.0 * eps, 2.0])).tocsc()
    linear = np.array([-2.0 * eps * target[0], -2.0 * eps * target[1], 0.0])
    options = clarabel.DefaultSettings()
    options.verbose = False
    options.max_iter = settings.max_iter
    # Clarabel's default 1e-8 accuracy: tighter targets stalled on near-degenerate steps
    # without changing feasibility, which the independent post-check still enforces.
    options.tol_gap_abs = 1e-8
    options.tol_gap_rel = 1e-8
    options.tol_feas = 1e-8
    solver = clarabel.DefaultSolver(
        hessian,
        linear,
        sparse.csc_matrix(solve_matrix),
        solve_limits,
        [clarabel.NonnegativeConeT(len(solve_limits))],
        options,
    )
    solution = solver.solve()
    status = str(solution.status)
    x = np.asarray(solution.x, dtype=np.float64)
    if x.shape != (3,) or not np.all(np.isfinite(x)):
        return EccQPResult(
            False, None, None, status, math.inf, False, time.perf_counter() - started
        )
    violation = float(max(np.max(matrix @ x - limits), 0.0))
    accepted = status in {"Solved", "AlmostSolved"} and violation <= settings.tolerance
    velocity = x[:2].copy()
    return EccQPResult(
        success=bool(accepted),
        velocity=velocity if accepted else None,
        slack=float(x[2]) if accepted else None,
        status=status,
        max_violation=violation,
        rate_satisfied_without_slack=bool(row.satisfied_by(velocity)),
        wall_s=time.perf_counter() - started,
    )
