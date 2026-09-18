"""Types shared by future attainability estimators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from attain_sampling.gp.protocol import GPBelief, VarianceKind

FloatArray = NDArray[np.float64]
CertificateScope = Literal[
    "none",
    "exact-gp-frozen-kernel",
    "frozen-dictionary-surrogate",
    "scenario-only",
]


@dataclass(frozen=True, slots=True)
class Budget:
    remaining_samples: int
    remaining_time_s: float


@dataclass(frozen=True, slots=True)
class AttainabilityEstimate:
    """Reference curve plus the provenance needed to interpret its bound.

    The fields intentionally distinguish a computed executable upper candidate from a
    mathematical certificate.  A caller must never infer certificate scope merely from
    ``feasible=True``.
    """

    reference_curve: FloatArray
    terminal_upper_bound: float
    optimistic_lower_bound: float | None
    planned_gains: FloatArray
    contraction_schedule: FloatArray
    calibration_margin: float
    feasible: bool
    rollout_backend: str
    evaluation_set_hash: str
    variance_kind: VarianceKind
    kernel_hyperparameters_frozen: bool
    rollout_coverage_complete: bool
    execution_validated: bool
    certificate_eligible: bool
    certificate_scope: CertificateScope


@runtime_checkable
class AttainabilityEstimator(Protocol):
    def estimate(
        self,
        belief: GPBelief,
        robot_state: FloatArray,
        remaining_budget: Budget,
    ) -> AttainabilityEstimate:
        """Estimate an attainable curve without future labels or ground truth."""
        ...
