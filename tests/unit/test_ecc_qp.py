"""The ECC per-robot QP: eqs. (10)/(17) optima, the barrier row, and honest failure."""

from __future__ import annotations

import math

import numpy as np
import pytest

from attain_sampling.control.ecc_qp import EccQPSettings, solve_robot_qp
from attain_sampling.control.rate_constraint import DecayConstraintRow
from attain_sampling.sources.ecc2025 import parameters

PAPER = parameters()


def settings(**overrides) -> EccQPSettings:
    options = {
        "epsilon_opt": PAPER["epsilon_opt"],
        "d_ca": PAPER["d_ca"],
        "alpha_ca": 1.0,
        "max_speed": 2.0,
    }
    options.update(overrides)
    return EccQPSettings(**options)


def row(xi1, xi2) -> DecayConstraintRow:
    return DecayConstraintRow(
        xi1=np.asarray(xi1, dtype=float),
        xi2=float(xi2),
        h=0.0,
        local_objective=0.0,
        initial_local=0.0,
        evaluation_count=1,
    )


def lone(position=(0.0, 0.0)) -> np.ndarray:
    return np.asarray([position])


def test_constraint_only_optimum_matches_the_closed_form():
    """eq. (10) with the rate row active: u* = -xi2 xi1 / (eps + |xi1|^2)."""
    xi1, xi2 = np.asarray([0.3, -0.2]), -0.5
    result = solve_robot_qp(
        robot=0, positions=lone(), row=row(xi1, xi2), nominal=np.zeros(2), settings=settings()
    )
    assert result.success
    eps = PAPER["epsilon_opt"]
    expected = -xi2 * xi1 / (eps + float(xi1 @ xi1))
    assert result.velocity == pytest.approx(expected, abs=1e-6)
    assert result.slack == pytest.approx(float(xi1 @ expected) + xi2, abs=1e-6)


def test_a_satisfied_rate_row_leaves_the_robot_at_rest_without_slack():
    result = solve_robot_qp(
        robot=0,
        positions=lone(),
        row=row([1.0, 0.0], 0.3),
        nominal=np.zeros(2),
        settings=settings(),
    )
    assert result.success
    assert result.velocity == pytest.approx([0.0, 0.0], abs=1e-6)
    assert result.slack == pytest.approx(0.0, abs=1e-6)
    assert result.rate_satisfied_without_slack


def test_a_flat_variance_landscape_gives_no_motion_the_myopic_deadlock():
    """With xi1 = 0 the constraint-only controller cannot move, however far behind it is."""
    result = solve_robot_qp(
        robot=0,
        positions=lone(),
        row=row([0.0, 0.0], -2.0),
        nominal=np.zeros(2),
        settings=settings(),
    )
    assert result.success
    assert result.velocity == pytest.approx([0.0, 0.0], abs=1e-6)
    assert result.slack == pytest.approx(-2.0, abs=1e-6)
    assert not result.rate_satisfied_without_slack


def test_hierarchical_form_follows_the_nominal_when_the_rate_row_allows_it():
    nominal = np.asarray([0.6, -0.8])
    result = solve_robot_qp(
        robot=0, positions=lone(), row=row([1.0, 0.0], 0.1), nominal=nominal, settings=settings()
    )
    assert result.success
    assert result.velocity == pytest.approx(nominal, abs=1e-6)
    assert result.slack == pytest.approx(0.0, abs=1e-6)


def test_the_speed_bound_holds_for_an_aggressive_nominal():
    kappa = PAPER["kappa"]
    nominal = kappa * np.asarray([10.0, 0.0])  # the paper's gain on a 10 m waypoint
    result = solve_robot_qp(
        robot=0, positions=lone(), row=row([0.0, 0.0], 0.0), nominal=nominal, settings=settings()
    )
    assert result.success
    assert np.linalg.norm(result.velocity) <= 2.0 + 1e-6
    # The inscribed polygon leaves the robot heading toward its waypoint.
    assert result.velocity[0] > 1.8
    assert abs(result.velocity[1]) < 1e-6


