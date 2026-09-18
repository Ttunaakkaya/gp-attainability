from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any

import numpy as np
import pytest

from attain_sampling.attainability.protocol import (
    AttainabilityEstimate,
    AttainabilityEstimator,
    Budget,
)
from attain_sampling.gp.protocol import GPBelief, GPPrediction
from attain_sampling.planning.types import Plan


class DummyBelief:
    def predict(self, x: np.ndarray[Any, Any], *, variance: str) -> GPPrediction:
        size = x.shape[0]
        return GPPrediction(np.zeros(size), np.ones(size), variance)  # type: ignore[arg-type]

    def update(self, x: np.ndarray[Any, Any], y: np.ndarray[Any, Any]) -> None:
        del x, y


class DummyEstimator:
    def estimate(
        self,
        belief: GPBelief,
        robot_state: np.ndarray[Any, Any],
        remaining_budget: Budget,
    ) -> AttainabilityEstimate:
        del belief, robot_state, remaining_budget
        raise NotImplementedError


def test_gp_prediction_records_explicit_variance_semantics() -> None:
    latent = GPPrediction(np.array([1.0]), np.array([0.25]), "latent")
    predictive = GPPrediction(np.array([1.0]), np.array([0.35]), "predictive")

    assert latent.variance_kind == "latent"
    assert predictive.variance_kind == "predictive"
    with pytest.raises(FrozenInstanceError):
        latent.variance_kind = "predictive"  # type: ignore[misc]


def test_runtime_protocols_accept_structural_implementations() -> None:
    assert isinstance(DummyBelief(), GPBelief)
    assert isinstance(DummyEstimator(), AttainabilityEstimator)


def test_budget_is_an_immutable_explicit_pair() -> None:
    budget = Budget(remaining_samples=12, remaining_time_s=30.0)

    assert budget.remaining_samples == 12
    assert budget.remaining_time_s == 30.0
    with pytest.raises(FrozenInstanceError):
        budget.remaining_samples = 11  # type: ignore[misc]


def test_plan_requires_non_empty_successful_feasibility_checks() -> None:
    points = np.array([[0.0, 0.0], [1.0, 1.0]])
    times = np.array([0.0, 1.0])
    empty = Plan(points, times, points, None, {})
    feasible = Plan(points, times, points, 0.2, {"collision": True, "bounds": True})
    blocked = Plan(points, times, points, 0.2, {"collision": True, "bounds": False})

    assert not empty.geometrically_feasible
    assert feasible.geometrically_feasible
    assert not blocked.geometrically_feasible


def test_protocol_dataclasses_are_frozen_and_slotted() -> None:
    protocol_types = (GPPrediction, Budget, AttainabilityEstimate, Plan)

    for protocol_type in protocol_types:
        assert is_dataclass(protocol_type)
        assert protocol_type.__dataclass_params__.frozen
        assert hasattr(protocol_type, "__slots__")


def test_attainability_estimate_preserves_core_provenance_fields() -> None:
    names = {field.name for field in fields(AttainabilityEstimate)}

    assert {
        "reference_curve",
        "terminal_upper_bound",
        "planned_gains",
        "contraction_schedule",
        "calibration_margin",
        "feasible",
        "rollout_backend",
        "certificate_eligible",
    } <= names
