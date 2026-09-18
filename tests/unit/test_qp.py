"""Analytical and adversarial checks for the actual independent tracking QP."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from attain_sampling.control import QPSettings, solve_tracking_qp
from attain_sampling.control import qp as qp_module


def solve(
    positions: Any,
    nominal: Any,
    **kwargs: Any,
) -> qp_module.QPResult:
    options = {"domain": (20.0, 20.0), "max_speed": 2.0, "min_separation": 2.0, "dt": 0.5}
    options.update(kwargs)
    result = solve_tracking_qp(np.asarray(positions), np.asarray(nominal), **options)
    json.dumps(result.log, allow_nan=False)
    assert result.log["control_s"] >= 0
    assert result.success == result.log["success"]
    if result.success:
        assert result.velocity is not None
        assert result.log["failure_reason"] is None
    else:
        assert result.velocity is None
        assert result.log["failure_reason"]
    return result


def test_unconstrained_command_and_objective() -> None:
    nominal = np.array([[0.25, -0.50], [-0.30, 0.40]])
    result = solve([[5.0, 5.0], [15.0, 15.0]], nominal)
    assert result.success
    np.testing.assert_allclose(result.velocity, nominal, atol=1e-7)
    assert result.log["objective"] < 1e-12
    assert result.log["max_constraint_violation"] <= 1e-7
    assert result.log["stationarity_residual"] <= 1e-7
    assert result.log["dual_feasibility_residual"] <= 1e-7
    assert result.log["normalized_complementarity_residual"] <= 1e-7
    assert result.log["active_constraints"] == []


def test_analytical_head_on_cbf_constraint() -> None:
    # r = (-3, 0), h = 5: 6*(u0x-u1x) <= 5. Symmetry gives +/-5/12.
    result = solve([[5.0, 10.0], [8.0, 10.0]], [[2.0, 0.0], [-2.0, 0.0]])
    assert result.success
    np.testing.assert_allclose(result.velocity, [[5 / 12, 0.0], [-5 / 12, 0.0]], atol=1e-7)
    assert "cbf:0:1" in result.log["active_constraints"]
    assert result.log["segment_min_separation"] == pytest.approx(31 / 12)


def test_long_step_endpoint_plane_dominates_cbf() -> None:
    # CBF alone allows +/-5/12, which would cross in a long dt=10 step.
    result = solve([[5.0, 10.0], [8.0, 10.0]], [[2.0, 0.0], [-2.0, 0.0]], dt=10.0)
    assert result.success
    np.testing.assert_allclose(result.velocity, [[0.05, 0.0], [-0.05, 0.0]], atol=1e-7)
    assert "segment_plane:0:1" in result.log["active_constraints"]
    assert result.log["segment_min_separation"] == pytest.approx(2.0, abs=1e-7)


def test_boundary_tracking_preserves_tangent_motion() -> None:
    result = solve([[0.0, 5.0]], [[-1.0, 0.75]])
    assert result.success
    np.testing.assert_allclose(result.velocity, [[0.0, 0.75]], atol=1e-7)
    assert "domain:0:0" in result.log["active_constraints"]
    assert result.log["segment_min_separation"] is None


def test_endpoint_limit_uses_dt() -> None:
    result = solve([[19.9, 5.0]], [[1.0, 0.0]], dt=0.5)
    assert result.success
    np.testing.assert_allclose(result.velocity, [[0.2, 0.0]], atol=1e-7)


@pytest.mark.parametrize("sides", [4, 8, 16, 32])
def test_inscribed_speed_polygon_has_documented_facet_radius(sides: int) -> None:
    angle = np.pi / sides
    direction = np.array([np.cos(angle), np.sin(angle)])
    result = solve([[10.0, 10.0]], [10.0 * direction], settings=QPSettings(polygon_sides=sides))
    assert result.success
    np.testing.assert_allclose(result.velocity, [2.0 * np.cos(angle) * direction], atol=1e-7)
    assert result.log["max_speed_observed"] == pytest.approx(2.0 * np.cos(angle), abs=1e-7)
    assert result.log["max_speed_observed"] <= 2.0 + 1e-7


def test_polygon_vertex_allows_exact_axis_speed() -> None:
    result = solve([[10.0, 10.0]], [[10.0, 0.0]])
    assert result.success
    np.testing.assert_allclose(result.velocity, [[2.0, 0.0]], atol=1e-7)


def test_crossing_robots_do_not_pass_through_each_other() -> None:
    positions = np.array([[8.0, 10.0], [10.0, 8.0]])
    result = solve(positions, [[2.0, 0.0], [0.0, 2.0]], dt=2.0)
    assert result.success
    assert result.velocity is not None
    for fraction in np.linspace(0.0, 1.0, 1001):
        points = positions + fraction * 2.0 * result.velocity
        assert np.linalg.norm(points[0] - points[1]) >= 2.0 - 1e-7
    assert result.log["segment_min_separation"] >= 2.0 - 1e-7


def test_touching_robots_do_not_move_closer() -> None:
    result = solve([[9.0, 10.0], [11.0, 10.0]], [[2.0, 0.0], [-2.0, 0.0]])
    assert result.success
    np.testing.assert_allclose(result.velocity, np.zeros((2, 2)), atol=1e-7)


def test_four_robots_and_inputs_are_not_mutated() -> None:
    positions = np.array([[0.0, 0.0], [0.0, 20.0], [20.0, 0.0], [20.0, 20.0]])
    nominal = np.array([[-3.0, -4.0], [-2.0, 3.0], [5.0, -3.0], [4.0, 2.0]])
    original_positions, original_nominal = positions.copy(), nominal.copy()
    result = solve(positions, nominal)
    assert result.success
    np.testing.assert_allclose(result.velocity, np.zeros((4, 2)), atol=1e-7)
    np.testing.assert_array_equal(positions, original_positions)
    np.testing.assert_array_equal(nominal, original_nominal)
    assert result.log["constraint_count"] == 4 * 18 + 2 * 6


def test_four_robot_pilot_geometry_meets_absolute_acceptance_tolerance() -> None:
    # Captured from the initial combined/seed7/4-robot pilot at tick2. OSQP's
    # former relative eps=1e-8 accepted a 1.23e-7 speed-facet residual because
    # distant-robot CBF rows increased the relative stopping scale. We retain
    # physical acceptance at 1e-7 and solve to an absolute threshold instead.
    result = solve(
        [
            [3.847604117094991, 3.4246227008012586],
            [3.96906033825975, 13.413012792844643],
            [3.996787360898604, 23.483848981301133],
            [3.8371705661974156, 33.38062210922899],
        ],
        [
            [1.6211812208088947, -0.17113728719475027],
            [1.999915402794045, -0.01839515335987582],
            [1.972778736430331, 0.32885263734436887],
            [1.994081829890068, 0.15374542497999033],
        ],
        domain=(60.0, 40.0),
    )
    assert result.success
    assert result.log["solver_settings"]["eps_rel"] == 0.0
    assert result.log["solver_settings"]["eps_abs"] == 1e-8
    assert result.log["acceptance_tol"] == 1e-7
    assert result.log["max_constraint_violation"] <= 1e-7
    assert result.log["stationarity_residual"] <= 1e-7


def test_solver_settings_are_deterministic_except_recorded_times() -> None:
    first = solve([[5.0, 10.0], [8.0, 10.0]], [[2.0, 0.5], [-2.0, -0.5]])
    second = solve([[5.0, 10.0], [8.0, 10.0]], [[2.0, 0.5], [-2.0, -0.5]])
    assert first.success and second.success
    np.testing.assert_array_equal(first.velocity, second.velocity)
    nondeterministic = {"setup_s", "solve_s", "setup_wall_s", "solve_wall_s", "control_s"}
    assert {k: v for k, v in first.log.items() if k not in nondeterministic} == {
        k: v for k, v in second.log.items() if k not in nondeterministic
    }


@pytest.mark.parametrize(
    "positions,nominal,kwargs,reason",
    [
        ([], [], {}, "non-empty shape"),
        ([[1.0, 2.0, 3.0]], [[0.0, 0.0]], {}, "non-empty shape"),
        ([[1.0, 2.0]], [[0.0, 0.0], [0.0, 0.0]], {}, "same (n, 2) shape"),
        ([[float("nan"), 2.0]], [[0.0, 0.0]], {}, "finite"),
        ([[1.0, 2.0]], [[float("inf"), 0.0]], {}, "finite"),
        ([[1.0 + 1j, 2.0]], [[0.0, 0.0]], {}, "real-valued"),
        (
            [[1.0, 2.0]],
            [[0.0, 0.0]],
            {"domain": np.array([20.0 + 1j, 20.0])},
            "real-valued",
        ),
        ([[-0.01, 2.0]], [[0.0, 0.0]], {}, "outside"),
        ([[20.1, 2.0]], [[0.0, 0.0]], {}, "outside"),
        ([[1.0, 2.0], [1.5, 2.0]], [[0.0, 0.0], [0.0, 0.0]], {}, "separation"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"domain": (0.0, 10.0)}, "domain"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"domain": (10.0,)}, "domain"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"dt": 0.0}, "dt"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"max_speed": -1.0}, "max_speed"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"min_separation": 0.0}, "min_separation"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"dt": True}, "dt"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"dt": "0.5"}, "dt"),
        ([[1.0, 2.0]], [[0.0, 0.0]], {"max_speed": 2.0 + 1j}, "max_speed"),
        (
            [[1.0, 2.0], [1.0, 2.0]],
            [[0.0, 0.0], [0.0, 0.0]],
            {"min_separation": 1e-8},
            "zero pair separation",
        ),
    ],
)
def test_invalid_state_returns_failure_not_motion(
    positions: Any, nominal: Any, kwargs: dict[str, Any], reason: str
) -> None:
    result = solve(positions, nominal, **kwargs)
    assert not result.success
    assert result.log["status"] == "invalid_input"
    assert reason in result.log["failure_reason"]
    assert result.log["iterations"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": 0.0},
        {"alpha": True},
        {"alpha": "1.0"},
        {"alpha": 1.0 + 1j},
        {"eps_abs": float("nan")},
        {"eps_rel": -1.0},
        {"acceptance_tol": 0.0},
        {"polygon_sides": 3},
        {"polygon_sides": 6.0},
        {"polygon_sides": True},
        {"max_iter": 0},
        {"max_iter": 5.0},
        {"max_iter": True},
    ],
)
def test_invalid_settings_raise(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        QPSettings(**kwargs)


def test_small_numerical_initial_boundary_offset_is_explicitly_tolerated() -> None:
    result = solve([[-1e-9, 5.0]], [[1.0, 0.0]])
    assert result.success
    rejected = solve([[-2e-7, 5.0]], [[1.0, 0.0]])
    assert not rejected.success


@pytest.mark.parametrize(
    "positions,kwargs",
    [
        ([[1e200, 1e200], [2e200, 1e200]], {"domain": (3e200, 3e200)}),
        ([[5.0, 5.0], [8.0, 5.0]], {"settings": QPSettings(alpha=1e308)}),
    ],
)
def test_finite_inputs_that_overflow_are_rejected_before_solver(
    monkeypatch: pytest.MonkeyPatch, positions: Any, kwargs: dict[str, Any]
) -> None:
    def forbidden_solver() -> Any:
        pytest.fail("Invalid numerical input must not reach solver setup")

    monkeypatch.setattr(qp_module.osqp, "OSQP", forbidden_solver)
    result = solve(positions, np.zeros((2, 2)), **kwargs)
    assert not result.success
    assert result.log["status"] == "invalid_input"


def test_real_solver_max_iteration_is_failed_without_fallback() -> None:
    result = solve(
        [[5.0, 10.0], [8.0, 10.0]],
        [[2.0, 0.0], [-2.0, 0.0]],
        settings=QPSettings(max_iter=1),
    )
    assert not result.success
    assert result.log["status_val"] == 7
    assert result.log["iterations"] == 1
    assert "maximum iterations" in result.log["failure_reason"]


def install_fake_solver(
    monkeypatch: pytest.MonkeyPatch,
    *,
    velocity: Any = None,
    dual: Any = None,
    status_val: int = 1,
    status: str = "solved",
    setup_error: bool = False,
    solve_error: bool = False,
) -> None:
    class FakeSolver:
        def setup(self, **kwargs: Any) -> None:
            if setup_error:
                raise RuntimeError("injected setup failure")
            self.count = kwargs["A"].shape[0]
            self.variables = kwargs["A"].shape[1]
            assert kwargs["adaptive_rho_interval"] == 25
            assert kwargs["warm_starting"] is False

        def solve(self, *, raise_error: bool) -> Any:
            assert not raise_error
            if solve_error:
                raise RuntimeError("injected solve failure")
            return SimpleNamespace(
                x=np.zeros(self.variables) if velocity is None else velocity,
                y=np.zeros(self.count) if dual is None else dual,
                info=SimpleNamespace(
                    status=status,
                    status_val=status_val,
                    iter=25,
                    prim_res=0.0,
                    dual_res=0.0,
                    obj_val=0.0,
                    setup_time=0.001,
                    solve_time=0.002,
                    rho_updates=0,
                ),
            )

    monkeypatch.setattr(qp_module.osqp, "OSQP", FakeSolver)


@pytest.mark.parametrize(
    "status_val,status",
    [(3, "primal infeasible"), (4, "primal infeasible inaccurate"), (9, "non convex")],
)
def test_infeasible_or_invalid_solver_status_is_not_hidden(
    monkeypatch: pytest.MonkeyPatch, status_val: int, status: str
) -> None:
    # Zero is feasible for a valid state in this precise model; inject solver status
    # to test an error-reporting path, not to invent an infeasible benchmark state.
    install_fake_solver(monkeypatch, status_val=status_val, status=status)
    result = solve([[5.0, 5.0]], [[0.0, 0.0]])
    assert not result.success
    assert result.log["status_val"] == status_val
    assert result.log["failure_reason"] == f"solver_status: {status}"


@pytest.mark.parametrize("stage", ["setup", "solve"])
def test_solver_exception_returns_failure(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    install_fake_solver(monkeypatch, setup_error=stage == "setup", solve_error=stage == "solve")
    result = solve([[5.0, 5.0]], [[0.0, 0.0]])
    assert not result.success
    assert result.log["status"] == "solver_error"
    assert f"injected {stage} failure" in result.log["failure_reason"]


@pytest.mark.parametrize(
    "velocity,dual",
    [
        ([float("nan"), 0.0], None),
        ([1.0], None),
        ([0.0, 0.0], [float("inf")]),
        ([0.5 + 1j, 0.0], None),
        (["invalid", 0.0], None),
    ],
)
def test_invalid_numerical_solution_cannot_move(
    monkeypatch: pytest.MonkeyPatch, velocity: Any, dual: Any
) -> None:
    install_fake_solver(monkeypatch, velocity=velocity, dual=dual)
    result = solve([[5.0, 5.0]], [[0.0, 0.0]])
    assert not result.success
    assert result.log["failure_reason"] == "nonfinite_or_malformed_solution"


def test_overflowing_solution_verification_cannot_move(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_solver(monkeypatch, velocity=[1e308, 0.0])
    result = solve([[5.0, 5.0]], [[1e308, 0.0]])
    assert not result.success
    assert result.log["failure_reason"] == "nonfinite_solution_verification"


def test_solver_claim_of_solved_does_not_bypass_linear_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_solver(monkeypatch, velocity=[10.0, 0.0])
    result = solve([[5.0, 5.0]], [[10.0, 0.0]])
    assert not result.success
    assert result.log["failure_reason"] == "linear_constraint_violation"
    assert result.log["max_constraint_violation"] > 1.0


def test_stationarity_is_independent_of_solver_report(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_solver(monkeypatch, velocity=[0.0, 0.0])
    result = solve([[5.0, 5.0]], [[1.0, 0.0]])
    assert not result.success
    assert result.log["dual_residual"] == 0.0
    assert result.log["stationarity_residual"] == 1.0
    assert result.log["failure_reason"] == "stationarity_residual_exceeds_tolerance"


def test_stationarity_alone_does_not_accept_inactive_bound_multiplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The x domain row is dt*u_x <= 15. y=2 makes x=0 stationary for nominal
    # x=1, but this inactive bound cannot have a nonzero multiplier at optimum.
    dual = np.zeros(18)
    dual[16] = 2.0
    install_fake_solver(monkeypatch, velocity=[0.0, 0.0], dual=dual)
    result = solve([[5.0, 5.0]], [[1.0, 0.0]])
    assert not result.success
    assert result.log["stationarity_residual"] == 0.0
    assert result.log["complementarity_residual"] == 30.0
    assert result.log["normalized_complementarity_residual"] == 10.0
    assert result.log["failure_reason"] == "complementarity_residual_exceeds_tolerance"


def test_stationarity_alone_does_not_accept_wrong_dual_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Speed facets only have upper bounds: their multipliers must be positive.
    dual = np.zeros(18)
    dual[0] = -2.0
    direction = np.array([np.cos(np.pi / 16), np.sin(np.pi / 16)])
    install_fake_solver(monkeypatch, velocity=[0.0, 0.0], dual=dual)
    result = solve([[5.0, 5.0]], [-2.0 * direction])
    assert not result.success
    assert result.log["stationarity_residual"] == 0.0
    assert result.log["dual_feasibility_residual"] == 2.0
    assert result.log["failure_reason"] == "dual_feasibility_residual_exceeds_tolerance"


def test_solved_inaccurate_requires_same_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_solver(monkeypatch, velocity=[0.5, 0.0], status_val=2, status="solved inaccurate")
    accepted = solve([[5.0, 5.0]], [[0.5, 0.0]])
    assert accepted.success
    install_fake_solver(monkeypatch, velocity=[10.0, 0.0], status_val=2, status="solved inaccurate")
    rejected = solve([[5.0, 5.0]], [[10.0, 0.0]])
    assert not rejected.success


@pytest.mark.parametrize(
    "positions,nominal,kwargs,reason",
    [
        ([[5.0, 5.0]], [[3.0, 0.0]], {}, "euclidean_speed_violation"),
        ([[19.9, 5.0]], [[1.0, 0.0]], {}, "rectangular_domain_violation"),
        (
            [[8.0, 10.0], [12.0, 10.0]],
            [[2.0, 0.0], [-2.0, 0.0]],
            {"dt": 2.0},
            "continuous_segment_separation_violation",
        ),
    ],
)
def test_physical_checks_are_independent_of_constraint_assembly(
    monkeypatch: pytest.MonkeyPatch,
    positions: Any,
    nominal: Any,
    kwargs: dict[str, Any],
    reason: str,
) -> None:
    # Deliberately corrupt constraint assembly: a solved linear system must still
    # pass independent physical checks. In the crossing case the endpoints are safe.
    def no_constraints(points: Any, *args: Any) -> Any:
        return np.zeros((1, points.size)), np.array([-1.0]), np.array([1.0]), ["dummy"]

    monkeypatch.setattr(qp_module, "_constraints", no_constraints)
    install_fake_solver(monkeypatch, velocity=np.asarray(nominal).ravel())
    result = solve(positions, nominal, **kwargs)
    assert not result.success
    assert result.log["failure_reason"] == reason


def test_accepted_command_is_not_projected_or_clipped(monkeypatch: pytest.MonkeyPatch) -> None:
    command = np.array([0.5 + 3e-9, -0.2])
    install_fake_solver(monkeypatch, velocity=command)
    result = solve([[5.0, 5.0]], [command])
    assert result.success
    np.testing.assert_array_equal(result.velocity, command.reshape(1, 2))
