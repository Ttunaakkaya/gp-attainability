"""Deterministic, separated random streams for paired experiments."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SeedManifest:
    """Concrete child seeds derived from one experiment seed."""

    master_seed: int
    field_seed: int
    pose_seed: int
    measurement_noise_key: int
    evaluation_noise_key: int
    planner_tie_break_seed: int

    def as_dict(self) -> Mapping[str, int]:
        return {
            "master_seed": self.master_seed,
            "field_seed": self.field_seed,
            "pose_seed": self.pose_seed,
            "measurement_noise_key": self.measurement_noise_key,
            "evaluation_noise_key": self.evaluation_noise_key,
            "planner_tie_break_seed": self.planner_tie_break_seed,
        }


def _child_seed(sequence: np.random.SeedSequence) -> int:
    return int(sequence.generate_state(1, dtype=np.uint64)[0])


def derive_seed_manifest(master_seed: int) -> SeedManifest:
    """Spawn independent named streams without relying on global RNG state."""

    if master_seed < 0:
        raise ValueError("master_seed must be non-negative")
    children = np.random.SeedSequence(master_seed).spawn(5)
    return SeedManifest(
        master_seed=master_seed,
        field_seed=_child_seed(children[0]),
        pose_seed=_child_seed(children[1]),
        measurement_noise_key=_child_seed(children[2]),
        evaluation_noise_key=_child_seed(children[3]),
        planner_tie_break_seed=_child_seed(children[4]),
    )


def indexed_normal(
    key_seed: int,
    robot_id: int,
    sample_index: int,
    *,
    stream: str = "measurement",
) -> float:
    """Return a stable standard-normal innovation for a semantic event key.

    The value does not depend on call order. Two controllers can therefore share the
    same innovations even when their trajectories or solver branches differ.
    """

    if min(key_seed, robot_id, sample_index) < 0:
        raise ValueError("key_seed, robot_id, and sample_index must be non-negative")
    if not stream:
        raise ValueError("stream must be non-empty")

    payload = f"v1|{key_seed}|{robot_id}|{sample_index}|{stream}".encode()
    digest = hashlib.blake2b(payload, digest_size=16, person=b"attain-noise-v1").digest()
    rng_seed = int.from_bytes(digest, byteorder="little", signed=False)
    return float(np.random.default_rng(rng_seed).standard_normal())
