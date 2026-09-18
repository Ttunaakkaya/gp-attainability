"""The ECC decay-rate row must satisfy the paper's own eq. (15), not just look like (12)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from attain_sampling.control.rate_constraint import (
    DecayConstraintRow,
    decay_constraint_row,
    local_objective,
    paper_objective,
    rbf_kernel,
    voronoi_owner,
)
from attain_sampling.sources.ecc2025 import parameters

PAPER = parameters()
L = PAPER["L"]
NOISE = PAPER["sigma_eps"] ** 2


def scene(seed: int, basis_count: int = 6, query_count: int = 30):
    rng = np.random.default_rng(seed)
    basis = rng.uniform(-40.0, 40.0, size=(basis_count, 2))
    position = rng.uniform(-40.0, 40.0, size=2)
    queries = rng.uniform(-50.0, 50.0, size=(query_count, 2))
    return basis, position, queries


def row_for(basis, position, queries=None, **overrides):
    options = {
        "basis": basis,
        "position": position,
        "queries": np.empty((0, 2)) if queries is None else queries,
        "length_scale": L,
        "noise_variance": NOISE,
        "gamma": PAPER["gamma"],
        "robot_count": PAPER["n"],
        "sample_period_s": PAPER["t_s"],
        "elapsed_s": 0.0,
        "initial_local": 10.0,
        "alpha_j": PAPER["alpha_J"],
    }
    options.update(overrides)
    return decay_constraint_row(**options)


def test_paper_kernel_has_no_signal_variance_prefactor():
    point = np.zeros((1, 2))
    assert rbf_kernel(point, point, L)[0, 0] == pytest.approx(1.0)
    far = rbf_kernel(np.zeros((1, 2)), np.asarray([[L, 0.0]]), L)[0, 0]
    assert far == pytest.approx(math.exp(-0.5))


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7])
def test_the_row_reproduces_equation_15_by_finite_differences(seed):
    """eq. (15): d I~_il / dt = -xi_i1^T u_i, verified against I~_il itself."""
    basis, position, queries = scene(seed)
    rng = np.random.default_rng(seed + 100)
    velocity = rng.normal(size=2)
    row = row_for(basis, position, queries)
    step = 1e-6

    def value(where):
        return local_objective(
            basis=basis,
            position=where,
            queries=queries,
            length_scale=L,
            noise_variance=NOISE,
        )

    numeric = (value(position + step * velocity) - value(position - step * velocity)) / (2 * step)
    predicted = -float(row.xi1 @ velocity)
    assert numeric == pytest.approx(predicted, abs=1e-7, rel=1e-5)


# Scenes where the two readings of (12) genuinely disagree; for some geometries the
# missing factor happens to cancel, which is why the discrepancy is checked on several.
@pytest.mark.parametrize("seed", [0, 19, 32, 36, 37, 46])
def test_the_printed_grouping_of_equation_12_does_not_satisfy_equation_15(seed):
    """The basis term must also carry [z_*]_{N+1}; without it the gradient is wrong.

    This pins the reading recorded in the module docstring, so a later 'simplification'
    back to the printed grouping cannot pass silently.
    """
    basis, position, queries = scene(seed)
    augmented = np.vstack((basis, position[None, :]))
    gram = rbf_kernel(augmented, augmented, L)
    gram[np.diag_indices_from(gram)] += NOISE
    cross = rbf_kernel(augmented, queries, L)
    z = -np.linalg.solve(gram, cross)
    own = rbf_kernel(position[None, :], queries, L)[0]
    first = 2.0 * np.sum((z[-1, :] * own)[:, None] * (position[None, :] - queries), axis=0) / L**2
    basis_kernel = rbf_kernel(position[None, :], basis, L)[0]
    offsets = position[None, :] - basis
    printed = (
        first
        + 2.0 * np.sum((np.sum(z[:-1, :], axis=1) * basis_kernel)[:, None] * offsets, axis=0) / L**2
    )

    implemented = row_for(basis, position, queries).xi1
    step = 1e-6

    def value(where):
        return local_objective(
            basis=basis, position=where, queries=queries, length_scale=L, noise_variance=NOISE
        )

    for direction in (np.asarray([1.0, 0.0]), np.asarray([0.0, 1.0])):
        numeric = (value(position + step * direction) - value(position - step * direction)) / (
            2 * step
        )
        # Central differences on a ~1e-2 gradient bottom out around 1e-8 absolute.
        assert numeric == pytest.approx(-float(implemented @ direction), rel=1e-4, abs=1e-9)
    discrepancy = float(np.linalg.norm(printed - implemented)) / float(np.linalg.norm(implemented))
    assert discrepancy > 0.5


def test_the_constraint_row_is_the_class_k_inequality():
    basis, position, queries = scene(3)
    row = row_for(basis, position, queries, elapsed_s=40.0, initial_local=12.0)
    slope = PAPER["gamma"] / (PAPER["n"] * PAPER["t_s"])
    assert row.h == pytest.approx(12.0 - slope * 40.0 - row.local_objective)
    assert row.xi2 == pytest.approx(-slope + PAPER["alpha_J"] * row.h)
    # eq. (8) with a linear alpha_J is exactly the recorded row.
    velocity = np.asarray([0.4, 1.1])
    hdot = -slope + float(row.xi1 @ velocity)
    assert hdot + PAPER["alpha_J"] * row.h == pytest.approx(float(row.xi1 @ velocity) + row.xi2)


def test_row_satisfaction_uses_the_greater_equal_convention_of_equation_11():
    basis, position, queries = scene(4)
    row = row_for(basis, position, queries)
    best = row.xi1 / max(float(np.linalg.norm(row.xi1)), 1e-12)
    assert row.satisfied_by(best * 1e6)
    assert not row.satisfied_by(-best * 1e6)
    # A slack variable relaxes the row exactly as eq. (10) allows.
    violating = -best * 1e6
    margin = float(row.xi1 @ violating) + row.xi2
    assert row.satisfied_by(violating, slack=margin)


def test_local_objective_is_a_latent_variance_sum_over_the_share():
    basis, position, queries = scene(5)
    augmented = np.vstack((basis, position[None, :]))
    gram = rbf_kernel(augmented, augmented, L)
    gram[np.diag_indices_from(gram)] += NOISE
    cross = rbf_kernel(augmented, queries, L)
    expected = float(np.sum(1.0 - np.sum(cross * np.linalg.solve(gram, cross), axis=0)))
    assert local_objective(
        basis=basis, position=position, queries=queries, length_scale=L, noise_variance=NOISE
    ) == pytest.approx(expected)
    # Latent, not predictive: no sensor-noise term is added to the query variance.
    assert expected < queries.shape[0]


def test_sampling_at_a_point_lowers_the_objective_there():
    basis, _, _ = scene(6, basis_count=3)
    queries = np.asarray([[0.0, 0.0]])
    far = local_objective(
        basis=basis,
        position=np.asarray([45.0, 45.0]),
        queries=queries,
        length_scale=L,
        noise_variance=NOISE,
    )
    near = local_objective(
        basis=basis,
        position=np.asarray([0.0, 0.0]),
        queries=queries,
        length_scale=L,
        noise_variance=NOISE,
    )
    assert near < far


def test_paper_objective_is_a_sum_not_a_mean():
    values = np.asarray([0.5, 0.25, 0.25])
    assert paper_objective(values) == pytest.approx(1.0)
    assert paper_objective(values) != pytest.approx(float(np.mean(values)))


def test_voronoi_cells_partition_the_evaluation_set_once():
    _, _, queries = scene(7, query_count=200)
    positions = np.asarray([[-20.0, -20.0], [20.0, -20.0], [0.0, 25.0]])
    owner = voronoi_owner(queries, positions)
    assert owner.shape == (200,)
    assert set(np.unique(owner)) <= {0, 1, 2}
    counts = [int(np.sum(owner == index)) for index in range(3)]
    assert sum(counts) == 200
    for index, point in enumerate(queries):
        distances = np.linalg.norm(positions - point, axis=1)
        assert distances[owner[index]] == pytest.approx(distances.min())


def test_an_empty_voronoi_share_yields_a_zero_gradient():
    basis, position, _ = scene(8)
    row = row_for(basis, position, np.empty((0, 2)), initial_local=0.0)
    assert row.evaluation_count == 0
    assert np.allclose(row.xi1, 0.0)
    assert row.local_objective == 0.0
    assert row.satisfied_by(np.zeros(2)) is (row.xi2 >= 0.0)


def test_record_is_json_safe_and_states_its_convention():
    basis, position, queries = scene(9)
    record = row_for(basis, position, queries).as_dict()
    assert record["convention"].startswith("xi1 @ u + xi2 >= w_i")
    assert "not a safety certificate" in record["scope"]
    assert isinstance(record["xi1"], list)


@pytest.mark.parametrize(
    "overrides",
    [
        {"length_scale": 0.0},
        {"noise_variance": -1.0},
        {"gamma": 0.0},
        {"robot_count": 0},
        {"robot_count": True},
        {"sample_period_s": -5.0},
        {"elapsed_s": -1.0},
        {"elapsed_s": math.nan},
        {"alpha_j": 0.0},
        {"initial_local": math.inf},
        {"queries": np.zeros((3, 3))},
    ],
)
def test_invalid_row_inputs_are_rejected(overrides):
    basis, position, queries = scene(10)
    options = {"queries": queries, **overrides}
    with pytest.raises(ValueError):
        row_for(basis, position, **options)


def test_the_row_type_is_immutable():
    basis, position, queries = scene(11)
    row = row_for(basis, position, queries)
    assert isinstance(row, DecayConstraintRow)
    with pytest.raises(AttributeError):
        row.xi2 = 1.0  # type: ignore[misc]


@pytest.mark.parametrize("signal", [1.0, 4.0])
@pytest.mark.parametrize("seed", [0, 3, 21])
def test_equation_15_holds_with_a_signal_variance(seed, signal):
    basis, position, queries = scene(seed)
    velocity = np.random.default_rng(seed + 5).normal(size=2)
    row = row_for(basis, position, queries, signal_variance=signal)
    step = 1e-6

    def value(where):
        return local_objective(
            basis=basis,
            position=where,
            queries=queries,
            length_scale=L,
            noise_variance=NOISE,
            signal_variance=signal,
        )

    numeric = (value(position + step * velocity) - value(position - step * velocity)) / (2 * step)
    assert numeric == pytest.approx(-float(row.xi1 @ velocity), rel=1e-4, abs=1e-8)


@pytest.mark.parametrize("signal", [1.0, 4.0])
@pytest.mark.parametrize(("seed", "basis_count"), [(0, 0), (1, 1), (2, 6), (3, 40)])
def test_epoch_cache_matches_the_reference_row(seed, basis_count, signal):
    from attain_sampling.control.rate_constraint import EpochDecayCache

    rng = np.random.default_rng(seed)
    basis = rng.uniform(-50.0, 50.0, size=(basis_count, 2))
    queries = rng.uniform(-60.0, 60.0, size=(120, 2))
    cache = EpochDecayCache(
        basis=basis,
        queries=queries,
        length_scale=L,
        noise_variance=NOISE,
        signal_variance=signal,
    )
    assert cache.basis_size == basis_count
    for _ in range(4):
        position = rng.uniform(-50.0, 50.0, size=2)
        selection = rng.random(len(queries)) < 0.4
        options = {
            "gamma": PAPER["gamma"],
            "robot_count": PAPER["n"],
            "sample_period_s": PAPER["t_s"],
            "elapsed_s": 120.0,
            "initial_local": 300.0,
            "alpha_j": PAPER["alpha_J"],
        }
        fast = cache.row(position=position, selection=selection, **options)
        slow = decay_constraint_row(
            basis=basis,
            position=position,
            queries=queries[selection],
            length_scale=L,
            noise_variance=NOISE,
            signal_variance=signal,
            **options,
        )
        assert fast.evaluation_count == slow.evaluation_count
        assert fast.local_objective == pytest.approx(slow.local_objective, rel=1e-9, abs=1e-9)
        assert fast.xi2 == pytest.approx(slow.xi2, rel=1e-9, abs=1e-12)
        assert fast.xi1 == pytest.approx(slow.xi1, rel=1e-7, abs=1e-12)


def test_epoch_cache_accepts_index_or_mask_selections_and_empty_shares():
    from attain_sampling.control.rate_constraint import EpochDecayCache

    basis, position, queries = scene(12)
    cache = EpochDecayCache(basis=basis, queries=queries, length_scale=L, noise_variance=NOISE)
    options = {
        "gamma": PAPER["gamma"],
        "robot_count": PAPER["n"],
        "sample_period_s": PAPER["t_s"],
        "elapsed_s": 0.0,
        "initial_local": 1.0,
        "alpha_j": PAPER["alpha_J"],
    }
    mask = np.zeros(len(queries), dtype=bool)
    mask[[1, 4, 9]] = True
    by_mask = cache.row(position=position, selection=mask, **options)
    by_index = cache.row(position=position, selection=np.asarray([1, 4, 9]), **options)
    assert by_mask.xi1 == pytest.approx(by_index.xi1)
    empty = cache.row(position=position, selection=np.zeros(len(queries), dtype=bool), **options)
    assert empty.evaluation_count == 0
    assert np.allclose(empty.xi1, 0.0)
