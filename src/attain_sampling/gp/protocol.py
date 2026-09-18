"""Explicit GP contracts that prevent latent/predictive variance ambiguity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
VarianceKind = Literal["latent", "predictive"]


@dataclass(frozen=True, slots=True)
class GPPrediction:
    mean: FloatArray
    variance: FloatArray
    variance_kind: VarianceKind


@runtime_checkable
class GPBelief(Protocol):
    def predict(self, x: FloatArray, *, variance: VarianceKind) -> GPPrediction:
        """Predict with an explicitly selected variance semantic."""
        ...

    def update(self, x: FloatArray, y: FloatArray) -> None:
        """Incorporate observations according to the concrete backend."""
        ...


class CovarianceBelief(GPBelief, Protocol):
    """Fixed-parameter belief queried by planners, not a future update oracle."""

    @property
    def length_scale(self) -> float: ...

    @property
    def signal_variance(self) -> float: ...

    @property
    def noise_variance(self) -> float: ...

    @property
    def jitter(self) -> float: ...

    @property
    def observation_count(self) -> int: ...

    @property
    def backend_name(self) -> str: ...

    @property
    def forecast_scope(self) -> str: ...

    def posterior_covariance(self, a: FloatArray, b: FloatArray | None = None) -> FloatArray: ...

    def fantasy_variance(self, query: FloatArray, samples: FloatArray) -> FloatArray:
        """Condition current covariance without forecasting adaptive dictionary changes."""
        ...
