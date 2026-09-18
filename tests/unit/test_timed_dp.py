"""M2 mathematical, timing, information-access and nominal-geometry contracts."""

from __future__ import annotations

import copy
import itertools
import json
from typing import Any

import numpy as np
import pytest

from attain_sampling.gp.exact import ExactGP
from attain_sampling.planning.timed_dp import (
    DPSettings,
    _bellman,
    _condition_nodes,
    _nominal_checks,
    _robot_orders,
    _sample_times,
    plan_timed_dp,
)


def make_plan(**overrides: Any) -> tuple[dict[str, Any], ExactGP, np.ndarray]:
    query = np.stack(np.meshgrid(np.linspace(0, 12, 7), np.linspace(0, 12, 7)), axis=-1)
    query = query.reshape(-1, 2)
    positions = np.asarray([[1.0, 1.0], [1.0, 9.0]])
    gp = ExactGP(length_scale=2.0, noise_variance=0.04)
    gp.update(positions, np.asarray([2.0, -1.0]))
    options: dict[str, Any] = {
        "gp": gp,
        "positions": positions,
        "query": query,
        "domain": (12.0, 12.0),
        "max_speed": 3.0,
        "min_separation": 1.0,
        "sample_period_s": 2.0,
        "now_s": 0.0,
        "mission_end_s": 20.0,
        "plan_version": 0,
        "settings": DPSettings(horizon_steps=3, grid_shape=(5, 5)),
    }
    options.update(overrides)
    return plan_timed_dp(**options), options["gp"], options["query"]


def strip_timings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_timings(item) for key, item in value.items() if not key.endswith("_wall_s")
        }
    if isinstance(value, list):
        return [strip_timings(item) for item in value]
    return value


def brute_force(rewards, costs, feasible, start):
    best_value, best_path = -np.inf, None
    for path in itertools.product(range(len(rewards)), repeat=len(feasible)):
        node, value = start, 0.0
        for epoch, target in enumerate(path):
            if not feasible[epoch, node, target]:
                break
            value += rewards[target] - costs[node, target]
            node = target
        else:
            if value > best_value:
                best_value, best_path = value, list(path)
    return best_path, best_value


def test_bellman_matches_exhaustive_finite_horizon_and_is_not_greedy():
    rewards = np.asarray([1.0, 0.0, 10.0])
    costs = np.zeros((3, 3))
    edges = np.asarray([[True, True, False], [False, True, True], [False, False, True]])
    feasible = np.repeat(edges[None], 3, axis=0)
    path, value = _bellman(rewards, costs, feasible, 0)
    assert (path, value) == brute_force(rewards, costs, feasible, 0)
    assert path == [1, 2, 2]
    assert value == 20
    # A one-step greedy decision stays at node 0, unlike the backward recursion.
    assert int(np.argmax(np.where(edges[0], rewards, -np.inf))) == 0


@pytest.mark.parametrize("seed", range(8))
def test_bellman_matches_enumeration_with_time_dependent_edges_and_costs(seed):
    rng = np.random.default_rng(seed)
    rewards = rng.uniform(size=4)
    costs = rng.uniform(0, 0.3, size=(4, 4))
    feasible = rng.random((3, 4, 4)) > 0.4
    feasible[:, np.arange(4), np.arange(4)] = True
    path, value = _bellman(rewards, costs, feasible, 0)
    expected_path, expected_value = brute_force(rewards, costs, feasible, 0)
    assert value == pytest.approx(expected_value)
    assert path == expected_path


def test_bellman_search_failure_is_explicit():
    assert _bellman(np.ones(2), np.zeros((2, 2)), np.zeros((2, 2, 2), dtype=bool), 0) == (
        None,
        None,
    )


@pytest.mark.parametrize("robot_count", [1, 2, 3, 4])
@pytest.mark.parametrize("version", [0, 1, 7])
def test_multiple_orders_are_bounded_deterministic_and_cover_reverse(robot_count, version):
    orders = _robot_orders(robot_count, version)
    assert 1 <= len(orders) <= 4
    assert len({tuple(order) for order in orders}) == len(orders)
    assert all(sorted(order) == list(range(robot_count)) for order in orders)
    assert orders[0][::-1] in orders
    assert orders[0][0] == version % robot_count


