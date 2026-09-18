"""The ECC cell MDP: representative values, eq. (16), and the recorded project choices."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from attain_sampling.planning.cell_mdp import (
    CellRepresentatives,
    bellman_policy,
    cell_representatives,
    plan_cell_route,
)
from attain_sampling.sources.ecc2025 import parameters

RHO = parameters()["rho"]


def grid_queries(side: float, count: int, origin: float) -> np.ndarray:
    axis = origin + (np.arange(count) + 0.5) * side / count
    xx, yy = np.meshgrid(axis, axis)
    return np.column_stack((xx.ravel(), yy.ravel()))


def representatives(points: np.ndarray, variances: np.ndarray) -> CellRepresentatives:
    return CellRepresentatives(
        points=np.asarray(points, dtype=float),
        variances=np.asarray(variances, dtype=float),
        counts=np.ones(len(points), dtype=np.int64),
    )


def test_representative_variance_is_a_mean_and_the_point_is_a_centroid():
    queries = np.asarray([[1.0, 1.0], [3.0, 1.0], [1.0, 3.0], [3.0, 3.0], [15.0, 15.0]])
    variance = np.asarray([0.2, 0.4, 0.6, 0.8, 1.0])
    cells = cell_representatives(queries, variance, origin=(0.0, 0.0), cell_size=10.0, shape=(2, 2))
    # Four points share the first 10 m cell; the fifth sits in the diagonal cell.
    assert cells.counts.tolist() == [4, 1]
    assert cells.variances[0] == pytest.approx(0.5)
    assert cells.points[0] == pytest.approx([2.0, 2.0])
    assert cells.variances[1] == pytest.approx(1.0)
    assert cells.points[1] == pytest.approx([15.0, 15.0])


def test_empty_cells_are_dropped_rather_than_invented():
    queries = np.asarray([[1.0, 1.0], [1.0, 2.0]])
    cells = cell_representatives(
        queries, np.asarray([1.0, 1.0]), origin=(0.0, 0.0), cell_size=10.0, shape=(4, 4)
    )
    assert len(cells.points) == 1
    assert cells.counts.tolist() == [2]


def test_the_partition_matches_the_paper_setup_shape():
    """120 m field on a 30 x 30 evaluation grid with 10 m cells (pp. 308, 310)."""
    queries = grid_queries(120.0, 30, -60.0)
    cells = cell_representatives(
        queries, np.ones(len(queries)), origin=(-60.0, -60.0), cell_size=10.0, shape=(12, 12)
    )
    assert len(queries) == 900
    assert len(cells.points) == 144
    assert int(cells.counts.sum()) == 900
    # n_c < m, as the paper requires on p. 308.
    assert len(cells.points) < len(queries)


def test_reward_prefers_a_near_high_variance_cell_over_a_far_one():
    points = np.asarray([[0.0, 0.0], [1.0, 0.0], [50.0, 0.0]])
    # The far cell has the larger variance, but the ratio sigma^2/distance favours the near.
    cells = representatives(points, [0.0, 1.0, 10.0])
    _, policy = bellman_policy(cells, discount=RHO)
    assert policy[0] == 1


def test_value_iteration_matches_exhaustive_discounted_enumeration():
    """eq. (16) is an infinite-horizon fixed point; a deep enumeration must approach it."""
    points = np.asarray([[0.0, 0.0], [2.0, 0.0], [0.0, 3.0], [4.0, 4.0]])
    variances = np.asarray([0.1, 0.9, 0.4, 0.7])
    cells = representatives(points, variances)
    values, _ = bellman_policy(cells, discount=RHO)

    distance = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    reward = np.where(
        distance > 0, variances[None, :] / np.where(distance > 0, distance, 1), -np.inf
    )
    np.fill_diagonal(reward, -np.inf)

    # rho = 0.9 contracts by ~1e-3 per 60 sweeps, so the reference must run far deeper
    # than the module's 1e-10 tolerance to compare against the same fixed point.
    best = np.zeros(len(points))
    for _ in range(600):
        best = np.max(reward + RHO * best[None, :], axis=1)
    assert values == pytest.approx(best, rel=1e-9, abs=1e-9)

    # Brute force over explicit routes for a shallow depth, as an independent check.
    shallow = np.zeros(len(points))
    for _ in range(4):
        shallow = np.max(reward + RHO * shallow[None, :], axis=1)
    enumerated = []
    for start in range(len(points)):
        scores = []
        for route in itertools.product(range(len(points)), repeat=4):
            node, total, discount = start, 0.0, 1.0
            for step in route:
                if step == node:
                    total = -np.inf
                    break
                total += discount * reward[node, step]
                discount *= RHO
                node = step
            scores.append(total)
        enumerated.append(max(scores))
    assert shallow == pytest.approx(np.asarray(enumerated), rel=1e-9)


def test_self_transitions_are_excluded_because_their_reward_is_undefined():
    points = np.asarray([[0.0, 0.0], [5.0, 0.0]])
    cells = representatives(points, [100.0, 0.001])
    _, policy = bellman_policy(cells, discount=RHO)
    # Even though staying in the high-variance cell would score best, b' == b is not an action.
    assert policy.tolist() == [1, 0]


def test_a_lower_discount_shortens_the_planning_view():
    points = np.asarray([[0.0, 0.0], [1.0, 0.0], [1.5, 0.0], [40.0, 0.0]])
    cells = representatives(points, [0.0, 0.05, 0.05, 30.0])
    patient, _ = bellman_policy(cells, discount=0.99)
    myopic, _ = bellman_policy(cells, discount=0.05)
    assert patient[0] > myopic[0]


def test_the_route_starts_from_the_cell_nearest_the_robot():
    points = np.asarray([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    cells = representatives(points, [0.5, 0.5, 0.5])
    plan = plan_cell_route(cells, np.asarray([19.0, 1.0]), discount=RHO)
    assert plan.start_cell == 2


def test_the_route_stops_on_revisit_and_reports_it():
    points = np.asarray([[0.0, 0.0], [5.0, 0.0]])
    cells = representatives(points, [1.0, 1.0])
    plan = plan_cell_route(cells, np.asarray([0.0, 0.0]), discount=RHO, max_waypoints=10)
    # Two cells can only alternate, so the unroll must terminate rather than cycle.
    assert plan.truncated_by_revisit is True
    assert len(plan.cell_indices) <= 2
    assert len(plan.waypoints) == len(plan.cell_indices)


def test_the_route_is_bounded_by_max_waypoints():
    rng = np.random.default_rng(3)
    points = rng.uniform(-50.0, 50.0, size=(40, 2))
    cells = representatives(points, rng.uniform(0.1, 1.0, size=40))
    plan = plan_cell_route(cells, np.zeros(2), discount=RHO, max_waypoints=5)
    assert len(plan.cell_indices) <= 5
    assert len(set(plan.cell_indices)) == len(plan.cell_indices)


def test_plan_record_declares_its_surrogate_status_and_project_choices():
    points = np.asarray([[0.0, 0.0], [8.0, 0.0], [0.0, 8.0]])
    cells = representatives(points, [0.2, 0.9, 0.5])
    record = plan_cell_route(cells, np.zeros(2), discount=RHO).as_dict()
    assert "not a belief-MDP" in record["scope"]
    assert any("self-transitions" in choice for choice in record["project_choices"])
    assert isinstance(record["waypoints"], list)


def test_representatives_record_states_its_definition():
    queries = np.asarray([[1.0, 1.0], [2.0, 2.0]])
    cells = cell_representatives(
        queries, np.asarray([0.3, 0.7]), origin=(0.0, 0.0), cell_size=10.0, shape=(1, 1)
    )
    assert "mean latent variance and centroid" in cells.as_dict()["definition"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"cell_size": 0.0},
        {"shape": (0, 3)},
        {"shape": (3,)},
        {"origin": (0.0,)},
    ],
)
def test_invalid_partitions_are_rejected(overrides):
    options = {
        "origin": (0.0, 0.0),
        "cell_size": 10.0,
        "shape": (2, 2),
    }
    options.update(overrides)
    with pytest.raises(ValueError):
        cell_representatives(np.asarray([[1.0, 1.0]]), np.asarray([0.5]), **options)


def test_variance_must_match_the_evaluation_points():
    with pytest.raises(ValueError):
        cell_representatives(
            np.asarray([[1.0, 1.0], [2.0, 2.0]]),
            np.asarray([0.5]),
            origin=(0.0, 0.0),
            cell_size=10.0,
            shape=(1, 1),
        )


@pytest.mark.parametrize("discount", [0.0, 1.0, 1.5])
def test_a_non_contracting_discount_is_rejected(discount):
    cells = representatives(np.asarray([[0.0, 0.0], [1.0, 0.0]]), [0.5, 0.5])
    with pytest.raises(ValueError):
        bellman_policy(cells, discount=discount)


def test_a_single_cell_cannot_support_the_recursion():
    cells = representatives(np.asarray([[0.0, 0.0]]), [0.5])
    with pytest.raises(ValueError):
        bellman_policy(cells, discount=RHO)


def test_coincident_cells_are_rejected_rather_than_dividing_by_zero():
    cells = representatives(np.asarray([[1.0, 1.0], [1.0, 1.0]]), [0.5, 0.5])
    with pytest.raises(ValueError):
        bellman_policy(cells, discount=RHO)
