"""The ECC 2025 variance-decay performance constraint (M5, source profile).

M1 deliberately shipped a tracking QP with **no** GP performance constraint, because the
paper's inequality could not be written down without the full text. The text was audited
on 15 September 2026, so this module implements it from the cited equations.

Anchor: Suenaga, Hanif, Uto and Hatanaka, ECC 2025, pp. 304-311,
doi:10.23919/ECC65951.2025.11187026. Ledger topics T01, T02, T05, T07.

What the paper states
---------------------
Objective, p. 306 — an **unnormalized sum** of latent variances over a finite set::

    J = sum_{x in F_d} sigma^2(x),   sigma^2(x) = k(x,x) + k_{x,l}^T C_l k_{x,l}

Decomposition, pp. 306-307 — Voronoi cells, then a per-robot approximation that keeps
only robot ``i``'s own position in the virtual basis set::

    I_il(t)      = sum_{x in F_d cap V_i} sigma~^2(x; Z~_t[l])
    I~_il(t)     = sum_{x in F_d cap V_i} sigma~^2(x; Z~_ti[l]),  Z~_ti[l] = Z[l] + p_i(t)

Constraint, p. 307 — with ``h_Ji = I_i0 - gamma t / (n t_s) - I~_il(t)`` and a linear
extended class-K function ``alpha_J(h) = alpha_J h`` (the paper reuses the symbol for the
function and its gain), eq. (8) ``hdot_Ji + alpha_J(h_Ji) >= 0`` becomes the linear row
of eq. (11)::

    xi_i1^T u_i + xi_i2 >= w_i

Row, eqs. (12)-(13) and (15), pp. 307-308, using ``C~_li = -(K~_tl + sigma_eps^2 I)^-1``
over the basis set augmented with ``p_i(t)``, and ``z_* = C~_li k_*``::

    xi_i1 = 2 sum_x [ [z_*]_{N+1} k(p_i,x)/L^2 (p_i - x)
                      + sum_{j<=N} [z_*]_j k(p_i,x_j)/L^2 (p_i - x_j) ]
    xi_i2 = -gamma/(n t_s) - alpha_J( I~_il(t) + gamma t/(n t_s) - I_i0 )

Reading decisions
-----------------
Two places where the printed equation (12) does not match the paper's own derivation on
the same pages. Both are resolved in favour of the derivation, because ``xi_i1`` is
defined as the gradient of ``I~_il`` and only that reading satisfies eq. (15). Both are
pinned down by a finite-difference test against ``I~_il`` itself.

1. **Summation set.** (12) sums over ``x_* in F_d`` while ``I_il``, ``I~_il`` and the
   derivation of (14)-(15) all restrict to ``F_d cap V_i``.
2. **Missing factor.** In (12) the basis term carries only ``[z_*]_j``. Expanding (14)
   gives ``2 [z_*]_{N+1} ( kdot(p_i,x_*) + sum_j [z_*]_j kdot(p_i,x_j) )``: because only
   the appended row of ``k_*`` and the last row/column of ``K~_tl`` depend on ``p_i``,
   **both** terms carry ``[z_*]_{N+1}``. Numerically, the derivation form reproduces
   ``d I~_il / dt = -xi_i1^T u_i`` to ~1e-10 while the printed grouping departs from it
   by up to 4e-2 on the same configurations.

These are recorded readings of the source, not claims about the paper's results; the
substantive content of Theorem 1 is unaffected.

``I_i0`` is stated as the value of ``I_il(t)`` at ``t = t_1`` (p. 307). It is supplied by
the caller and is never recomputed here, so the reference cannot drift silently.

Limits
------
This is the paper's constraint row, not a safety certificate and not a guarantee that the
requested decay is attainable: the paper itself states (p. 306) that meeting its decay
constraint for all ``l`` is infeasible and targets only the transient. ``alpha_ca``, the
input set ``U`` and the control period are **not stated** in the source and remain
recorded project choices elsewhere.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.linalg import cho_solve

from attain_sampling.gp.protocol import FloatArray

__all__ = [
    "DecayConstraintRow",
    "EpochDecayCache",
    "decay_constraint_row",
    "local_objective",
    "paper_objective",
    "rbf_kernel",
    "voronoi_owner",
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


def rbf_kernel(
    a: FloatArray, b: FloatArray, length_scale: float, signal_variance: float = 1.0
) -> FloatArray:
    """The paper's RBF, Theorem 1 p. 307.

    Theorem 1 prints no signal-variance prefactor, so the source default is ``k(x,x) = 1``.
    ``signal_variance`` exists only for the figure-scale sensitivity profile: Fig. 3
    starts at ``J[0] ~ 3600`` on 900 points, which a unit prefactor cannot produce.
    """
    left = _finite_points(a, "a")
    right = _finite_points(b, "b")
    scale = _positive(length_scale, "length_scale")
    amplitude = _positive(signal_variance, "signal_variance")
    squared = np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2)
    return np.asarray(amplitude * np.exp(-squared / (2.0 * scale**2)), dtype=np.float64)


def voronoi_owner(queries: FloatArray, positions: FloatArray) -> np.ndarray:
    """Nearest-robot index per evaluation point (p. 306 Voronoi cells).

    Ties go to the lowest robot index, so the cells partition the evaluation set exactly
    once and no point is counted twice in the decomposition.
    """
    points = _finite_points(queries, "queries")
    robots = _finite_points(positions, "positions")
    if not len(robots):
        raise ValueError("positions must contain at least one robot")
    distances = np.linalg.norm(points[:, None, :] - robots[None, :, :], axis=2)
    return np.asarray(np.argmin(distances, axis=1), dtype=np.int64)


def _augmented_posterior(
    basis: FloatArray,
    position: FloatArray,
    queries: FloatArray,
    length_scale: float,
    noise_variance: float,
    signal_variance: float,
) -> tuple[FloatArray, FloatArray]:
    """Return ``(sigma2, z)`` for the basis set augmented with the robot position.

    ``C~_li = -(K~_tl + sigma_eps^2 I)^-1`` (proof of Theorem 1, p. 308), so
    ``sigma~^2(x) = k(x,x) - k_*^T (K~ + sigma_eps^2 I)^-1 k_*`` and ``z_* = C~_li k_*``.
    Labels never enter, exactly as the paper notes on p. 306.
    """
    augmented = np.vstack((basis, position[None, :])) if len(basis) else position[None, :]
    gram = rbf_kernel(augmented, augmented, length_scale, signal_variance)
    gram[np.diag_indices_from(gram)] += noise_variance
    cross = rbf_kernel(augmented, queries, length_scale, signal_variance)
    try:
        factor = np.linalg.cholesky(gram)
    except np.linalg.LinAlgError as error:  # pragma: no cover - guarded by noise term
        raise FloatingPointError("augmented kernel matrix is not positive definite") from error
    solved = np.linalg.solve(factor.T, np.linalg.solve(factor, cross))
    variance = signal_variance - np.sum(cross * solved, axis=0)
    return np.asarray(variance, dtype=np.float64), np.asarray(-solved, dtype=np.float64)


def local_objective(
    *,
    basis: FloatArray,
    position: FloatArray,
    queries: FloatArray,
    length_scale: float,
    noise_variance: float,
    signal_variance: float = 1.0,
) -> float:
    """``I~_il(t)``: the paper's per-robot unnormalized latent-variance sum (p. 307)."""
    points = _finite_points(queries, "queries")
    if not len(points):
        return 0.0
    variance, _ = _augmented_posterior(
        _finite_points(basis, "basis") if len(np.asarray(basis)) else np.empty((0, 2)),
        np.asarray(position, dtype=np.float64).reshape(2),
        points,
        _positive(length_scale, "length_scale"),
        _positive(noise_variance, "noise_variance"),
        _positive(signal_variance, "signal_variance"),
    )
    return float(np.sum(variance))


