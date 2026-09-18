"""The preservation comparator accepts runtime noise and identifies scientific changes."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


def harness():
    path = Path(__file__).resolve().parents[2] / "scripts" / "mission_reference.py"
    spec = importlib.util.spec_from_file_location("mission_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comparison_identifies_the_changed_scientific_field():
    tool = harness()
    original = {"frames": [{"mean_variance": 0.25}], "summary": {"runtime_s": 1.0}}
    changed = {"frames": [{"mean_variance": 0.5}], "summary": {"runtime_s": 2.0}}
    difference = tool.first_difference(tool.normalize(original), tool.normalize(changed))
    assert difference == "$.frames[0].mean_variance: expected 0.25, got 0.5"


def test_only_reviewed_measurements_are_excluded_and_nulls_remain_checked():
    tool = harness()
    first = {"controls": [{"wall_s": 0.01, "solve_s": None, "time_s": 5.0}]}
    second = {"controls": [{"wall_s": 0.02, "solve_s": None, "time_s": 5.0}]}
    assert tool.first_difference(tool.normalize(first), tool.normalize(second)) is None
    second["controls"][0]["solve_s"] = 0.0
    assert "solve_s" in tool.first_difference(tool.normalize(first), tool.normalize(second))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("time_s", 5.1), ("plan_id", "plan-2"), ("received", False), ("status", "failed")],
)
def test_comparator_detects_physical_clock_provenance_receipt_and_status(field, replacement):
    tool = harness()
    original = {
        "samples": [{"time_s": 5.0, "plan_id": "plan-1", "received": True}],
        "status": "completed",
    }
    changed = deepcopy(original)
    if field == "status":
        changed[field] = replacement
    else:
        changed["samples"][0][field] = replacement
    assert field in tool.first_difference(tool.normalize(original), tool.normalize(changed))


@pytest.mark.parametrize("runtime", [-1.0, float("nan"), float("inf"), True, "1"])
def test_invalid_runtime_is_not_hidden_by_normalization(runtime):
    with pytest.raises(ValueError, match="runtime"):
        harness().normalize({"summary": {"runtime_s": runtime}})


def test_check_rejects_changed_capture_harness_before_running(tmp_path):
    tool = harness()
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [],
                "timing_paths": tool.TIMING_PATHS,
                "environment": tool.environment(),
                "harness_sha256": "changed-harness",
            }
        )
    )
    output = tmp_path / "check"
    with pytest.raises(ValueError, match="harness"):
        tool.check(reference, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "changed",
    [
        {"summary": {}},
        {"summary": {"runtime_s": 1.0, "new_field": 1}},
        {"summary": {"runtime_s": None}},
    ],
)
def test_runtime_normalization_does_not_hide_schema_changes(changed):
    tool = harness()
    original = {"summary": {"runtime_s": 1.0}}
    assert tool.first_difference(tool.normalize(original), tool.normalize(changed))


def test_runtime_named_fields_outside_the_reviewed_paths_remain_scientific_evidence():
    tool = harness()
    first = {"budget": {"remaining_time_s": 5.0, "runtime_s": 3.0}}
    second = {"budget": {"remaining_time_s": 5.0, "runtime_s": 4.0}}
    assert "$.budget.runtime_s" in tool.first_difference(
        tool.normalize(first), tool.normalize(second)
    )
