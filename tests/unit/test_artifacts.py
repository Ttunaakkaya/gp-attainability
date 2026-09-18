from __future__ import annotations

import math

import pytest

from attain_sampling.eval.artifacts import build_run_id, canonical_digest


def test_canonical_digest_is_independent_of_mapping_order() -> None:
    left = {"method": "B0", "nested": {"threshold": 0.1, "seed": 7}}
    right = {"nested": {"seed": 7, "threshold": 0.1}, "method": "B0"}

    assert canonical_digest(left) == canonical_digest(right)
    assert len(canonical_digest(left)) == 64


def test_canonical_digest_changes_with_configuration() -> None:
    assert canonical_digest({"seed": 1}) != canonical_digest({"seed": 2})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_digest_rejects_non_json_finite_values(value: float) -> None:
    with pytest.raises(ValueError):
        canonical_digest({"value": value})


def test_build_run_id_normalizes_method_and_accepts_strict_hashes() -> None:
    run_id = build_run_id(
        "  Proposed / Method  ",
        "DEADBEEFcafe",
        17,
        "ABCDEF12345",
    )

    assert run_id == "proposed-method-deadbeef-s17-abcdef1"
    assert "/" not in run_id
    assert " " not in run_id


def test_build_run_id_is_stable() -> None:
    arguments = ("B0", "0123456789abcdef", 0, "fedcba987654321")
    assert build_run_id(*arguments) == build_run_id(*arguments)


def test_build_run_id_rejects_negative_seed() -> None:
    with pytest.raises(ValueError, match="seed must be non-negative"):
        build_run_id("B0", "01234567", -1, "abcdef0")


def test_build_run_id_rejects_boolean_seed() -> None:
    with pytest.raises(ValueError, match="seed must be non-negative"):
        build_run_id("B0", "01234567", True, "abcdef0")


@pytest.mark.parametrize(
    ("config_hash", "git_sha", "message"),
    [
        ("0123456", "abcdef0", "config_hash must contain at least eight"),
        ("01234567", "abcdef", "git_sha must contain at least seven"),
        ("not-a-hash", "abcdef0", "config_hash must contain at least eight"),
        ("dead-beef", "abcdef0", "config_hash must contain at least eight"),
        ("01234567", "abc-def0", "git_sha must contain at least seven"),
    ],
)
def test_build_run_id_requires_minimum_hex_identifiers(
    config_hash: str,
    git_sha: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_run_id("B0", config_hash, 1, git_sha)


def test_build_run_id_rejects_method_without_alphanumeric_content() -> None:
    with pytest.raises(ValueError, match="identifier must contain"):
        build_run_id(" / ", "01234567", 1, "abcdef0")