@pytest.mark.parametrize(
    ("now", "end", "period", "horizon", "expected"),
    [
        (0, 90, 5, 4, [5, 10, 15, 20]),
        (80, 90, 5, 4, [85, 90]),
        (85, 89.9, 5, 4, []),
        (86, 92, 5, 4, [90]),
        (4.9, 11, 5, 4, [5, 10]),
        (90, 90, 5, 4, []),
        (0.1, 0.3, 0.1, 4, [0.2, 0.3]),
        (3 * 0.7, 21, 2.1, 4, [4.2, 6.3, 8.4, 10.5]),
    ],
)
def test_only_real_global_sample_epochs_fit_remaining_budget(now, end, period, horizon, expected):
    assert _sample_times(now, end, period, horizon) == pytest.approx(expected)


def test_every_forecast_is_the_same_chosen_plan_prefix_and_selection_is_joint():
    plan, gp, query = make_plan()
    targets = np.asarray(plan["targets_by_epoch"])
    assert plan["sample_times_s"] == [2, 4, 6]
    assert plan["horizon_end_s"] < plan["mission_end_s"]
    assert plan["belief_observation_count"] == 2
    for epoch, row in enumerate(plan["forecast"]):
        variance = gp.fantasy_variance(query, targets[:epoch].reshape(-1, 2))
        assert row["time_s"] == [0, 2, 4, 6][epoch]
        assert row["mean_variance"] == pytest.approx(float(np.mean(variance)), abs=1e-12)
        assert row["max_variance"] == pytest.approx(float(np.max(variance)), abs=1e-12)
    accepted = [row for row in plan["candidates"] if row["status"] == "accepted"]
    for row in accepted:
        exact = gp.fantasy_variance(query, np.asarray(row["targets_by_epoch"]).reshape(-1, 2))
        assert row["terminal_mean_variance"] == pytest.approx(float(np.mean(exact)), abs=1e-12)
    selected = [row for row in accepted if row["selected"]]
    assert len(selected) == 1
    assert selected[0]["candidate_id"] == plan["selected_candidate_id"]
    assert (
        selected[0]["terminal_mean_variance"]
        <= min(row["terminal_mean_variance"] for row in accepted)
        + plan["selection_variance_tolerance"]
    )
    assert plan["planning_wall_s"] > 0
    assert json.loads(json.dumps(plan, allow_nan=False))["plan_id"] == plan["plan_id"]


def test_joint_information_is_not_sum_of_unconditioned_single_sample_gains():
    gp = ExactGP(length_scale=4.0, noise_variance=0.04)
    query = np.asarray([[0.0, 0.0], [1.0, 0.0]])
    positions = np.asarray([[0.0, 0.0]])
    plan, _, _ = make_plan(
        gp=gp,
        query=query,
        positions=positions,
        max_speed=0.001,
        settings=DPSettings(horizon_steps=3, grid_shape=(2, 2)),
    )
    targets = np.asarray(plan["targets_by_epoch"]).reshape(-1, 2)
    assert len(targets) == 3
    current = gp.predict(query, variance="latent").variance.mean()
    independent_sum = sum(
        current - gp.fantasy_variance(query, sample[None]).mean() for sample in targets
    )
    joint_gain = current - plan["forecast"][-1]["mean_variance"]
    assert independent_sum > 2 * joint_gain


def test_final_joint_variance_ties_prefer_shorter_travel(monkeypatch):
    gp = ExactGP(length_scale=2.0)
    monkeypatch.setattr(
        gp,
        "fantasy_variance",
        lambda query, samples: gp.predict(query, variance="latent").variance,
    )
    plan, _, _ = make_plan(gp=gp)
    assert any(row.get("travel_m", 0) > 0 for row in plan["candidates"])
    chosen = next(row for row in plan["candidates"] if row["selected"])
    assert chosen["travel_m"] == 0
    assert chosen["candidate_id"] == "nominal-hold"


def test_rejected_order_search_is_logged_without_global_impossibility(monkeypatch):
    import attain_sampling.planning.timed_dp as module

    monkeypatch.setattr(module, "_bellman", lambda *args: (None, None))
    plan, _, _ = make_plan()
    rejected = [row for row in plan["candidates"] if row["status"] == "rejected"]
    assert len(rejected) == 2
    assert all(
        row["rejection_reason"] == "no_route_in_this_ordered_coarse_reservation_search"
        for row in rejected
    )
    assert plan["status"] == "planned"
    assert plan["selected_candidate_id"] == "nominal-hold"
    assert "no_task_impossibility_or_recovery_certificate" in plan["claim_limits"]


