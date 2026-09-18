"""Paper-independent field and sensor boundaries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@runtime_checkable
class ScalarField(Protocol):
    def evaluate(self, x: FloatArray) -> FloatArray:
        """Evaluate the noiseless scalar field at one or more 2-D positions."""
        ...


@runtime_checkable
class SensorModel(Protocol):
    def sample(
        self,
        field: ScalarField,
        x: FloatArray,
        rng: np.random.Generator,
    ) -> FloatArray:
        """Sample the field through an explicit random generator."""
        ...
