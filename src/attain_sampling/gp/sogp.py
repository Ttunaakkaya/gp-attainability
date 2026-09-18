"""Bounded sparse online Gaussian regression (Csato and Opper, 2002).

This is an independent implementation of NCRG/2001/014 (corrected October
2002), equations 9, 11, 16, 23--27 and Gaussian-likelihood equation 31. In
particular, removal uses ``abs(alpha_i) / Q_ii`` and the RKHS projection
downdate, not a KL-removal alternative. It is not an ECC 2025 reproduction.

The stored posterior is ``m(x)=k_B(x) alpha`` and
``cov(x,z)=k(x,z)+k_B(x) C k_B(z).T`` with ``Q=K_BB**-1``. Dictionary
admission uses geometric novelty relative to signal variance; pruning depends
on observed labels. Future conditioning therefore freezes the *current
approximate posterior*, without predicting later admission or removal.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from attain_sampling.gp.exact import _points, _solve
from attain_sampling.gp.protocol import FloatArray, GPPrediction, VarianceKind


@dataclass(slots=True)
class _State:
    basis: FloatArray
    indices: NDArray[np.int64]
    alpha: FloatArray
    c: FloatArray
    q: FloatArray
    observations: int = 0
    admitted: int = 0
    projected: int = 0
    pruned: int = 0


class SparseOnlineGP:
    """Sequential, fixed-budget 2-D RBF GP with transactional batch updates.

    Every received observation is assimilated, in the caller's row order.
    Observation history is not retained: only the dictionary and O(m**2)
    posterior arrays remain. Events cover the last successful nonempty batch
    only; callers wanting a complete audit trail must persist them externally.
    A failed batch leaves both the posterior and its previous events unchanged.

    ``novelty_tolerance`` is dimensionless and lies in [1e-12, 1). The numerical
    lower bound avoids deliberately admitting machine-precision-dependent
    bases. Noise conditioning uses exactly the oracle's 1e-10 * signal_variance
    jitter; that jitter is *not* added to the prior dictionary Gram matrix.
    """

    def __init__(
        self,
        *,
        length_scale: float = 8.0,
        signal_variance: float = 1.0,
        noise_variance: float = 0.04,
        max_basis: int = 64,
        novelty_tolerance: float = 1e-6,
    ) -> None:
        for name, value in (
            ("length_scale", length_scale),
            ("signal_variance", signal_variance),
            ("noise_variance", noise_variance),
        ):
            if not np.isfinite(value) or value < 0 or (name != "noise_variance" and value == 0):
                qualifier = "non-negative" if name == "noise_variance" else "positive"
                raise ValueError(f"{name} must be finite and {qualifier}")
        if isinstance(max_basis, bool) or not isinstance(max_basis, (int, np.integer)):
            raise ValueError("max_basis must be a positive integer")
        if max_basis < 1:
            raise ValueError("max_basis must be a positive integer")
        if not np.isfinite(novelty_tolerance) or not 1e-12 <= novelty_tolerance < 1.0:
            raise ValueError("novelty_tolerance must be finite and in [1e-12, 1)")
        self._length_scale = float(length_scale)
        self._signal_variance = float(signal_variance)
        self._noise_variance = float(noise_variance)
        self._max_basis = int(max_basis)
        self._novelty_tolerance = float(novelty_tolerance)
        self._state = _State(
            np.empty((0, 2)),
            np.empty(0, dtype=np.int64),
            np.empty(0),
            np.empty((0, 0)),
            np.empty((0, 0)),
        )
        self._last_update_events: list[dict[str, Any]] = []

    @property
    def backend_name(self) -> str:
        return "sogp"

    @property
    def forecast_scope(self) -> str:
        return (
            "frozen_current_sogp_posterior_nominal_locations_all_future_samples_received_"
            "no_future_pruning"
        )

    @property
    def length_scale(self) -> float:
        return self._length_scale

    @property
    def signal_variance(self) -> float:
        return self._signal_variance

    @property
    def noise_variance(self) -> float:
        return self._noise_variance

    @property
    def max_basis(self) -> int:
        return self._max_basis

    @property
    def novelty_tolerance(self) -> float:
        return self._novelty_tolerance

    @property
    def jitter(self) -> float:
        return 1e-10 * self.signal_variance

    @property
    def observation_count(self) -> int:
        return self._state.observations

    @property
    def dictionary_size(self) -> int:
        return len(self._state.basis)

    @property
    def admitted_count(self) -> int:
        return self._state.admitted

    @property
    def projected_count(self) -> int:
        return self._state.projected

    @property
    def pruned_count(self) -> int:
        return self._state.pruned

    @property
    def dictionary_points(self) -> FloatArray:
        """Independent copy; caller edits cannot change the dictionary."""
        return self._state.basis.copy()

    @property
    def dictionary_observation_indices(self) -> NDArray[np.int64]:
        """Zero-based indices in the assimilated observation stream."""
        return self._state.indices.copy()

    @property
    def last_update_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._last_update_events)

    @property
    def state_nbytes(self) -> int:
        """Bytes of persistent numeric arrays, excluding Python/event overhead."""
        state = self._state
        return sum(a.nbytes for a in (state.basis, state.indices, state.alpha, state.c, state.q))

    def _kernel(self, a: FloatArray, b: FloatArray) -> FloatArray:
        difference = (a[:, None, :] - b[None, :, :]) / self.length_scale
        return np.asarray(self.signal_variance * np.exp(-0.5 * np.sum(difference**2, axis=2)))

    def _nonnegative(self, value: FloatArray) -> FloatArray:
        if not np.all(np.isfinite(value)) or np.any(value < -1e-8 * self.signal_variance):
            raise FloatingPointError("SOGP produced non-finite or materially negative variance")
        return np.maximum(value, 0.0)

    def _assimilate(self, state: _State, point: FloatArray, label: float) -> dict[str, Any]:
        kernel = self._kernel(state.basis, point[None, :])[:, 0]
        ck = state.c @ kernel
        projection = state.q @ kernel
        raw_gamma = self.signal_variance - float(kernel @ projection)
        gamma = float(self._nonnegative(np.array([raw_gamma]))[0])
        variance = float(self._nonnegative(np.array([self.signal_variance + kernel @ ck]))[0])
        denominator = variance + self.noise_variance + self.jitter
        derivative = (label - float(kernel @ state.alpha)) / denominator
        curvature = -1.0 / denominator
        admit = not len(state.basis) or gamma >= self.novelty_tolerance * self.signal_variance
        event: dict[str, Any] = {
            "observation_index": state.observations,
            "update_kind": "admitted" if admit else "projected",
            "gamma": gamma,
            "gamma_raw": raw_gamma,
            "removed_observation_index": None,
            "removed_position": None,
            "removal_score": None,
            "removed_point_variance_before": None,
            "removed_point_variance_after": None,
            "pruning_variance_jump": None,
        }
        if admit:
            step = np.append(ck, 1.0)
            state.alpha = np.append(state.alpha, 0.0) + derivative * step
            state.c = np.pad(state.c, ((0, 1), (0, 1))) + curvature * np.outer(step, step)
            inverse_step = np.append(projection, -1.0)
            state.q = (
                np.pad(state.q, ((0, 1), (0, 1))) + np.outer(inverse_step, inverse_step) / gamma
            )
            state.basis = np.vstack((state.basis, point))
            state.indices = np.append(state.indices, state.observations)
            state.admitted += 1
            if len(state.basis) > self.max_basis:
                event.update(self._prune(state))
        else:
            step = ck + projection
            state.alpha = state.alpha + derivative * step
            state.c = state.c + curvature * np.outer(step, step)
            state.projected += 1
        state.c = (state.c + state.c.T) * 0.5
        state.q = (state.q + state.q.T) * 0.5
        if any(not np.all(np.isfinite(a)) for a in (state.alpha, state.c, state.q)):
            raise FloatingPointError("SOGP update produced non-finite posterior coefficients")
        if np.any(np.diag(state.q) <= 0):
            raise FloatingPointError("SOGP dictionary inverse lost positive diagonal")
        state.observations += 1
        event["dictionary_size"] = len(state.basis)
        return event

    def _prune(self, state: _State) -> dict[str, Any]:
        # Equation 25: first-index argmin gives deterministic tie handling.
        scores = np.abs(state.alpha) / np.diag(state.q)
        removed = int(np.argmin(scores))
        point = state.basis[removed].copy()
        cross_before = self._kernel(state.basis, point[None, :])[:, 0]
        variance_before = float(
            self._nonnegative(
                np.array([self.signal_variance + cross_before @ state.c @ cross_before])
            )[0]
        )
        keep = np.arange(len(state.basis)) != removed
        qstar = float(state.q[removed, removed])
        qcolumn = state.q[keep, removed]
        ccolumn = state.c[keep, removed]
        cstar = float(state.c[removed, removed])
        removed_observation = int(state.indices[removed])
        # Equation 25 projects the old posterior onto the retained basis.
        ratio = qcolumn / qstar
        state.alpha = state.alpha[keep] - state.alpha[removed] * ratio
        state.c = (
            state.c[np.ix_(keep, keep)]
            + cstar * np.outer(ratio, ratio)
            - np.outer(ratio, ccolumn)
            - np.outer(ccolumn, ratio)
        )
        state.q = state.q[np.ix_(keep, keep)] - np.outer(qcolumn, ratio)
        state.basis = state.basis[keep]
        state.indices = state.indices[keep]
        state.pruned += 1
        cross_after = self._kernel(state.basis, point[None, :])[:, 0]
        variance_after = float(
            self._nonnegative(
                np.array([self.signal_variance + cross_after @ state.c @ cross_after])
            )[0]
        )
        return {
            "removed_observation_index": removed_observation,
            "removed_position": point.tolist(),
            "removal_score": float(scores[removed]),
            "removed_point_variance_before": variance_before,
            "removed_point_variance_after": variance_after,
            "pruning_variance_jump": variance_after - variance_before,
        }

    def update(self, x: FloatArray, y: FloatArray) -> None:
        """Assimilate all rows sequentially, committing only if the batch succeeds."""
        points = _points(x, "x")
        labels = np.asarray(y, dtype=np.float64)
        if labels.ndim != 1 or labels.shape[0] != len(points):
            raise ValueError("y must have shape (n,) matching x")
        if not np.all(np.isfinite(labels)):
            raise ValueError("y must contain only finite values")
        if not len(points):
            return
        old = self._state
        state = _State(
            old.basis.copy(),
            old.indices.copy(),
            old.alpha.copy(),
            old.c.copy(),
            old.q.copy(),
            old.observations,
            old.admitted,
            old.projected,
            old.pruned,
        )
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                events = [
                    self._assimilate(state, point, float(label))
                    for point, label in zip(points, labels, strict=True)
                ]
        except np.linalg.LinAlgError as error:
            raise FloatingPointError("SOGP update could not preserve a finite posterior") from error
        self._state = state
        self._last_update_events = events

    def predict(self, x: FloatArray, *, variance: VarianceKind) -> GPPrediction:
        if variance not in ("latent", "predictive"):
            raise ValueError("variance must be 'latent' or 'predictive'")
        points = _points(x, "x")
        kernel = self._kernel(points, self._state.basis)
        mean = kernel @ self._state.alpha
        diagonal = self._nonnegative(
            self.signal_variance + np.sum((kernel @ self._state.c) * kernel, axis=1)
        )
        if not np.all(np.isfinite(mean)):
            raise FloatingPointError("SOGP produced a non-finite posterior mean")
        if variance == "predictive":
            diagonal = diagonal + self.noise_variance
        return GPPrediction(mean=mean, variance=diagonal, variance_kind=variance)

    def posterior_covariance(self, a: FloatArray, b: FloatArray | None = None) -> FloatArray:
        first = _points(a, "a")
        second = first if b is None else _points(b, "b")
        left = self._kernel(first, self._state.basis)
        right = left if b is None else self._kernel(second, self._state.basis)
        covariance = self._kernel(first, second) + left @ self._state.c @ right.T
        if not np.all(np.isfinite(covariance)):
            raise FloatingPointError("SOGP produced non-finite posterior covariance")
        if b is None:
            covariance = (covariance + covariance.T) * 0.5
            np.fill_diagonal(covariance, self._nonnegative(np.diag(covariance)))
        return covariance

    def fantasy_variance(self, query: FloatArray, samples: FloatArray) -> FloatArray:
        """Condition the frozen current approximate posterior on noisy sites.

        Joint Gaussian conditioning is label-free for this fixed posterior.
        This does not simulate future SOGP pruning and is not an exact-GP or
        attainability certificate. Duplicate sites are distinct noisy samples.
        """
        points = _points(query, "query")
        future = _points(samples, "samples")
        current = self.predict(points, variance="latent").variance
        if not len(points) or not len(future):
            return current
        cross = self.posterior_covariance(points, future)
        covariance = self.posterior_covariance(future)
        covariance.flat[:: len(future) + 1] += self.noise_variance + self.jitter
        try:
            factor = np.asarray(np.linalg.cholesky(covariance), dtype=np.float64)
        except np.linalg.LinAlgError as error:
            raise FloatingPointError(
                "SOGP forecast covariance could not be factorized with the documented jitter"
            ) from error
        projected = _solve(factor, cross.T)
        return self._nonnegative(current - np.sum(projected**2, axis=0))
