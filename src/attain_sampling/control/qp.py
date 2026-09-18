"""Centralized tracking QP for sampled, disturbance-free holonomic robots.

The applied motion is ``p(t+s) = p(t) + s*u`` for ``0 <= s <= dt``. The hard
constraints are an inscribed regular speed polygon, rectangular endpoint bounds,
the continuous-time pair CBF evaluated at the current state, and a conservative
separating-plane endpoint constraint. The last constraint also protects the
interior of each *linear* motion segment: its projection on the initial relative
direction stays at least ``min_separation``. These are independent design choices,
not the ECC paper's QP or a physical-robot safety certificate. There is no GP
performance constraint and no safety slack.

OSQP solves ``.5*u.T@u - u_nom.T@u``; the omitted constant is restored in the
reported tracking objective. Every accepted result is independently checked
against the assembled linear constraints, stationarity, dual signs, normalized
complementarity, Euclidean speed, domain, and analytical segment minimum distance.
Each complementarity product is divided by ``1 + abs(dual_multiplier)`` before
comparison with the explicit tolerance; raw products are logged too. No
projection, clipping, backtracking, or hold fallback is applied after a failed or
successful solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from time import perf_counter
from typing import Any

import numpy as np
import osqp
from scipy import sparse

from attain_sampling.gp.protocol import FloatArray


def _valid_real(value: Any, *, allow_zero: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return False
    return bool(np.isfinite(number)) and (number >= 0 if allow_zero else number > 0)


@dataclass(frozen=True, slots=True)
class QPSettings:
    """Deterministic solver choices and explicit numerical acceptance bounds."""

    alpha: float = 1.0
    polygon_sides: int = 16
    eps_abs: float = 1e-8
    # Unscaled CBF rows can be large even in a 60 m domain. A relative stopping
    # bound may then exceed the independent physical acceptance tolerance.
    eps_rel: float = 0.0
    acceptance_tol: float = 1e-7
    max_iter: int = 10000

    def __post_init__(self) -> None:
        for name in ("alpha", "eps_abs", "acceptance_tol"):
            value = getattr(self, name)
            if not _valid_real(value):
                raise ValueError(f"{name} must be finite and positive")
        if not _valid_real(self.eps_rel, allow_zero=True):
            raise ValueError("eps_rel must be finite and nonnegative")
        if (
            isinstance(self.polygon_sides, bool)
            or not isinstance(self.polygon_sides, int)
            or self.polygon_sides < 4
            or self.polygon_sides % 2
        ):
            raise ValueError("polygon_sides must be an even integer >= 4")
        if (
            isinstance(self.max_iter, bool)
            or not isinstance(self.max_iter, int)
            or self.max_iter < 1
        ):
            raise ValueError("max_iter must be a positive integer")


_DEFAULT_SETTINGS = QPSettings()


@dataclass(frozen=True, slots=True)
class QPResult:
    """A verified command, or explicit failure with no substitute command."""

    velocity: FloatArray | None
    success: bool
    log: dict[str, Any]


def _finite_number(value: Any) -> float | None:
    """Keep solver diagnostics strict-JSON compatible, even on solver failure."""
    if value is None:
        return None
    number = float(value)
    return number if np.isfinite(number) else None


def _segment_minimum(positions: FloatArray, displacement: FloatArray) -> float | None:
    closest = float("inf")
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            relative = positions[first] - positions[second]
            change = displacement[first] - displacement[second]
            norm_squared = float(change @ change)
            fraction = (
                float(np.clip(-(relative @ change) / norm_squared, 0.0, 1.0))
                if norm_squared > 0.0
                else 0.0
            )
            closest = min(closest, float(np.linalg.norm(relative + fraction * change)))
    return _finite_number(closest)


def _validated_inputs(
    positions: FloatArray,
    nominal_velocity: FloatArray,
    domain: tuple[float, float],
    max_speed: float,
    min_separation: float,
    dt: float,
    tolerance: float,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    if np.iscomplexobj(positions) or np.iscomplexobj(nominal_velocity) or np.iscomplexobj(domain):
        raise ValueError("positions, nominal_velocity and domain must be real-valued")
    points = np.asarray(positions, dtype=np.float64)
    nominal = np.asarray(nominal_velocity, dtype=np.float64)
    bounds = np.asarray(domain, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or not len(points):
        raise ValueError("positions must have non-empty shape (n, 2)")
    if nominal.shape != points.shape:
        raise ValueError("nominal_velocity must have the same (n, 2) shape as positions")
    if not np.all(np.isfinite(points)) or not np.all(np.isfinite(nominal)):
        raise ValueError("positions and nominal_velocity must be finite")
    if bounds.shape != (2,) or not np.all(np.isfinite(bounds)) or np.any(bounds <= 0):
        raise ValueError("domain must contain two finite positive lengths")
    for name, value in (("max_speed", max_speed), ("min_separation", min_separation), ("dt", dt)):
        if not _valid_real(value):
            raise ValueError(f"{name} must be finite and positive")
    if np.any(points < -tolerance) or np.any(points > bounds + tolerance):
        raise ValueError("initial positions are outside the rectangular domain")
    initial_minimum = _segment_minimum(points, np.zeros_like(points))
    if initial_minimum == 0.0:
        # The relative direction in the segment-plane constraint is undefined.
        # An absolute acceptance tolerance must not admit coincident robots.
        raise ValueError("initial positions have zero pair separation")
    if initial_minimum is not None and initial_minimum < min_separation - tolerance:
        raise ValueError("initial positions violate minimum separation")
    return points.copy(), nominal.copy(), bounds.copy()


def _constraints(
    positions: FloatArray,
    domain: FloatArray,
    max_speed: float,
    min_separation: float,
    dt: float,
    settings: QPSettings,
) -> tuple[FloatArray, FloatArray, FloatArray, list[str]]:
    variables = positions.size
    rows: list[FloatArray] = []
    lower: list[float] = []
    upper: list[float] = []
    labels: list[str] = []
    for robot, point in enumerate(positions):
        # Vertices are at angles 2*k*pi/N, so the x axis is a polygon vertex.
        for facet in range(settings.polygon_sides):
            angle = (2 * facet + 1) * np.pi / settings.polygon_sides
            row = np.zeros(variables)
            row[2 * robot : 2 * robot + 2] = (np.cos(angle), np.sin(angle))
            rows.append(row)
            lower.append(-np.inf)
            upper.append(float(max_speed * np.cos(np.pi / settings.polygon_sides)))
            labels.append(f"speed:{robot}:{facet}")
        for coordinate in range(2):
            row = np.zeros(variables)
            row[2 * robot + coordinate] = dt
            rows.append(row)
            lower.append(float(-point[coordinate]))
            upper.append(float(domain[coordinate] - point[coordinate]))
            labels.append(f"domain:{robot}:{coordinate}")
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            relative = positions[first] - positions[second]
            distance = float(np.linalg.norm(relative))
            row = np.zeros(variables)
            row[2 * first : 2 * first + 2] = 2 * relative
            row[2 * second : 2 * second + 2] = -2 * relative
            rows.append(row)
            cbf_bound = -settings.alpha * (distance**2 - min_separation**2)
            if not np.isfinite(cbf_bound):
                raise ValueError("CBF bound overflowed; rescale the problem")
            lower.append(cbf_bound)
            upper.append(np.inf)
            labels.append(f"cbf:{first}:{second}")
            row = np.zeros(variables)
            row[2 * first : 2 * first + 2] = dt * relative / distance
            row[2 * second : 2 * second + 2] = -dt * relative / distance
            rows.append(row)
            lower.append(min_separation - distance)
            upper.append(np.inf)
            labels.append(f"segment_plane:{first}:{second}")
    return np.asarray(rows), np.asarray(lower), np.asarray(upper), labels


def solve_tracking_qp(
    positions: FloatArray,
    nominal_velocity: FloatArray,
    *,
    domain: tuple[float, float],
    max_speed: float,
    min_separation: float,
    dt: float,
    settings: QPSettings = _DEFAULT_SETTINGS,
) -> QPResult:
    """Return only independently verified QP velocities; invalid starts fail.

    The caller must mark failed execution as such, rather than moving using a
    nominal or held command. Any exogenous disturbance after this solve requires
    its own validation; the QP does not guarantee unknown post-control drift.
    Constraint margins combine velocity, distance and CBF units; individual
    physical speed/distance/domain diagnostics are reported separately.
    """
    started = perf_counter()
    solver_settings: dict[str, Any] = {
        "eps_abs": settings.eps_abs,
        "eps_rel": settings.eps_rel,
        "max_iter": settings.max_iter,
        "adaptive_rho": True,
        "adaptive_rho_interval": 25,
        "check_termination": 25,
        "warm_starting": False,
        "polishing": False,
        "scaled_termination": False,
        "verbose": False,
    }
    log: dict[str, Any] = {
        "controller": "centralized_tracking_qp",
        "status": "not_run",
        "status_val": None,
        "success": False,
        "iterations": 0,
        "primal_residual": None,
        "dual_residual": None,
        "stationarity_residual": None,
        "dual_feasibility_residual": None,
        "complementarity_residual": None,
        "normalized_complementarity_residual": None,
        "objective": None,
        "solver_objective": None,
        "setup_s": 0.0,
        "solve_s": 0.0,
        "setup_wall_s": 0.0,
        "solve_wall_s": 0.0,
        "control_s": 0.0,
        "min_linear_margin": None,
        "max_constraint_violation": None,
        "segment_min_separation": None,
        "max_speed_observed": None,
        "domain_violation": None,
        "modification_norm": None,
        "active_constraints": [],
        "failure_reason": None,
        "acceptance_tol": settings.acceptance_tol,
        "solver_eps_abs": settings.eps_abs,
        "solver_eps_rel": settings.eps_rel,
        "solver_max_iter": settings.max_iter,
        "solver_settings": solver_settings.copy(),
        "speed_polygon_sides": settings.polygon_sides,
        "rho_updates": 0,
    }

    def failure(reason: str) -> QPResult:
        log["failure_reason"] = reason
        log["control_s"] = perf_counter() - started
        return QPResult(velocity=None, success=False, log=log)

    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            points, nominal, bounds = _validated_inputs(
                positions,
                nominal_velocity,
                domain,
                max_speed,
                min_separation,
                dt,
                settings.acceptance_tol,
            )
            matrix, lower, upper, labels = _constraints(
                points, bounds, max_speed, min_separation, dt, settings
            )
        # Only deliberate one-sided bounds may be infinite. In particular,
        # overflow must not silently turn a finite CBF bound into no constraint.
        if (
            not np.all(np.isfinite(matrix))
            or np.any(np.isnan(lower))
            or np.any(np.isnan(upper))
            or np.any(np.isposinf(lower))
            or np.any(np.isneginf(upper))
            or np.any(lower > upper)
        ):
            raise ValueError("constraint assembly produced invalid numerical values")
    except (ValueError, TypeError, OverflowError, FloatingPointError) as error:
        log["status"] = "invalid_input"
        return failure(f"invalid_input: {error}")
    log["constraint_count"] = len(labels)
    setup_started = perf_counter()
    try:
        solver = osqp.OSQP()
        solver.setup(
            P=sparse.eye(points.size, format="csc"),
            q=-nominal.ravel(),
            A=sparse.csc_matrix(matrix),
            l=lower,
            u=upper,
            **solver_settings,
        )
        log["setup_wall_s"] = perf_counter() - setup_started
        solve_started = perf_counter()
        solution = solver.solve(raise_error=False)
        log["solve_wall_s"] = perf_counter() - solve_started
    except Exception as error:  # Solver failures must not become unchecked motion.
        log["status"] = "solver_error"
        return failure(f"solver_error: {type(error).__name__}: {error}")
    info = solution.info
    log.update(
        status=str(info.status),
        status_val=int(info.status_val),
        iterations=int(info.iter),
        primal_residual=_finite_number(info.prim_res),
        dual_residual=_finite_number(info.dual_res),
        solver_objective=_finite_number(info.obj_val),
        setup_s=_finite_number(info.setup_time),
        solve_s=_finite_number(info.solve_time),
        rho_updates=int(info.rho_updates),
    )
    if info.status_val not in (1, 2):
        return failure(f"solver_status: {info.status}")
    try:
        if np.iscomplexobj(solution.x) or np.iscomplexobj(solution.y):
            return failure("nonfinite_or_malformed_solution")
        velocity = np.asarray(solution.x, dtype=np.float64)
        dual = np.asarray(solution.y, dtype=np.float64)
    except (ValueError, TypeError, OverflowError):
        return failure("nonfinite_or_malformed_solution")
    if (
        velocity.shape != (points.size,)
        or dual.shape != (len(labels),)
        or not np.all(np.isfinite(velocity))
        or not np.all(np.isfinite(dual))
    ):
        return failure("nonfinite_or_malformed_solution")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            values = matrix @ velocity
            margins = np.minimum(values - lower, upper - values)
            minimum_margin = float(np.min(margins))
            stationarity = float(np.max(np.abs(velocity - nominal.ravel() + matrix.T @ dual)))
            # OSQP uses positive multipliers for upper bounds and negative ones
            # for lower bounds. Stationarity alone cannot reject an arbitrary
            # feasible command with invented multipliers on inactive bounds.
            positive = dual > 0.0
            negative = dual < 0.0
            finite_upper = np.isfinite(upper)
            finite_lower = np.isfinite(lower)
            invalid_sign = (positive & ~finite_upper) | (negative & ~finite_lower)
            dual_feasibility = float(np.max(np.where(invalid_sign, np.abs(dual), 0.0)))
            complementarity = np.zeros_like(dual)
            upper_duals = positive & finite_upper
            lower_duals = negative & finite_lower
            complementarity[upper_duals] = np.abs(
                dual[upper_duals] * (upper[upper_duals] - values[upper_duals])
            )
            complementarity[lower_duals] = np.abs(
                dual[lower_duals] * (values[lower_duals] - lower[lower_duals])
            )
            raw_complementarity = float(np.max(complementarity))
            normalized_complementarity = float(np.max(complementarity / (1.0 + np.abs(dual))))
            command = velocity.reshape(points.shape)
            endpoint = points + dt * command
            minimum_distance = _segment_minimum(points, dt * command)
            maximum_speed = float(np.max(np.linalg.norm(command, axis=1)))
            domain_violation = max(0.0, float(np.max(-endpoint)), float(np.max(endpoint - bounds)))
            modification = float(np.linalg.norm(command - nominal))
            objective = 0.5 * modification**2
        if not all(
            np.isfinite(value)
            for value in (
                minimum_margin,
                stationarity,
                dual_feasibility,
                raw_complementarity,
                normalized_complementarity,
                maximum_speed,
                domain_violation,
                modification,
                objective,
            )
        ):
            return failure("nonfinite_solution_verification")
    except (OverflowError, FloatingPointError):
        return failure("nonfinite_solution_verification")
    log.update(
        stationarity_residual=stationarity,
        dual_feasibility_residual=dual_feasibility,
        complementarity_residual=raw_complementarity,
        normalized_complementarity_residual=normalized_complementarity,
        min_linear_margin=minimum_margin,
        max_constraint_violation=max(0.0, -minimum_margin),
        segment_min_separation=minimum_distance,
        max_speed_observed=maximum_speed,
        domain_violation=domain_violation,
        modification_norm=modification,
        objective=objective,
        active_constraints=[
            label
            for label, margin in zip(labels, margins, strict=True)
            if margin <= settings.acceptance_tol
        ],
    )
    tolerance = settings.acceptance_tol
    if minimum_margin < -tolerance:
        return failure("linear_constraint_violation")
    if stationarity > tolerance:
        return failure("stationarity_residual_exceeds_tolerance")
    if dual_feasibility > tolerance:
        return failure("dual_feasibility_residual_exceeds_tolerance")
    if normalized_complementarity > tolerance:
        return failure("complementarity_residual_exceeds_tolerance")
    if maximum_speed > max_speed + tolerance:
        return failure("euclidean_speed_violation")
    if domain_violation > tolerance:
        return failure("rectangular_domain_violation")
    if minimum_distance is not None and minimum_distance < min_separation - tolerance:
        return failure("continuous_segment_separation_violation")
    log["success"] = True
    log["control_s"] = perf_counter() - started
    return QPResult(velocity=command.copy(), success=True, log=log)