def paper_objective(variance: FloatArray) -> float:
    """``J = sum_{x in F_d} sigma^2(x)`` (p. 306) — a sum, never a mean."""
    values = np.asarray(variance, dtype=np.float64)
    if values.ndim != 1 or not len(values):
        raise ValueError("variance must be a nonempty one-dimensional array")
    if not np.all(np.isfinite(values)):
        raise ValueError("variance must be finite")
    return float(np.sum(values))


@dataclass(frozen=True, slots=True)
class DecayConstraintRow:
    """One robot's linear row ``xi1 @ u + xi2 >= w`` plus the quantities behind it."""

    xi1: FloatArray
    xi2: float
    h: float
    local_objective: float
    initial_local: float
    evaluation_count: int

    def satisfied_by(self, velocity: FloatArray, slack: float = 0.0) -> bool:
        """Whether a command meets the row; slack relaxes it exactly as in eq. (10)."""
        command = np.asarray(velocity, dtype=np.float64).reshape(2)
        return bool(float(self.xi1 @ command) + self.xi2 >= slack)

    def as_dict(self) -> dict[str, Any]:
        return {
            "xi1": self.xi1.tolist(),
            "xi2": self.xi2,
            "h": self.h,
            "local_objective": self.local_objective,
            "initial_local": self.initial_local,
            "evaluation_count": self.evaluation_count,
            "convention": "xi1 @ u + xi2 >= w_i (eq. (11), p. 307)",
            "scope": (
                "ECC 2025 decay-rate row; not a safety certificate and not a claim that "
                "the requested decay is attainable"
            ),
        }


