"""Fixed-hyperparameter exact GP oracle for the independent mapping simulator.

The kernel is an isotropic squared exponential and the prior mean is zero. All
variances use field-value-squared units; ``signal_variance`` is not a standard
deviation. A fixed diagonal jitter of ``1e-10 * signal_variance`` stabilizes each
Cholesky factorization, including noiseless repeated points. This numerical
regularizer is separate from the physical observation-noise variance.

This backend is independent of the ECC 2025 implementation. Its covariance-only
fantasies are label-free because the hyperparameters and observation noise stay
fixed; this is not a claim about online hyperparameter fitting or SOGP pruning.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import solve_triangular

from attain_sampling.gp.protocol import FloatArray, GPPrediction, VarianceKind


def _points(value: FloatArray, name: str) -> FloatArray:
    points = np.asarray(value, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError(f"{name} must have shape (n, 2)")
    if not np.all(np.isfinite(points)):
        raise ValueError(f"{name} must contain only finite coordinates")
    return points


def _solve(factor: FloatArray, rhs: FloatArray, *, transpose: bool = False) -> FloatArray:
    return np.asarray(
        solve_triangular(factor, rhs, lower=True, trans="T" if transpose else "N"),
        dtype=np.float64,
    )


class ExactGP:
    """Accumulating, two-dimensional exact GP with a cached Cholesky factor.

    Prediction requires an explicit variance semantic: ``latent`` describes the
    unknown field, while ``predictive`` adds noise for a new noisy observation.
    Inputs passed to ``update`` are copied so caller mutation cannot corrupt the
    posterior. The model parameters are read-only for the lifetime of a belief.
    """

    def __init__(
        self,
        *,
        length_scale: float = 8.0,
        signal_variance: float = 1.0,
        noise_variance: float = 0.04,
    ) -> None:
        for name, value in (
            ("length_scale", length_scale),
            ("signal_variance", signal_variance),
            ("noise_variance", noise_variance),
        ):
            if not np.isfinite(value) or value < 0 or (name != "noise_variance" and value == 0):
                qualifier = "non-negative" if name == "noise_variance" else "positive"
                raise ValueError(f"{name} must be finite and {qualifier}")
        self._length_scale = float(length_scale)
        self._signal_variance = float(signal_variance)
        self._noise_variance = float(noise_variance)
        self._x = np.empty((0, 2), dtype=np.float64)
        self._y = np.empty(0, dtype=np.float64)
        self._factor: FloatArray | None = None
        self._alpha: FloatArray | None = None

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
    def observation_count(self) -> int:
        return len(self._y)

    @property
    def backend_name(self) -> str:
        return "exact"

    @property
    def forecast_scope(self) -> str:
        return "current_fixed_exact_gp_nominal_locations_all_future_samples_received"

    @property
    def jitter(self) -> float:
        """Numerical diagonal regularizer, not additional sensor noise."""
        return 1e-10 * self.signal_variance

    def _kernel(self, a: FloatArray, b: FloatArray) -> FloatArray:
        difference = (a[:, None, :] - b[None, :, :]) / self.length_scale
        distance_squared = np.sum(difference * difference, axis=2)
        return np.asarray(self.signal_variance * np.exp(-0.5 * distance_squared))

    def _cholesky(self, covariance: FloatArray) -> FloatArray:
        regularized = covariance.copy()
        regularized.flat[:: len(covariance) + 1] += self.noise_variance + self.jitter
        try:
            return np.asarray(np.linalg.cholesky(regularized), dtype=np.float64)
        except np.linalg.LinAlgError as error:
            raise FloatingPointError(
                "GP covariance could not be factorized with the documented jitter"
            ) from error

    def _ensure_cache(self) -> tuple[FloatArray, FloatArray]:
        if self._factor is None or self._alpha is None:
            self._factor = self._cholesky(self._kernel(self._x, self._x))
            self._alpha = _solve(self._factor, _solve(self._factor, self._y), transpose=True)
        return self._factor, self._alpha

    def _nonnegative(self, value: FloatArray) -> FloatArray:
        tolerance = 1e-8 * self.signal_variance
        if not np.all(np.isfinite(value)) or np.any(value < -tolerance):
            raise FloatingPointError("GP produced non-finite or materially negative variance")
        return np.maximum(value, 0.0)

    def update(self, x: FloatArray, y: FloatArray) -> None:
        """Append noisy observations; an empty, correctly shaped batch is a no-op."""
        points = _points(x, "x")
        labels = np.asarray(y, dtype=np.float64)
        if labels.ndim != 1 or labels.shape[0] != len(points):
            raise ValueError("y must have shape (n,) matching x")
        if not np.all(np.isfinite(labels)):
            raise ValueError("y must contain only finite values")
        if not len(points):
            return
        self._x = np.concatenate((self._x, points))
        self._y = np.concatenate((self._y, labels))
        self._factor = None
        self._alpha = None

    def predict(self, x: FloatArray, *, variance: VarianceKind) -> GPPrediction:
        """Return posterior mean and diagonal latent or noisy-predictive variance."""
        if variance not in ("latent", "predictive"):
            raise ValueError("variance must be 'latent' or 'predictive'")
        points = _points(x, "x")
        mean = np.zeros(len(points), dtype=np.float64)
        diagonal = np.full(len(points), self.signal_variance, dtype=np.float64)
        if self.observation_count and len(points):
            factor, alpha = self._ensure_cache()
            cross = self._kernel(self._x, points)
            mean = cross.T @ alpha
            projected = _solve(factor, cross)
            diagonal -= np.sum(projected * projected, axis=0)
        diagonal = self._nonnegative(diagonal)
        if variance == "predictive":
            diagonal += self.noise_variance
        return GPPrediction(mean=mean, variance=diagonal, variance_kind=variance)

    def posterior_covariance(self, a: FloatArray, b: FloatArray | None = None) -> FloatArray:
        """Latent posterior cross-covariance; omitting b returns a symmetric matrix."""
        first = _points(a, "a")
        second = first if b is None else _points(b, "b")
        covariance = self._kernel(first, second)
        if self.observation_count and len(first) and len(second):
            factor, _ = self._ensure_cache()
            projected_a = _solve(factor, self._kernel(self._x, first))
            projected_b = (
                projected_a if b is None else _solve(factor, self._kernel(self._x, second))
            )
            covariance -= projected_a.T @ projected_b
        if b is None:
            covariance = (covariance + covariance.T) * 0.5
            diagonal = self._nonnegative(np.diag(covariance))
            np.fill_diagonal(covariance, diagonal)
        return covariance

    def fantasy_variance(self, query: FloatArray, samples: FloatArray) -> FloatArray:
        """Latent diagonal after a joint batch of noisy future observations.

        No labels are guessed and the current belief is not mutated. Repeated
        sample sites remain repeated noisy observations. Conditioning is joint,
        so correlated sites do not receive independently summed information gains.
        """
        points = _points(query, "query")
        future = _points(samples, "samples")
        current = self.predict(points, variance="latent").variance
        if not len(future) or not len(points):
            return current
        cross = self.posterior_covariance(points, future)
        future_covariance = self.posterior_covariance(future)
        factor = self._cholesky(future_covariance)
        projected = _solve(factor, cross.T)
        return self._nonnegative(current - np.sum(projected * projected, axis=0))
