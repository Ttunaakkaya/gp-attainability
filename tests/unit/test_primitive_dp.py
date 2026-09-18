"""M7 motion-primitive Bellman planner: tree, recursion, reservations and plan record."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from attain_sampling.gp.exact import ExactGP
from attain_sampling.planning import primitive_dp
from attain_sampling.planning.primitive_dp import PRIMITIVES, plan_primitive_dp
from attain_sampling.planning.timed_dp import DPSettings
from attain_sampling.sim import usv

RADIUS = 2.0 / 0.45
BOUNDS = np.asarray([60.0, 40.0])


def _tree(budgets=(10.0, 10.0), start=(30.0, 20.0), heading=0.0):
    return primitive_dp._Tree(
        np.asarray(start), heading, np.asarray(budgets), radius=RADIUS, bounds=BOUNDS
    )


def test_tree_levels_hold_every_primitive_and_keep_the_invariants():
    tree = _tree()
    assert tree.depth == 2
    assert [len(level) for level in tree.positions] == [1, 7, 49]
    stop = len(PRIMITIVES) - 1
    np.testing.assert_allclose(tree.positions[1][stop], [30.0, 20.0])
    assert tree.lengths[1][stop] == 0.0
    np.testing.assert_allclose(tree.lengths[1], [10, 10, 10, 5, 5, 5, 0])
    for level in (1, 2):
        valid = tree.valid[level]
        positions = tree.positions[level][valid]
        assert np.all(positions >= 0) and np.all(positions <= BOUNDS)
        left, right = usv.viable(positions, tree.headings[level][valid], RADIUS, (60.0, 40.0))
        moving = tree.lengths[level][valid] > 0
        assert np.all((left | right)[moving])


def test_nodes_that_would_leave_the_field_are_inadmissible():
    tree = _tree(start=(60.0 - RADIUS - 0.5, 20.0))
    # Full straight ahead crosses the viability margin at the right wall.
    assert not bool(tree.valid[1][1])
    assert bool(tree.valid[1][len(PRIMITIVES) - 1])


def test_a_robot_with_an_inside_circle_can_always_keep_moving():
    # Regression for D057: a sampled containment margin rejected every moving
    # primitive when the only inside circle came within a few centimetres of an edge.
    tree = _tree(budgets=(10.0,) * 4, start=(51.094, 39.429), heading=0.496)
    left, right = usv.viable(np.asarray([51.094, 39.429]), np.asarray(0.496), RADIUS, (60, 40))
    assert not bool(left) and bool(right)
    assert bool(tree.valid[1][2]) and bool(tree.valid[1][5])
    rng = np.random.default_rng(11)
    starts = rng.uniform([0, 0], BOUNDS, (400, 2))
    headings = rng.uniform(-np.pi, np.pi, 400)
    left, right = usv.viable(starts, headings, RADIUS, (60.0, 40.0))
    for start, heading, has_left, has_right in zip(starts, headings, left, right, strict=True):
        if not (has_left or has_right):
            continue
        tree = _tree(budgets=(10.0,) * 3, start=start, heading=heading)
        # The full turn along an inside circle stays on it, so it is admissible at
        # every level of the tree.
        turn = 0 if has_left else 2
        node = 0
        for level in range(1, 4):
            node = node * len(PRIMITIVES) + turn
            assert bool(tree.valid[level][node])


def test_bellman_recursion_matches_enumerating_every_route():
    rng = np.random.default_rng(4)
    tree = _tree()
    rewards = [np.zeros(1)] + [rng.uniform(0, 1, len(level)) for level in tree.positions[1:]]
    costs = [np.zeros(1)] + [rng.uniform(0, 0.2, len(level)) for level in tree.positions[1:]]
    admissible = [valid.copy() for valid in tree.valid]
    admissible[2][rng.random(49) < 0.3] = False
    route, value = primitive_dp._route_values(tree, rewards, costs, admissible, greedy=False)
    best = -np.inf
    best_route = None
    for first, second in itertools.product(range(7), repeat=2):
        child = first * 7 + second
        if not (admissible[1][first] and admissible[2][child]):
            continue
        total = rewards[1][first] - costs[1][first] + rewards[2][child] - costs[2][child]
        if total > best + 1e-15:
            best, best_route = total, [first, child]
    assert route == best_route
    assert value == pytest.approx(best)


def test_greedy_takes_the_best_admissible_child_each_epoch():
    tree = _tree()
    rewards = [np.zeros(1), np.arange(7, dtype=float), np.arange(49, dtype=float)[::-1]]
    costs = [np.zeros(1), np.zeros(7), np.zeros(49)]
    admissible = [valid.copy() for valid in tree.valid]
    admissible[1][6] = False
    route, value = primitive_dp._route_values(tree, rewards, costs, admissible, greedy=True)
    assert value is None
    assert route[0] == 5
    assert route[1] == 35
    admissible[1][:] = False
    assert primitive_dp._route_values(tree, rewards, costs, admissible, greedy=True) is None
    assert primitive_dp._route_values(tree, rewards, costs, admissible, greedy=False) is None


def _belief():
    gp = ExactGP(length_scale=8.0, signal_variance=1.0, noise_variance=0.0225)
    gp.update(np.asarray([[15.0, 10.0], [40.0, 30.0]]), np.asarray([0.3, -0.2]))
    return gp


def _grid():
    x, y = np.meshgrid(np.linspace(0, 60, 12), np.linspace(0, 40, 8))
    return np.column_stack((x.ravel(), y.ravel()))


STARTS = np.column_stack(
    (RADIUS + 1 + (np.arange(3) % 2) * (2 * RADIUS + 2.0), (np.arange(3) + 0.35) * 40 / 3)
)


def _plan(**overrides):
    kwargs = {
        "domain": (60.0, 40.0),
        "max_speed": 2.0,
        "min_separation": 2.0,
        "turn_radius": RADIUS,
        "sample_period_s": 5.0,
        "now_s": 0.0,
        "mission_end_s": 30.0,
        "plan_version": 3,
        "settings": DPSettings(horizon_steps=3, include_greedy_candidates=True),
    }
    kwargs.update(overrides)
    return plan_primitive_dp(_belief(), STARTS, np.zeros(3), _grid(), **kwargs)


def test_plan_record_is_timed_flyable_and_separated():
    plan = _plan()
    assert plan["status"] == "planned"
    assert plan["sample_times_s"] == [5.0, 10.0, 15.0]
    assert len(plan["forecast"]) == 4
    assert plan["plan_id"].startswith("dp-000003-")
    assert plan["plan_id"] == _plan()["plan_id"]
    selected = [candidate for candidate in plan["candidates"] if candidate["selected"]]
    assert len(selected) == 1 and selected[0]["candidate_id"] == plan["selected_candidate_id"]
    assert any(candidate["candidate_id"] == "nominal-hold" for candidate in plan["candidates"])
    generators = {candidate["generator"] for candidate in plan["candidates"]}
    assert {"primitive_tree_bellman", "primitive_tree_greedy", "nominal_hold"} <= generators
    for candidate in plan["candidates"]:
        if candidate["status"] != "accepted":
            continue
        checks = candidate["nominal_checks"]
        assert checks["accepted"]
        assert checks["min_pair_distance_m"] >= 2.0 - 1e-7
        assert np.max(candidate["primitive_lengths_by_epoch"]) <= 10.0 + 1e-9
        targets = np.asarray(candidate["targets_by_epoch"])
        assert targets.shape == (3, 3, 2)
        previous = STARTS
        for epoch, positions in enumerate(targets):
            flown = usv.point_path(previous, np.zeros(3), positions, RADIUS).length
            # Shortest forward paths never exceed the primitive that got there.
            assert np.all(np.linalg.norm(positions - previous, axis=1) <= 10.0 + 1e-9)
            previous = positions
            assert epoch < 3 and flown.shape == (3,)
    assert plan["motion_model"]["model"] == "usv_curvature"
    assert plan["forecast"][-1]["mean_variance"] <= plan["forecast"][0]["mean_variance"]


def test_no_remaining_epoch_returns_an_empty_plan():
    plan = _plan(now_s=30.0)
    assert plan["status"] == "no_remaining_samples"
    assert plan["targets_by_epoch"] == [] and plan["candidates"] == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mission_end_s": -1.0}, "finite and non-negative"),
        ({"now_s": 10.0, "mission_end_s": 5.0}, "must not precede"),
        ({"settings": "fast"}, "DPSettings"),
        ({"settings": DPSettings(horizon_steps=7)}, "at most six"),
        ({"turn_radius": 0.0}, "positive"),
    ],
)
def test_invalid_planning_inputs_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        _plan(**overrides)


def test_heading_and_fleet_shapes_are_checked():
    with pytest.raises(ValueError, match="one finite angle"):
        plan_primitive_dp(
            _belief(),
            STARTS,
            np.zeros(2),
            _grid(),
            domain=(60.0, 40.0),
            max_speed=2.0,
            min_separation=2.0,
            turn_radius=RADIUS,
            sample_period_s=5.0,
            now_s=0.0,
            mission_end_s=30.0,
            plan_version=0,
            settings=DPSettings(),
        )
    with pytest.raises(ValueError, match="one to four robots"):
        plan_primitive_dp(
            _belief(),
            np.tile(STARTS, (2, 1)),
            np.zeros(6),
            _grid(),
            domain=(60.0, 40.0),
            max_speed=2.0,
            min_separation=2.0,
            turn_radius=RADIUS,
            sample_period_s=5.0,
            now_s=0.0,
            mission_end_s=30.0,
            plan_version=0,
            settings=DPSettings(),
        )