@dataclass(frozen=True, slots=True)
class _RowTerms:
    level: float
    period: float
    gain: float
    robots: int
    elapsed: float
    initial: float


def _row_terms(
    gamma: float,
    robot_count: int,
    sample_period_s: float,
    elapsed_s: float,
    initial_local: float,
    alpha_j: float,
) -> _RowTerms:
    if isinstance(robot_count, bool) or not isinstance(robot_count, int) or robot_count < 1:
        raise ValueError("robot_count must be a positive integer")
    for name, value in (("elapsed_s", elapsed_s), ("initial_local", initial_local)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a real number")
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
    if float(elapsed_s) < 0:
        raise ValueError("elapsed_s must be non-negative")
    return _RowTerms(
        level=_positive(gamma, "gamma"),
        period=_positive(sample_period_s, "sample_period_s"),
        gain=_positive(alpha_j, "alpha_j"),
        robots=robot_count,
        elapsed=float(elapsed_s),
        initial=float(initial_local),
    )


def _finish_row(
    terms: _RowTerms, current: float, gradient: FloatArray, count: int
) -> DecayConstraintRow:
    slope = terms.level / (terms.robots * terms.period)
    h = terms.initial - slope * terms.elapsed - current
    xi2 = -slope + terms.gain * h
    if not math.isfinite(xi2) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("decay-rate row is not finite")
    return DecayConstraintRow(
        xi1=np.asarray(gradient, dtype=np.float64),
        xi2=float(xi2),
        h=h,
        local_objective=current,
        initial_local=terms.initial,
        evaluation_count=count,
    )


def _gradient(
    robot: FloatArray,
    points: FloatArray,
    vectors: FloatArray,
    appended: FloatArray,
    weights: FloatArray,
    scale: float,
    amplitude: float,
) -> FloatArray:
    """eq. (12) as the derivation of (14)-(15) requires; see the module docstring."""
    own = rbf_kernel(robot[None, :], points, scale, amplitude)[0]
    gradient = 2.0 * np.sum((appended * own)[:, None] * (robot[None, :] - points), axis=0)
    if len(vectors):
        basis_kernel = rbf_kernel(robot[None, :], vectors, scale, amplitude)[0]
        gradient = gradient + 2.0 * np.sum(
            (weights * basis_kernel)[:, None] * (robot[None, :] - vectors), axis=0
        )
    return np.asarray(gradient / scale**2, dtype=np.float64)


def decay_constraint_row(
    *,
    basis: FloatArray,
    position: FloatArray,
    queries: FloatArray,
    length_scale: float,
    noise_variance: float,
    gamma: float,
    robot_count: int,
    sample_period_s: float,
    elapsed_s: float,
    initial_local: float,
    alpha_j: float,
    signal_variance: float = 1.0,
) -> DecayConstraintRow:
    """Build eqs. (12)-(13) for one robot from its Voronoi share of the evaluation set.

    This is the reference implementation. ``queries`` must already be restricted to
    ``F_d cap V_i``. An empty share yields a zero gradient: the robot's motion then cannot
    change ``I~_il``, which is a statement about this decomposition, not about the fleet.
    """
    points = _finite_points(queries, "queries")
    robot = np.asarray(position, dtype=np.float64).reshape(2)
    if not np.all(np.isfinite(robot)):
        raise ValueError("position must be finite")
    vectors = _finite_points(basis, "basis") if np.asarray(basis).size else np.empty((0, 2))
    scale = _positive(length_scale, "length_scale")
    noise = _positive(noise_variance, "noise_variance")
    amplitude = _positive(signal_variance, "signal_variance")
    terms = _row_terms(gamma, robot_count, sample_period_s, elapsed_s, initial_local, alpha_j)
    if not len(points):
        return _finish_row(terms, 0.0, np.zeros(2), 0)
    variance, z = _augmented_posterior(vectors, robot, points, scale, noise, amplitude)
    appended = z[-1, :]
    weights = np.sum(z[:-1, :] * appended[None, :], axis=1)
    gradient = _gradient(robot, points, vectors, appended, weights, scale, amplitude)
    return _finish_row(terms, float(np.sum(variance)), gradient, len(points))


class EpochDecayCache:
    """The same row as :func:`decay_constraint_row`, amortised over one sampling epoch.

    The basis set ``Z[l]`` only changes at sampling instants, so ``(K_ZZ + sigma^2 I)`` is
    factorised once per epoch. Appending ``p_i(t)`` is then a Schur-complement update:
    each control step costs ``O(N^2 + N M)`` instead of ``O(N^3)``. A test pins this path
    to the reference implementation.
    """

    def __init__(
        self,
        *,
        basis: FloatArray,
        queries: FloatArray,
        length_scale: float,
        noise_variance: float,
        signal_variance: float = 1.0,
    ) -> None:
        self._points = _finite_points(queries, "queries")
        self._vectors = (
            _finite_points(basis, "basis") if np.asarray(basis).size else np.empty((0, 2))
        )
        self._scale = _positive(length_scale, "length_scale")
        self._noise = _positive(noise_variance, "noise_variance")
        self._amplitude = _positive(signal_variance, "signal_variance")
        if len(self._vectors):
            gram = rbf_kernel(self._vectors, self._vectors, self._scale, self._amplitude)
            gram[np.diag_indices_from(gram)] += self._noise
            try:
                self._factor = np.linalg.cholesky(gram)
            except np.linalg.LinAlgError as error:  # pragma: no cover - noise guards it
                raise FloatingPointError("basis kernel matrix is not positive definite") from error
            cross = rbf_kernel(self._vectors, self._points, self._scale, self._amplitude)
            self._solved = self._solve(cross)
            self._base = np.sum(cross * self._solved, axis=0)
        else:
            self._factor = np.empty((0, 0))
            self._solved = np.empty((0, len(self._points)))
            self._base = np.zeros(len(self._points))

    def _solve(self, rhs: FloatArray) -> FloatArray:
        # Two triangular solves: O(N^2) per column, not a general O(N^3) solve.
        return np.asarray(cho_solve((self._factor, True), rhs), dtype=np.float64)

    @property
    def basis_size(self) -> int:
        return len(self._vectors)

    def row(
        self,
        *,
        position: FloatArray,
        selection: np.ndarray,
        gamma: float,
        robot_count: int,
        sample_period_s: float,
        elapsed_s: float,
        initial_local: float,
        alpha_j: float,
    ) -> DecayConstraintRow:
        """Row for one robot; ``selection`` indexes its Voronoi share of the queries."""
        robot = np.asarray(position, dtype=np.float64).reshape(2)
        if not np.all(np.isfinite(robot)):
            raise ValueError("position must be finite")
        chosen = np.asarray(selection)
        if chosen.dtype == bool:
            chosen = np.flatnonzero(chosen)
        terms = _row_terms(gamma, robot_count, sample_period_s, elapsed_s, initial_local, alpha_j)
        if not len(chosen):
            return _finish_row(terms, 0.0, np.zeros(2), 0)
        points = self._points[chosen]
        own = rbf_kernel(robot[None, :], points, self._scale, self._amplitude)[0]
        prior = self._amplitude + self._noise
        if len(self._vectors):
            b = rbf_kernel(self._vectors, robot[None, :], self._scale, self._amplitude)[:, 0]
            solved_b = self._solve(b[:, None])[:, 0]
            schur = prior - float(b @ solved_b)
            columns = self._solved[:, chosen]
            t = (own - b @ columns) / schur
            base = self._base[chosen]
            # Block inverse of the augmented Gram matrix applied to k_*:
            # [A^-1 k_Z - A^-1 b t ; t]; z_* is its negative.
            appended = -t
            weights = np.sum(columns * t[None, :], axis=1) - solved_b * float(t @ t)
        else:
            schur = prior
            t = own / schur
            base = np.zeros(len(chosen))
            appended = -t
            weights = np.empty(0)
        if schur <= 0 or not math.isfinite(schur):
            raise FloatingPointError("Schur complement of the augmented basis is not positive")
        variance = self._amplitude - base - schur * t * t
        gradient = _gradient(
            robot, points, self._vectors, appended, weights, self._scale, self._amplitude
        )
        return _finish_row(terms, float(np.sum(variance)), gradient, len(chosen))
