"""T03/T04: our SOGP must equal an independent transcription of the paper's p. 305 rules.

The reference below is written directly from Suenaga et al., ECC 2025, p. 305, using the
paper's own operators — ``W`` appends a zero, ``U`` pads a matrix, ``beta`` is the novelty,
``omega`` the threshold, ``eta`` the removal score — and deliberately does not reuse the
structure of ``attain_sampling.gp.sogp``.
"""

from __future__ import annotations

import numpy as np
import pytest

from attain_sampling.control.rate_constraint import rbf_kernel
from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sources.ecc2025 import parameters

PAPER = parameters()


def W(vector: np.ndarray) -> np.ndarray:  # noqa: N802 - the paper's operator name
    return np.append(vector, 0.0)


def U(matrix: np.ndarray) -> np.ndarray:  # noqa: N802 - the paper's operator name
    size = matrix.shape[0]
    padded = np.zeros((size + 1, size + 1))
    padded[:size, :size] = matrix
    return padded


class PaperSOGP:
    """Literal p. 305 transcription with k(x, x') = s * exp(-|x-x'|^2 / (2 L^2))."""

    def __init__(self, *, L: float, sigma_eps: float, omega: float, n_max: int, s: float = 1.0):
        self.L, self.noise, self.omega, self.n_max, self.s = L, sigma_eps**2, omega, n_max, s
        self.Z = np.empty((0, 2))
        self.a = np.empty(0)
        self.C = np.empty((0, 0))
        self.Q = np.empty((0, 0))

    def k(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return self.s * rbf_kernel(a, b, self.L)

    def moments(self, x: np.ndarray) -> tuple[float, float]:
        kx = self.k(self.Z, x[None, :])[:, 0]
        return float(self.a @ kx), float(self.s + kx @ self.C @ kx)

    def add(self, x: np.ndarray, y: float) -> None:
        kx = self.k(self.Z, x[None, :])[:, 0]
        mu, var = self.moments(x)
        q = (y - mu) / (var + self.noise)  # eq. (1)
        r = -1.0 / (var + self.noise)  # eq. (1)
        e_hat = self.Q @ kx
        beta = self.s - kx @ self.Q @ kx  # novelty, p. 305
        if len(self.Z) and beta < self.omega:
            # "the new sample gets discarded": project, s = C k + e_hat, no growth.
            s_vec = self.C @ kx + e_hat
            self.a = self.a + q * s_vec
            self.C = self.C + r * np.outer(s_vec, s_vec)
            return
        e_tau = np.zeros(len(self.Z) + 1)
        e_tau[-1] = 1.0
        s_vec = W(self.C @ kx) + e_tau  # eq. (1)
        self.a = W(self.a) + q * s_vec
        self.C = U(self.C) + r * np.outer(s_vec, s_vec)
        diff = W(e_hat) - e_tau
        self.Q = U(self.Q) + np.outer(diff, diff) / beta if len(self.Z) else np.array([[1 / beta]])
        self.Z = np.vstack((self.Z, x))
        if len(self.Z) > self.n_max:
            eta = np.abs(self.a) / np.diag(self.Q)  # removal score, p. 305
            j = int(np.argmin(eta))
            keep = np.arange(len(self.Z)) != j
            Qj, qj = self.Q[keep, j], self.Q[j, j]
            Cj, cj = self.C[keep, j], self.C[j, j]
            aj = self.a[j]
            self.a = self.a[keep] - aj * Qj / qj
            self.C = (
                self.C[np.ix_(keep, keep)]
                + cj * np.outer(Qj, Qj) / qj**2
                - (np.outer(Qj, Cj) + np.outer(Cj, Qj)) / qj
            )
            self.Q = self.Q[np.ix_(keep, keep)] - np.outer(Qj, Qj) / qj
            self.Z = self.Z[keep]


def stream(seed: int, count: int, spread: float = 12.0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    points = rng.uniform(-spread, spread, size=(count, 2))
    # Deliberate near-duplicates exercise the projection branch.
    points[5::7] = points[4::7][: len(points[5::7])] + 0.05
    labels = np.sin(points[:, 0] / 3.0) + 0.5 * np.cos(points[:, 1] / 4.0)
    return points, labels + rng.normal(scale=PAPER["sigma_eps"], size=count)


@pytest.mark.parametrize(("seed", "n_max"), [(0, 6), (1, 10), (2, 360)])
def test_our_sogp_equals_the_paper_update_rules(seed, n_max):
    points, labels = stream(seed, 60)
    ours = SparseOnlineGP(
        length_scale=PAPER["L"],
        signal_variance=1.0,
        noise_variance=PAPER["sigma_eps"] ** 2,
        max_basis=n_max,
        novelty_tolerance=PAPER["omega"],
    )
    paper = PaperSOGP(L=PAPER["L"], sigma_eps=PAPER["sigma_eps"], omega=PAPER["omega"], n_max=n_max)
    for point, label in zip(points, labels, strict=True):
        ours.update(point[None, :], np.asarray([label]))
        paper.add(point, float(label))
    assert ours.dictionary_points == pytest.approx(paper.Z, abs=0)
    queries = np.random.default_rng(seed + 9).uniform(-15.0, 15.0, size=(40, 2))
    prediction = ours.predict(queries, variance="latent")
    expected = [paper.moments(query) for query in queries]
    assert prediction.mean == pytest.approx([m for m, _ in expected], rel=1e-8, abs=1e-8)
    assert prediction.variance == pytest.approx([v for _, v in expected], rel=1e-8, abs=1e-8)
    assert ours.projected_count > 0  # the duplicates really were projected
    if n_max < 20:
        assert ours.pruned_count > 0  # and capacity really forced label-dependent removal


def test_an_absolute_omega_with_a_signal_variance_needs_a_scaled_tolerance():
    """Our threshold is relative to k(x,x); the paper's omega is absolute on beta."""
    s = 4.0
    points, labels = stream(3, 50)
    ours = SparseOnlineGP(
        length_scale=PAPER["L"],
        signal_variance=s,
        noise_variance=PAPER["sigma_eps"] ** 2,
        max_basis=8,
        novelty_tolerance=PAPER["omega"] / s,
    )
    paper = PaperSOGP(
        L=PAPER["L"], sigma_eps=PAPER["sigma_eps"], omega=PAPER["omega"], n_max=8, s=s
    )
    for point, label in zip(points, labels, strict=True):
        ours.update(point[None, :], np.asarray([label]))
        paper.add(point, float(label))
    assert ours.dictionary_points == pytest.approx(paper.Z, abs=0)
    queries = np.random.default_rng(4).uniform(-15.0, 15.0, size=(20, 2))
    expected = np.asarray([paper.moments(query)[1] for query in queries])
    assert ours.predict(queries, variance="latent").variance == pytest.approx(expected, rel=1e-8)


def test_pruning_depends_on_labels_as_the_paper_implies():
    points, labels = stream(5, 40)
    kept = []
    for scale in (1.0, -3.0):
        model = SparseOnlineGP(
            length_scale=PAPER["L"],
            noise_variance=PAPER["sigma_eps"] ** 2,
            max_basis=6,
            novelty_tolerance=PAPER["omega"],
        )
        for index, point in enumerate(points):
            value = labels[index] * scale if index % 3 else labels[index]
            model.update(point[None, :], np.asarray([value]))
        kept.append(model.dictionary_observation_indices.tolist())
    assert kept[0] != kept[1]


def test_theorem_1_premise_c_equals_minus_inverse_regularized_gram_when_all_admitted():
    """Proof of Thm. 1, p. 308: with every point admitted, C = -(K + sigma_eps^2 I)^-1."""
    rng = np.random.default_rng(6)
    points = rng.uniform(-30.0, 30.0, size=(12, 2))
    model = PaperSOGP(L=PAPER["L"], sigma_eps=PAPER["sigma_eps"], omega=1e-9, n_max=100)
    for point in points:
        model.add(point, float(rng.normal()))
    assert len(model.Z) == len(points)
    gram = rbf_kernel(points, points, PAPER["L"]) + PAPER["sigma_eps"] ** 2 * np.eye(len(points))
    expected = -np.linalg.inv(gram)
    assert np.allclose(model.C, expected, rtol=1e-8, atol=1e-10)


def test_a_repeated_site_is_projected_rather_than_dividing_by_a_vanishing_novelty():
    """Why the novelty test is applied at every step, not only at capacity."""
    model = SparseOnlineGP(
        length_scale=PAPER["L"],
        noise_variance=PAPER["sigma_eps"] ** 2,
        max_basis=int(PAPER["n_d_max"]),
        novelty_tolerance=PAPER["omega"],
    )
    site = np.asarray([[1.0, 2.0]])
    for value in (0.3, 0.5, 0.4, 0.6):
        model.update(site, np.asarray([value]))
    # A stalled robot resampling one site keeps a single basis vector and a finite model.
    assert model.dictionary_size == 1
    assert model.projected_count == 3
    assert np.all(np.isfinite(model.predict(site, variance="latent").variance))
