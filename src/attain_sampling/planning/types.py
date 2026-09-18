"""Data contracts for executable sampling plans."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Plan:
    """A time-parametrized candidate plan, not an optimality certificate."""

    waypoints: FloatArray
    sample_times_s: FloatArray
    joint_sample_locations: FloatArray
    predicted_terminal_objective: float | None
    feasibility_checks: Mapping[str, bool]

    @property
    def geometrically_feasible(self) -> bool:
        return bool(self.feasibility_checks) and all(self.feasibility_checks.values())