def test_sequential_node_conditioning_matches_exact_joint_posterior():
    gp = ExactGP(length_scale=3.0, noise_variance=0.08)
    gp.update(np.asarray([[1.0, 1.0]]), np.asarray([2.0]))
    nodes = np.asarray([[0.0, 0.0], [2.0, 1.0], [5.0, 4.0], [8.0, 8.0]])
    query = np.asarray([[1.0, 2.0], [7.0, 7.0]])
    covariance = gp.posterior_covariance(nodes)
    cross = gp.posterior_covariance(query, nodes)
    indices = [1, 1, 3]
    for index in indices:
        _condition_nodes(
            covariance, cross, index, gp.noise_variance + gp.jitter, gp.signal_variance
        )
    samples = nodes[indices]
    sample_cov = gp.posterior_covariance(samples)
    sample_cov.flat[:: len(samples) + 1] += gp.noise_variance + gp.jitter
    exact_cov = gp.posterior_covariance(nodes) - gp.posterior_covariance(
        nodes, samples
    ) @ np.linalg.solve(sample_cov, gp.posterior_covariance(samples, nodes))
    exact_cross = gp.posterior_covariance(query, nodes) - gp.posterior_covariance(
        query, samples
    ) @ np.linalg.solve(sample_cov, gp.posterior_covariance(samples, nodes))
    np.testing.assert_allclose(covariance, exact_cov, atol=1e-12)
    np.testing.assert_allclose(cross, exact_cross, atol=1e-12)


def test_earlier_robot_covariance_conditioning_avoids_duplicate_corner_assignment():
    gp = ExactGP(length_scale=1.0, noise_variance=0.01)
    plan, _, _ = make_plan(
        gp=gp,
        positions=np.asarray([[6.0, 6.0], [6.0, 6.0]]),
        query=np.asarray([[0.0, 0.0], [12.0, 0.0], [0.0, 12.0], [12.0, 12.0]]),
        min_separation=0.0,
        max_speed=20.0,
        settings=DPSettings(horizon_steps=1, grid_shape=(3, 3), travel_weight=0.0),
    )
    rows = [row for row in plan["candidates"] if row["generator"] == "frozen_reward_bellman"]
    assert len(rows) == 2
    for row in rows:
        positions = np.asarray(row["targets_by_epoch"])[0]
        assert not np.array_equal(positions[0], positions[1])


def test_deterministic_plan_uses_covariance_not_labels_and_does_not_mutate_inputs():
    starts = np.asarray([[1.0, 1.0], [1.0, 9.0]])
    before = starts.copy()
    gp_a, gp_b = ExactGP(), ExactGP()
    gp_a.update(starts, np.asarray([1.0, 2.0]))
    gp_b.update(starts, np.asarray([-9.0, 20.0]))
    mean_before = gp_a.predict(starts, variance="latent").mean.copy()
    first, _, _ = make_plan(gp=gp_a, positions=starts)
    second, _, _ = make_plan(gp=gp_b, positions=starts)
    repeated, _, _ = make_plan(gp=gp_a, positions=starts)
    assert strip_timings(first) == strip_timings(second) == strip_timings(repeated)
    np.testing.assert_array_equal(starts, before)
    np.testing.assert_array_equal(gp_a.predict(starts, variance="latent").mean, mean_before)
    assert gp_a.observation_count == gp_b.observation_count == 2


@pytest.mark.parametrize("robots", [2, 3, 4])
def test_all_accepted_candidates_have_reachable_collision_checked_nominal_segments(robots):
    starts = np.asarray([[1.0, 1.0], [1.0, 5.0], [1.0, 9.0], [5.0, 9.0]])[:robots]
    plan, _, _ = make_plan(positions=starts)
    times = [0.0, *plan["sample_times_s"]]
    for row in plan["candidates"]:
        if row["status"] != "accepted":
            continue
        trajectory = np.concatenate((starts[None], np.asarray(row["targets_by_epoch"])))
        assert np.all(trajectory >= 0) and np.all(trajectory <= 12)
        for epoch, duration in enumerate(np.diff(times)):
            movement = trajectory[epoch + 1] - trajectory[epoch]
            assert np.max(np.linalg.norm(movement, axis=1)) <= 3 * duration + 1e-10
            for fraction in np.linspace(0, 1, 101):
                positions = trajectory[epoch] + fraction * movement
                for first in range(robots):
                    for second in range(first + 1, robots):
                        assert np.linalg.norm(positions[first] - positions[second]) >= 1 - 1e-7
        assert row["nominal_checks"]["accepted"]
    assert "not_a_controller_rollout_or_robust_safety_certificate" in plan["claim_limits"]


def test_nominal_checks_detect_crossing_even_when_endpoints_separated():
    checks = _nominal_checks(
        np.asarray([[0.0, 0.0], [10.0, 0.0]]),
        np.asarray([[[10.0, 0.0], [0.0, 0.0]]]),
        np.asarray([1.0]),
        np.asarray([10.0, 10.0]),
        10.0,
        1.0,
    )
    assert not checks["accepted"]
    assert checks["min_pair_distance_m"] == 0