def test_the_barrier_row_slows_a_robot_driving_into_a_neighbour():
    positions = np.asarray([[0.0, 0.0], [4.0, 0.0]])
    nominal = np.asarray([2.0, 0.0])  # straight at the neighbour
    result = solve_robot_qp(
        robot=0, positions=positions, row=row([0.0, 0.0], 0.0), nominal=nominal, settings=settings()
    )
    assert result.success
    offset = positions[0] - positions[1]
    h = float(offset @ offset) - PAPER["d_ca"] ** 2
    assert float(2.0 * offset @ result.velocity) + 1.0 * h >= -1e-7
    assert result.velocity[0] < 2.0 - 0.1


def test_a_barrier_that_cannot_be_met_within_the_speed_bound_is_rejected():
    # Already inside the minimum distance and required to separate faster than allowed.
    positions = np.asarray([[0.0, 0.0], [0.2, 0.0]])
    result = solve_robot_qp(
        robot=0,
        positions=positions,
        row=row([0.0, 0.0], 0.0),
        nominal=np.zeros(2),
        settings=settings(alpha_ca=50.0, max_speed=0.5),
    )
    assert not result.success
    assert result.velocity is None
    assert result.slack is None


def test_result_record_is_json_safe():
    result = solve_robot_qp(
        robot=0,
        positions=lone(),
        row=row([0.2, 0.1], -1.0),
        nominal=np.zeros(2),
        settings=settings(),
    )
    record = result.as_dict()
    assert isinstance(record["velocity"], list)
    assert math.isfinite(record["wall_s"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"epsilon_opt": 0.0},
        {"d_ca": -1.0},
        {"alpha_ca": math.nan},
        {"max_speed": 0.0},
        {"polygon_sides": 2},
        {"max_iter": 0},
    ],
)
def test_invalid_settings_are_rejected(overrides):
    with pytest.raises(ValueError):
        settings(**overrides)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"robot": 3},
        {"robot": True},
        {"positions": np.zeros((2, 3))},
        {"nominal": np.asarray([math.inf, 0.0])},
    ],
)
def test_invalid_calls_are_rejected(kwargs):
    options = {
        "robot": 0,
        "positions": np.zeros((2, 2)) + np.asarray([[0.0, 0.0], [5.0, 0.0]]),
        "row": row([0.0, 0.0], 0.0),
        "nominal": np.zeros(2),
        "settings": settings(),
    }
    options.update(kwargs)
    with pytest.raises(ValueError):
        solve_robot_qp(**options)


def test_far_neighbours_do_not_stall_the_solver_regression():
    """Captured from a 1000 s run: loose barrier rows ~1e4 once stalled Clarabel."""
    captured = row([0.12366634, -0.12640571], -1.9933713129520099)
    positions = np.asarray(
        [[-48.1085583, 18.9831273], [0.0, -11.0081339], [48.1085583, 18.9831273]]
    )
    result = solve_robot_qp(
        robot=0, positions=positions, row=captured, nominal=np.zeros(2), settings=settings()
    )
    assert result.success, result.status
    # The unconstrained optimum points at -45.6 deg and exceeds 2 m/s, so it lands on the
    # polygon vertex at -45 deg.
    assert result.velocity == pytest.approx([math.sqrt(2.0), -math.sqrt(2.0)], abs=1e-6)


@pytest.mark.parametrize("gap", [3.2, 4.0, 6.0, 30.0])
def test_dropping_implied_barrier_rows_never_changes_the_answer(gap):
    """A row is dropped only if no admissible velocity can violate it."""
    positions = np.asarray([[0.0, 0.0], [gap, 0.0]])
    nominal = np.asarray([30.0, 0.0])
    result = solve_robot_qp(
        robot=0, positions=positions, row=row([0.0, 0.0], 0.0), nominal=nominal, settings=settings()
    )
    assert result.success
    offset = positions[0] - positions[1]
    h = float(offset @ offset) - PAPER["d_ca"] ** 2
    assert float(2.0 * offset @ result.velocity) + h >= -1e-7
    assert np.linalg.norm(result.velocity) <= 2.0 + 1e-7
