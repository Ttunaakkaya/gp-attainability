"""Source-equation, approximation, bounded-state and forecast tests for SOGP."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_array_equal

from attain_sampling.gp.exact import ExactGP
from attain_sampling.gp.protocol import GPBelief
from attain_sampling.gp.sogp import SparseOnlineGP


def _snapshot(gp: SparseOnlineGP) -> dict[str, Any]:
    state = gp._state
    return {
        "basis": state.basis.copy(),
        "indices": state.indices.copy(),
        "alpha": state.alpha.copy(),
        "c": state.c.copy(),
        "q": state.q.copy(),
        "counts": (gp.observation_count, gp.admitted_count, gp.projected_count, gp.pruned_count),
        "events": gp.last_update_events,
    }


def _assert_unchanged(gp: SparseOnlineGP, before: dict[str, Any]) -> None:
    after = _snapshot(gp)
    for key in ("basis", "indices", "alpha", "c", "q"):
        assert_array_equal(after[key], before[key])
    assert after["counts"] == before["counts"]
    assert after["events"] == before["events"]


def test_prior_protocol_and_explicit_variance() -> None:
    gp = SparseOnlineGP(signal_variance=2.0, noise_variance=0.2)
    points = np.array([[0.0, 0.0], [1.0, 2.0]])
    latent = gp.predict(points, variance="latent")
    predictive = gp.predict(points, variance="predictive")
    assert isinstance(gp, GPBelief)
    assert gp.backend_name == "sogp"
    assert "no_future_pruning" in gp.forecast_scope
    assert_allclose(latent.mean, 0.0)
    assert_allclose(latent.variance, 2.0)
    assert_allclose(predictive.variance - latent.variance, 0.2)
    assert latent.variance_kind == "latent"
    assert predictive.variance_kind == "predictive"
    assert gp.observation_count == gp.dictionary_size == gp.state_nbytes == 0
    assert gp.last_update_events == []


def test_single_point_matches_analytic_gaussian_update() -> None:
    gp = SparseOnlineGP(length_scale=2.0, signal_variance=3.0, noise_variance=0.5)
    gp.update(np.zeros((1, 2)), np.array([2.0]))
    query = np.array([[0.0, 0.0], [2.0, 0.0]])
    cross = 3.0 * np.exp(-np.array([0.0, 4.0]) / 8.0)
    prediction = gp.predict(query, variance="latent")
    assert_allclose(prediction.mean, cross * 2.0 / (3.5 + gp.jitter))
    assert_allclose(prediction.variance, 3.0 - cross**2 / (3.5 + gp.jitter))
    assert_allclose(gp._state.q, [[1.0 / 3.0]])
    assert gp.admitted_count == gp.observation_count == gp.dictionary_size == 1
    assert gp.projected_count == gp.pruned_count == 0
    assert gp.last_update_events[0]["observation_index"] == 0
    assert gp.last_update_events[0]["gamma"] == 3.0


@pytest.mark.parametrize("noise", [0.0, 0.01, 0.2])
def test_no_pruning_or_projection_matches_exact(noise: float) -> None:
    rng = np.random.default_rng(7)
    observed = rng.uniform(-8.0, 8.0, (22, 2))
    labels = rng.normal(size=22)
    query = rng.uniform(-8.0, 8.0, (16, 2))
    kwargs = {"length_scale": 1.7, "signal_variance": 2.5, "noise_variance": noise}
    gp, exact = SparseOnlineGP(**kwargs, max_basis=32), ExactGP(**kwargs)
    for index in range(len(observed)):
        gp.update(observed[index : index + 1], labels[index : index + 1])
        exact.update(observed[index : index + 1], labels[index : index + 1])
        actual, expected = (
            gp.predict(query, variance="latent"),
            exact.predict(query, variance="latent"),
        )
        assert_allclose(actual.mean, expected.mean, atol=3e-11)
        assert_allclose(actual.variance, expected.variance, atol=3e-11)
    assert gp.pruned_count == gp.projected_count == 0
    assert_allclose(gp.posterior_covariance(query), exact.posterior_covariance(query), atol=3e-11)
    assert_allclose(gp._state.q, np.linalg.inv(gp._kernel(observed, observed)), atol=2e-10)


@pytest.mark.parametrize("noise", [0.0, 0.1])
def test_repeated_site_is_projected_not_discarded(noise: float) -> None:
    gp = SparseOnlineGP(noise_variance=noise)
    exact = ExactGP(noise_variance=noise)
    points = np.zeros((30, 2))
    labels = np.ones(30)
    gp.update(points, labels)
    exact.update(points, labels)
    actual = gp.predict(points[:1], variance="latent")
    expected = exact.predict(points[:1], variance="latent")
    assert_allclose(actual.mean, expected.mean, atol=1e-8)
    assert_allclose(actual.variance, expected.variance, atol=1e-12)
    assert gp.dictionary_size == gp.admitted_count == 1
    assert gp.observation_count == 30 and gp.projected_count == 29
    assert gp.last_update_events[-1]["update_kind"] == "projected"
    assert gp.last_update_events[-1]["gamma"] == 0


def test_projection_step_agrees_with_source_equation_11() -> None:
    gp = SparseOnlineGP(length_scale=2.0, novelty_tolerance=0.5)
    gp.update(np.array([[0.0, 0.0], [3.0, 1.0]]), np.array([1.0, -0.4]))
    point, label = np.array([[0.1, 0.0]]), 0.7
    before = _snapshot(gp)
    kernel = gp._kernel(before["basis"], point)[:, 0]
    direction = before["c"] @ kernel + before["q"] @ kernel
    denominator = gp.signal_variance + kernel @ before["c"] @ kernel + gp.noise_variance + gp.jitter
    expected_alpha = (
        before["alpha"] + ((label - kernel @ before["alpha"]) / denominator) * direction
    )
    expected_c = before["c"] - np.outer(direction, direction) / denominator
    gp.update(point, np.array([label]))
    assert gp.last_update_events[0]["update_kind"] == "projected"
    assert_array_equal(gp._state.q, before["q"])
    assert_allclose(gp._state.alpha, expected_alpha, atol=1e-15)
    assert_allclose(gp._state.c, expected_c, atol=1e-15)


@pytest.mark.parametrize("amplitude", [0.2, 1.0, 9.0])
def test_admission_tolerance_is_relative_to_signal_variance(amplitude: float) -> None:
    gp = SparseOnlineGP(signal_variance=amplitude, novelty_tolerance=0.01)
    points = np.array([[0.0, 0.0], [0.001, 0.0], [20.0, 0.0]])
    gp.update(points, np.array([1.0, 0.5, -0.2]))
    assert [event["update_kind"] for event in gp.last_update_events] == [
        "admitted",
        "projected",
        "admitted",
    ]


def test_pruning_agrees_with_equations_25_through_27() -> None:
    points = np.array([[0.0, 0.0], [1.5, 0.0], [0.0, 2.0]])
    labels = np.array([0.1, 3.0, -0.8])
    full, bounded = (
        SparseOnlineGP(length_scale=1.0, max_basis=3),
        SparseOnlineGP(length_scale=1.0, max_basis=2),
    )
    full.update(points, labels)
    bounded.update(points, labels)
    alpha, c, q = full._state.alpha, full._state.c, full._state.q
    scores = np.abs(alpha) / np.diag(q)
    removed = int(np.argmin(scores))
    keep = np.arange(3) != removed
    qstar, cstar = q[removed, removed], c[removed, removed]
    qcolumn, ccolumn = q[keep, removed], c[keep, removed]
    expected_alpha = alpha[keep] - alpha[removed] * qcolumn / qstar
    expected_c = (
        c[np.ix_(keep, keep)]
        + cstar * np.outer(qcolumn, qcolumn) / qstar**2
        - (np.outer(qcolumn, ccolumn) + np.outer(ccolumn, qcolumn)) / qstar
    )
    expected_q = q[np.ix_(keep, keep)] - np.outer(qcolumn, qcolumn) / qstar
    assert_allclose(bounded._state.alpha, expected_alpha)
    assert_allclose(bounded._state.c, expected_c)
    assert_allclose(bounded._state.q, expected_q)
    assert_array_equal(bounded.dictionary_observation_indices, np.flatnonzero(keep))
    event = bounded.last_update_events[-1]
    assert event["removed_observation_index"] == removed
    assert event["removal_score"] == pytest.approx(scores[removed])
    assert event["removed_point_variance_before"] == pytest.approx(
        full.predict(points[removed : removed + 1], variance="latent").variance[0]
    )
    assert event["removed_point_variance_after"] == pytest.approx(
        bounded.predict(points[removed : removed + 1], variance="latent").variance[0]
    )
    assert event["pruning_variance_jump"] == pytest.approx(
        event["removed_point_variance_after"] - event["removed_point_variance_before"]
    )


def test_pruning_ties_use_first_basis_index() -> None:
    gp = SparseOnlineGP(length_scale=1.0, max_basis=2)
    gp.update(np.array([[0.0, 0.0], [3.0, 0.0], [6.0, 0.0]]), np.zeros(3))
    assert gp.last_update_events[-1]["removed_observation_index"] == 0
    assert_array_equal(gp.dictionary_observation_indices, [1, 2])


def test_pruning_is_label_dependent_and_can_raise_variance() -> None:
    points = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 4.0]])
    first, second = (
        SparseOnlineGP(length_scale=1.0, max_basis=2),
        SparseOnlineGP(length_scale=1.0, max_basis=2),
    )
    first.update(points, np.array([0.0, 3.0, -4.0]))
    second.update(points, np.array([3.0, 0.0, -4.0]))
    assert not np.array_equal(
        first.dictionary_observation_indices, second.dictionary_observation_indices
    )
    assert not np.allclose(first.posterior_covariance(points), second.posterior_covariance(points))
    assert first.last_update_events[-1]["pruning_variance_jump"] > 0.9


def test_batch_and_sequential_order_agree_including_pruning() -> None:
    rng = np.random.default_rng(51)
    points, labels = rng.uniform(0.0, 20.0, (60, 2)), rng.normal(size=60)
    batch, single = SparseOnlineGP(max_basis=8), SparseOnlineGP(max_basis=8)
    batch.update(points, labels)
    events = []
    for point, label in zip(points, labels, strict=True):
        single.update(point[None, :], np.array([label]))
        events.extend(single.last_update_events)
    before = _snapshot(batch)
    before["events"] = single.last_update_events
    _assert_unchanged(single, before)
    assert events == batch.last_update_events
    assert batch.pruned_count > 0


def test_swapping_received_observation_order_can_change_pruning() -> None:
    rng = np.random.default_rng(21)
    points, labels = rng.uniform(0.0, 20.0, (24, 2)), rng.normal(size=24)
    first, second = SparseOnlineGP(max_basis=4), SparseOnlineGP(max_basis=4)
    first.update(points, labels)
    second.update(points[::-1], labels[::-1])
    assert not np.allclose(
        first.predict(points, variance="latent").variance,
        second.predict(points, variance="latent").variance,
    )


@pytest.mark.parametrize("budget", [1, 32, 64, 128])
def test_dictionary_fills_and_prunes_with_bounded_persistent_arrays(budget: int) -> None:
    rng = np.random.default_rng(77)
    points, labels = rng.uniform([0, 0], [60, 40], (300, 2)), rng.normal(size=300)
    gp = SparseOnlineGP(length_scale=2.5, max_basis=budget)
    for chunk in range(0, 300, 4):
        gp.update(points[chunk : chunk + 4], labels[chunk : chunk + 4])
        assert gp.dictionary_size <= budget
        assert len(gp.last_update_events) == 4
        assert gp.state_nbytes <= 16 * budget**2 + 32 * budget
    assert gp.dictionary_size == budget
    assert gp.pruned_count > 0
    assert gp.admitted_count - gp.pruned_count == gp.dictionary_size
    assert gp.admitted_count + gp.projected_count == gp.observation_count == 300
    assert gp.state_nbytes == 16 * budget**2 + 32 * budget
    assert not hasattr(gp, "_x") and not hasattr(gp, "_y")
    query = rng.uniform([0, 0], [60, 40], (50, 2))
    covariance = gp.posterior_covariance(query)
    assert np.linalg.eigvalsh(covariance).min() > -1e-10


def test_prolonged_dense_stream_remains_finite_psd_and_bounded() -> None:
    rng = np.random.default_rng(51)
    points = rng.uniform([0, 0], [60, 40], (2500, 2))
    labels = np.sin(points[:, 0] / 8) + rng.normal(0.0, 0.15, len(points))
    gp = SparseOnlineGP(max_basis=128)
    query = rng.uniform([0, 0], [60, 40], (70, 2))
    for start in range(0, len(points), 100):
        gp.update(points[start : start + 100], labels[start : start + 100])
        covariance = gp.posterior_covariance(query)
        assert np.linalg.eigvalsh(covariance).min() > -1e-8
        assert np.all(np.isfinite(gp.predict(query, variance="latent").mean))
    assert gp.dictionary_size == 128 and gp.pruned_count > 100
    assert gp.projected_count > 100


def test_dense_dictionary_novelty_remains_nonnegative_before_pruning() -> None:
    # Minimized from a real dense stream: each retained row is needed to reproduce
    # cancellation in the recursive inverse on the development float64 backend.
    indices = [
        0,
        1,
        2,
        3,
        4,
        5,
        8,
        11,
        12,
        16,
        17,
        18,
        19,
        22,
        23,
        24,
        25,
        26,
        27,
        29,
        30,
        31,
        32,
        35,
        36,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        49,
        51,
        53,
        54,
        55,
        57,
        58,
        59,
        60,
        61,
        62,
        64,
        65,
        68,
        69,
        70,
        71,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        94,
        95,
        96,
        98,
        99,
        101,
        102,
    ]
    points = np.random.default_rng(4).uniform([0, 0], [60, 40], (103, 2))[indices]
    gp = SparseOnlineGP(max_basis=128)
    gp.update(points, np.zeros(len(points)))

    assert gp.observation_count == len(points)
    assert gp.pruned_count == 0
    assert gp.last_update_events[-1]["update_kind"] == "projected"
    assert all(event["gamma"] >= 0 for event in gp.last_update_events)
    covariance = gp.posterior_covariance(points)
    assert np.linalg.eigvalsh(covariance).min() > -1e-8
    assert np.all(np.isfinite(gp.predict(points, variance="latent").mean))


def test_covariance_symmetry_cross_consistency_and_predictive_noise() -> None:
    rng = np.random.default_rng(31)
    gp = SparseOnlineGP(max_basis=8)
    gp.update(rng.uniform(-8.0, 8.0, (40, 2)), rng.normal(size=40))
    query = rng.uniform(-8.0, 8.0, (30, 2))
    covariance = gp.posterior_covariance(query)
    assert_allclose(covariance, covariance.T, atol=1e-14)
    assert np.linalg.eigvalsh(covariance).min() > -1e-10
    assert_allclose(np.diag(covariance), gp.predict(query, variance="latent").variance)
    assert_allclose(covariance[:3, 3:], gp.posterior_covariance(query[:3], query[3:]), atol=1e-13)
    assert_allclose(
        gp.predict(query, variance="predictive").variance, np.diag(covariance) + gp.noise_variance
    )


def test_frozen_fantasy_is_joint_label_free_and_nonmutating() -> None:
    rng = np.random.default_rng(13)
    gp = SparseOnlineGP(length_scale=2.0, max_basis=5)
    gp.update(rng.uniform(-6.0, 6.0, (20, 2)), rng.normal(size=20))
    query, future = rng.uniform(-6.0, 6.0, (10, 2)), rng.uniform(-6.0, 6.0, (4, 2))
    before = _snapshot(gp)
    current = gp.predict(query, variance="latent").variance
    cross = gp.posterior_covariance(query, future)
    covariance = gp.posterior_covariance(future) + np.eye(len(future)) * (
        gp.noise_variance + gp.jitter
    )
    expected = current - np.diag(cross @ np.linalg.solve(covariance, cross.T))
    actual = gp.fantasy_variance(query, future)
    assert_allclose(actual, expected, atol=1e-12)
    assert np.all(actual >= 0) and np.all(actual <= current + 1e-12)
    _assert_unchanged(gp, before)


def test_fantasy_matches_exact_before_approximation() -> None:
    rng = np.random.default_rng(73)
    points, labels = rng.uniform(-8.0, 8.0, (8, 2)), rng.normal(size=8)
    gp, exact = SparseOnlineGP(length_scale=2.0), ExactGP(length_scale=2.0)
    gp.update(points, labels)
    exact.update(points, labels)
    query, future = rng.uniform(-8.0, 8.0, (10, 2)), rng.uniform(-8.0, 8.0, (4, 2))
    assert_allclose(
        gp.fantasy_variance(query, future), exact.fantasy_variance(query, future), atol=1e-12
    )


@pytest.mark.parametrize("noise", [0.0, 0.1])
def test_repeated_future_sites_remain_distinct_observations(noise: float) -> None:
    gp = SparseOnlineGP(noise_variance=noise)
    query = np.array([[0.0, 0.0], [1.0, 0.0]])
    gp.update(query[:1], np.array([1.0]))
    one = gp.fantasy_variance(query, query[:1])
    repeated = gp.fantasy_variance(query, np.repeat(query[:1], 4, axis=0))
    assert np.all(np.isfinite(repeated)) and np.all(repeated >= 0.0)
    assert np.all(repeated <= one + 1e-12)
    if noise:
        assert repeated[0] < one[0]


def test_fantasy_is_not_promised_to_equal_label_dependent_future_pruning() -> None:
    gp = SparseOnlineGP(length_scale=1.0, max_basis=2)
    gp.update(np.array([[0.0, 0.0], [4.0, 0.0]]), np.array([0.0, 3.0]))
    query, future = np.array([[0.0, 0.0]]), np.array([[0.0, 4.0]])
    forecast = gp.fantasy_variance(query, future)
    gp.update(future, np.array([-4.0]))
    actual = gp.predict(query, variance="latent").variance
    assert actual[0] > forecast[0] + 0.9


def test_external_mutation_and_empty_update_do_not_change_belief() -> None:
    gp = SparseOnlineGP(max_basis=2)
    points, labels = np.array([[0.0, 0.0], [5.0, 0.0], [0.0, 5.0]]), np.array([1.0, 0.0, -1.0])
    gp.update(points, labels)
    before = _snapshot(gp)
    points[:] = labels[:] = 100
    gp.dictionary_points[:] = 100
    gp.dictionary_observation_indices[:] = 100
    events = gp.last_update_events
    events[-1]["removed_position"][0] = 100
    gp.update(np.empty((0, 2)), np.empty(0))
    _assert_unchanged(gp, before)


def test_empty_queries_and_covariances() -> None:
    gp = SparseOnlineGP()
    empty, query = np.empty((0, 2)), np.zeros((1, 2))
    assert gp.predict(empty, variance="latent").mean.shape == (0,)
    assert gp.posterior_covariance(empty).shape == (0, 0)
    assert gp.posterior_covariance(empty, query).shape == (0, 1)
    assert gp.fantasy_variance(empty, query).shape == (0,)
    assert_allclose(gp.fantasy_variance(query, empty), 1.0)
    gp.update(query, np.ones(1))
    assert gp.posterior_covariance(query, empty).shape == (1, 0)


@pytest.mark.parametrize(
    "parameter,value",
    [
        ("length_scale", 0.0),
        ("length_scale", -1.0),
        ("length_scale", np.inf),
        ("signal_variance", 0.0),
        ("signal_variance", np.nan),
        ("noise_variance", -0.1),
        ("noise_variance", np.inf),
        ("max_basis", 0),
        ("max_basis", -2),
        ("max_basis", 1.5),
        ("max_basis", True),
        ("novelty_tolerance", 0.0),
        ("novelty_tolerance", 1e-15),
        ("novelty_tolerance", 1.0),
        ("novelty_tolerance", np.nan),
    ],
)
def test_invalid_parameters(parameter: str, value: Any) -> None:
    with pytest.raises(ValueError, match=parameter):
        SparseOnlineGP(**{parameter: value})


@pytest.mark.parametrize("points", [np.ones(2), np.ones((2, 3)), np.array([[np.nan, 0.0]])])
def test_invalid_coordinates(points: np.ndarray) -> None:
    gp = SparseOnlineGP()
    with pytest.raises(ValueError):
        gp.update(points, np.ones(len(points)))
    with pytest.raises(ValueError):
        gp.predict(points, variance="latent")
    with pytest.raises(ValueError):
        gp.posterior_covariance(points)
    with pytest.raises(ValueError):
        gp.fantasy_variance(np.zeros((1, 2)), points)


@pytest.mark.parametrize("labels", [np.ones(2), np.ones((1, 1)), np.array([np.inf])])
def test_invalid_label_batch_is_transactional(labels: np.ndarray) -> None:
    gp = SparseOnlineGP()
    gp.update(np.zeros((1, 2)), np.ones(1))
    before = _snapshot(gp)
    with pytest.raises(ValueError):
        gp.update(np.zeros((1, 2)), labels)
    _assert_unchanged(gp, before)


def test_invalid_variance_semantics() -> None:
    with pytest.raises(ValueError, match="variance"):
        SparseOnlineGP().predict(np.zeros((1, 2)), variance="ambiguous")  # type: ignore[arg-type]


def test_all_configuration_properties_are_readonly() -> None:
    gp = SparseOnlineGP()
    for property_name in (
        "length_scale",
        "signal_variance",
        "noise_variance",
        "max_basis",
        "novelty_tolerance",
        "jitter",
        "observation_count",
        "backend_name",
    ):
        with pytest.raises(AttributeError):
            setattr(gp, property_name, 1)


def test_overflow_after_successful_row_rolls_back_entire_batch() -> None:
    gp = SparseOnlineGP(noise_variance=0.0)
    gp.update(np.zeros((1, 2)), np.ones(1))
    before = _snapshot(gp)
    with pytest.raises(FloatingPointError):
        gp.update(np.array([[10.0, 0.0], [0.0, 0.0]]), np.array([1.0, 1e308]))
    _assert_unchanged(gp, before)


def test_injected_pruning_failure_is_transactional(monkeypatch: pytest.MonkeyPatch) -> None:
    gp = SparseOnlineGP(max_basis=1)
    gp.update(np.zeros((1, 2)), np.ones(1))
    before = _snapshot(gp)

    def fail(_: Any) -> dict[str, Any]:
        raise FloatingPointError("injected prune failure")

    monkeypatch.setattr(gp, "_prune", fail)
    with pytest.raises(FloatingPointError, match="injected"):
        gp.update(np.array([[20.0, 0.0]]), np.ones(1))
    _assert_unchanged(gp, before)


def test_material_negative_variance_is_not_silently_clipped() -> None:
    gp = SparseOnlineGP()
    gp.update(np.zeros((1, 2)), np.ones(1))
    gp._state.c[:] = -2.0
    with pytest.raises(FloatingPointError, match="negative variance"):
        gp.predict(np.zeros((1, 2)), variance="latent")


def test_nonpositive_fantasy_covariance_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    gp = SparseOnlineGP(noise_variance=0.0)
    original = gp.posterior_covariance

    def broken(a: np.ndarray, b: np.ndarray | None = None) -> np.ndarray:
        return np.array([[1.0, 2.0], [2.0, 1.0]]) if b is None else original(a, b)

    monkeypatch.setattr(gp, "posterior_covariance", broken)
    with pytest.raises(FloatingPointError, match="factorized"):
        gp.fantasy_variance(np.zeros((1, 2)), np.zeros((2, 2)))


def test_malformed_dictionary_inverse_fails_and_does_not_reset() -> None:
    gp = SparseOnlineGP()
    gp.update(np.zeros((1, 2)), np.ones(1))
    gp._state.q[:] = 2.0
    before = deepcopy(_snapshot(gp))
    with pytest.raises(FloatingPointError, match="negative variance"):
        gp.update(np.zeros((1, 2)), np.ones(1))
    _assert_unchanged(gp, before)