def test_actual_start_connector_can_hold_when_coarse_grid_is_unreachable():
    starts = np.asarray([[10.0, 10.0]])
    plan, _, _ = make_plan(
        positions=starts,
        domain=(1000.0, 1000.0),
        max_speed=0.001,
        settings=DPSettings(horizon_steps=2, grid_shape=(2, 2)),
    )
    np.testing.assert_array_equal(plan["targets_by_epoch"], np.repeat(starts[None], 2, axis=0))


def test_first_off_grid_epoch_uses_only_actual_remaining_travel_time():
    starts = np.asarray([[1.0, 1.0], [1.0, 9.0]])
    plan, _, _ = make_plan(positions=starts, now_s=1.99)
    movement = np.linalg.norm(np.asarray(plan["targets_by_epoch"])[0] - starts, axis=1)
    assert plan["sample_times_s"][0] == 2
    assert np.max(movement) <= 3 * 0.01 + 1e-10


def test_no_remaining_sample_budget_returns_empty_plan_not_fabricated_terminal_sample():
    plan, gp, query = make_plan(now_s=18.0, mission_end_s=19.9)
    assert plan["status"] == "no_remaining_samples"
    assert plan["targets_by_epoch"] == []
    assert plan["sample_times_s"] == []
    assert plan["candidates"] == []
    assert plan["selected_candidate_id"] is None
    assert len(plan["forecast"]) == 1
    assert plan["forecast"][0]["mean_variance"] == pytest.approx(
        gp.predict(query, variance="latent").variance.mean()
    )


def test_m1_numeric_geometry_excursions_are_accepted_without_projecting_starts():
    starts = np.asarray([[-5e-8, 1.0], [1.0 - 1e-7, 1.0]])
    plan, _, _ = make_plan(positions=starts, now_s=20.0, mission_end_s=20.0)
    np.testing.assert_array_equal(plan["starts"], starts)
    assert plan["nominal_checks"]["max_bounds_violation_m"] == 5e-8
    assert plan["nominal_checks"]["accepted"]


@pytest.mark.parametrize(
    "options",
    [
        {"horizon_steps": 0},
        {"horizon_steps": 17},
        {"horizon_steps": True},
        {"horizon_steps": 1.5},
        {"grid_shape": (1, 2)},
        {"grid_shape": (30, 30)},
        {"grid_shape": (2,)},
        {"grid_shape": (2.5, 3)},
        {"travel_weight": -0.1},
        {"travel_weight": np.nan},
        {"travel_weight": True},
    ],
)
def test_invalid_settings_rejected(options):
    with pytest.raises(ValueError):
        DPSettings(**options)


@pytest.mark.parametrize(
    "options",
    [
        {"max_speed": 0.0},
        {"max_speed": np.inf},
        {"min_separation": -1.0},
        {"sample_period_s": 0.0},
        {"sample_period_s": True},
        {"now_s": -1.0},
        {"now_s": 30.0, "mission_end_s": 20.0},
        {"mission_end_s": np.nan},
        {"plan_version": -1},
        {"plan_version": 0.5},
        {"plan_version": True},
        {"domain": (0.0, 12.0)},
        {"domain": (True, 12.0)},
        {"domain": (12.0,)},
        {"domain": (12.0 + 1j, 12.0)},
        {"query": np.empty((0, 2))},
        {"query": np.asarray([[np.inf, 1.0]])},
        {"query": np.asarray([[1j, 2j]])},
        {"positions": np.empty((0, 2))},
        {"positions": np.zeros((5, 2))},
        {"positions": np.asarray([[-1e-5, 1.0]])},
        {"positions": np.asarray([[0.0, 1.0], [0.5, 1.0]])},
        {"positions": np.asarray([[np.nan, 1.0]])},
        {"settings": {}},
    ],
)
def test_invalid_problem_inputs_rejected(options):
    with pytest.raises(ValueError):
        make_plan(**options)


def test_settings_snapshot_and_identity_do_not_alias_mutable_output():
    plan, _, _ = make_plan()
    second, _, _ = make_plan()
    pristine = copy.deepcopy(second)
    plan["targets_by_epoch"][0][0][0] = -100
    assert second == pristine
    assert second["settings"] == {
        "horizon_steps": 3,
        "grid_shape": (5, 5),
        "travel_weight": 0.01,
        "include_greedy_candidates": False,
    }
