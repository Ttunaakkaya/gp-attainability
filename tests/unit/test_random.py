from __future__ import annotations

import math

import numpy as np
import pytest

from attain_sampling.random import derive_seed_manifest, indexed_normal


def test_seed_manifest_is_repeatable_and_has_separated_children() -> None:
    first = derive_seed_manifest(12345)
    second = derive_seed_manifest(12345)

    assert first == second
    assert first.master_seed == 12345
    child_seeds = {
        first.field_seed,
        first.pose_seed,
        first.measurement_noise_key,
        first.evaluation_noise_key,
        first.planner_tie_break_seed,
    }
    assert len(child_seeds) == 5
    assert first.as_dict()["master_seed"] == 12345


def test_different_master_seeds_produce_different_manifests() -> None:
    assert derive_seed_manifest(1) != derive_seed_manifest(2)


def test_seed_manifest_rejects_negative_seed() -> None:
    with pytest.raises(ValueError, match="master_seed must be non-negative"):
        derive_seed_manifest(-1)


def test_indexed_normal_is_independent_of_call_order_and_global_rng() -> None:
    expected = indexed_normal(100, 2, 9)
    indexed_normal(100, 99, 999)
    np.random.seed(7)
    np.random.standard_normal(20)

    actual = indexed_normal(100, 2, 9)

    assert actual == expected
    assert math.isfinite(actual)


def test_indexed_normal_uses_all_semantic_key_components() -> None:
    baseline = indexed_normal(100, 2, 9, stream="measurement")

    variants = {
        indexed_normal(101, 2, 9, stream="measurement"),
        indexed_normal(100, 3, 9, stream="measurement"),
        indexed_normal(100, 2, 10, stream="measurement"),
        indexed_normal(100, 2, 9, stream="evaluation"),
    }

    assert baseline not in variants
    assert len(variants) == 4


@pytest.mark.parametrize(
    ("key_seed", "robot_id", "sample_index"),
    [(-1, 0, 0), (0, -1, 0), (0, 0, -1)],
)
def test_indexed_normal_rejects_negative_key_parts(
    key_seed: int,
    robot_id: int,
    sample_index: int,
) -> None:
    with pytest.raises(ValueError, match="must be non-negative"):
        indexed_normal(key_seed, robot_id, sample_index)


def test_indexed_normal_rejects_empty_stream() -> None:
    with pytest.raises(ValueError, match="stream must be non-empty"):
        indexed_normal(0, 0, 0, stream="")
