"""Numerical contracts for the fixed-model exact GP independent implementation."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose

from attain_sampling.gp.exact import ExactGP
from attain_sampling.gp.protocol import FloatArray, GPBelief


def test_prior_and_explicit_variance_semantics() -> None:
    gp = ExactGP(signal_variance=2.0, noise_variance=0.2)
    points = np.array([[0.0, 0.0], [1.0, 2.0]])
    latent = gp.predict(points, variance="latent")
    predictive = gp.predict(points, variance="predictive")
    assert_allclose(latent.mean, 0.0)
    assert_allclose(latent.variance, 2.0)
    assert_allclose(predictive.variance - latent.variance, 0.2)
    assert latent.variance_kind == "latent"
    assert predictive.variance_kind == "predictive"
    assert gp.observation_count == 0
    assert isinstance(gp, GPBelief)


def test_single_point_analytic_posterior() -> None:
    gp = ExactGP(length_scale=2.0, signal_variance=3.0, noise_variance=0.5)
    gp.update(np.array([[0.0, 0.0]]), np.array([2.0]))
    query = np.array([[0.0, 0.0], [2.0, 0.0]])
    cross = 3.0 * np.exp(-np.array([0.0, 4.0]) / 8.0)
    denominator = 3.5 + gp.jitter
    result = gp.predict(query, variance="latent")
    assert_allclose(result.mean, cross * 2.0 / denominator)
    assert_allclose(result.variance, 3.0 - cross**2 / denominator)


def test_repeated_noisy_observations_reduce_latent_below_sensor_noise() -> None:
    gp = ExactGP(signal_variance=1.0, noise_variance=0.1)
    point = np.array([[0.0, 0.0]])
    gp.update(np.repeat(point, 30, axis=0), np.ones(30))
    latent = gp.predict(point, variance="latent").variance
    predictive = gp.predict(point, variance="predictive").variance
    expected = 1.0 / (1.0 + 30.0 / (gp.noise_variance + gp.jitter))
    assert_allclose(latent, expected, atol=1e-12)
    assert latent[0] < gp.noise_variance
    assert predictive[0] > gp.noise_variance
    assert gp.observation_count == 30


def test_covariance_and_fantasies_are_label_independent() -> None:
    first, second = ExactGP(), ExactGP()
    observations = np.array([[0.0, 0.0], [5.0, 6.0], [10.0, 3.0]])
    query = np.array([[2.0, 3.0], [7.0, 8.0]])
    future = np.array([[4.0, 4.0], [9.0, 3.0]])
    first.update(observations, np.array([1.0, 2.0, 3.0]))
    second.update(observations, np.array([-20.0, 19.0, 5.0]))
    assert_allclose(first.posterior_covariance(query), second.posterior_covariance(query))
    assert_allclose(first.fantasy_variance(query, future), second.fantasy_variance(query, future))
    assert not np.allclose(
        first.predict(query, variance="latent").mean,
        second.predict(query, variance="latent").mean,
    )


def test_joint_fantasy_matches_actual_batch_and_sequential_updates() -> None:
    rng = np.random.default_rng(7)
    observed = rng.uniform(-10.0, 10.0, (6, 2))
    labels = rng.normal(size=6)
    future = rng.uniform(-10.0, 10.0, (4, 2))
    query = rng.uniform(-10.0, 10.0, (12, 2))
    gp, batch, sequential = ExactGP(), ExactGP(), ExactGP()
    for model in (gp, batch, sequential):
        model.update(observed, labels)
    fantasy = gp.fantasy_variance(query, future)
    batch.update(future, rng.normal(size=4))
    for site in future:
        sequential.update(site[None, :], np.array([12.0]))
    assert_allclose(fantasy, batch.predict(query, variance="latent").variance, atol=1e-12)
    assert_allclose(fantasy, sequential.predict(query, variance="latent").variance, atol=1e-12)
    assert gp.observation_count == 6
    assert np.all(fantasy <= gp.predict(query, variance="latent").variance + 1e-12)


def test_duplicate_noiseless_sites_and_joint_fantasy_remain_finite() -> None:
    gp = ExactGP(noise_variance=0.0)
    site = np.array([[1.0, 2.0]])
    gp.update(np.repeat(site, 4, axis=0), np.ones(4))
    result = gp.predict(site, variance="latent")
    assert_allclose(result.mean, 1.0, atol=1e-8)
    assert 0.0 <= result.variance[0] < 1e-8
    future = gp.fantasy_variance(site, np.repeat(site, 3, axis=0))
    assert np.all(np.isfinite(future))
    assert np.all(future >= 0.0)


def test_posterior_is_symmetric_psd_and_cross_covariance_consistent() -> None:
    rng = np.random.default_rng(18)
    gp = ExactGP()
    gp.update(rng.uniform(0.0, 20.0, (10, 2)), rng.normal(size=10))
    points = rng.uniform(0.0, 20.0, (20, 2))
    covariance = gp.posterior_covariance(points)
    assert_allclose(covariance, covariance.T, atol=1e-14)
    assert np.linalg.eigvalsh(covariance).min() > -1e-12
    assert_allclose(np.diag(covariance), gp.predict(points, variance="latent").variance)
    assert_allclose(gp.posterior_covariance(points[:3], points[3:]), covariance[:3, 3:])


def test_inputs_are_copied_and_cache_is_invalidated() -> None:
    gp = ExactGP()
    points, labels = np.array([[0.0, 0.0]]), np.array([1.0])
    gp.update(points, labels)
    points[:] = 50.0
    labels[:] = 50.0
    query = np.array([[0.0, 0.0]])
    before = gp.predict(query, variance="latent")
    assert before.mean[0] < 1.0
    gp.update(query, np.array([2.0]))
    after = gp.predict(query, variance="latent")
    assert after.mean[0] > before.mean[0]
    assert after.variance[0] < before.variance[0]


def test_empty_batches_and_queries() -> None:
    gp = ExactGP()
    empty = np.empty((0, 2))
    gp.update(empty, np.empty(0))
    assert gp.observation_count == 0
    assert gp.predict(empty, variance="latent").mean.shape == (0,)
    assert gp.posterior_covariance(empty).shape == (0, 0)
    query = np.array([[0.0, 0.0]])
    assert_allclose(gp.fantasy_variance(query, empty), 1.0)
    assert gp.fantasy_variance(empty, query).shape == (0,)
    gp.update(query, np.ones(1))
    assert gp.posterior_covariance(empty, query).shape == (0, 1)


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
    ],
)
def test_invalid_hyperparameters(parameter: str, value: float) -> None:
    with pytest.raises(ValueError, match=parameter):
        ExactGP(**{parameter: value})


@pytest.mark.parametrize("points", [np.ones(2), np.ones((2, 3)), np.array([[np.nan, 0.0]])])
def test_invalid_coordinates(points: FloatArray) -> None:
    with pytest.raises(ValueError):
        ExactGP().predict(points, variance="latent")


@pytest.mark.parametrize("labels", [np.ones(2), np.ones((1, 1)), np.array([np.inf])])
def test_invalid_labels(labels: FloatArray) -> None:
    with pytest.raises(ValueError):
        ExactGP().update(np.zeros((1, 2)), labels)


def test_invalid_variance_semantic() -> None:
    with pytest.raises(ValueError, match="variance"):
        ExactGP().predict(np.zeros((1, 2)), variance="ambiguous")  # type: ignore[arg-type]


def test_against_sklearn_fixed_hyperparameter_oracle() -> None:
    gaussian_process = pytest.importorskip("sklearn.gaussian_process")
    kernels = pytest.importorskip("sklearn.gaussian_process.kernels")
    rng = np.random.default_rng(93)
    observed = rng.uniform(-5.0, 5.0, (15, 2))
    labels = rng.normal(size=15)
    query = rng.uniform(-5.0, 5.0, (8, 2))
    gp = ExactGP(length_scale=3.0, signal_variance=1.7, noise_variance=0.08)
    gp.update(observed, labels)
    reference = gaussian_process.GaussianProcessRegressor(
        kernel=kernels.ConstantKernel(1.7, constant_value_bounds="fixed")
        * kernels.RBF(3.0, length_scale_bounds="fixed"),
        alpha=0.08 + gp.jitter,
        optimizer=None,
        normalize_y=False,
    ).fit(observed, labels)
    mean, covariance = reference.predict(query, return_cov=True)
    actual = gp.predict(query, variance="latent")
    assert_allclose(actual.mean, mean, atol=1e-12)
    assert_allclose(actual.variance, np.diag(covariance), atol=1e-12)
    assert_allclose(gp.posterior_covariance(query), covariance, atol=1e-12)
