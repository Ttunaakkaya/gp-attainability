"""The M3 auditors must reject corruption, not only accept self-generated data."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from attain_sampling.sim.mapping import MappingConfig, run_mapping


@pytest.fixture(scope="module")
def audit_module():
    directory = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location("m3_audit_test", directory / "validate_m3.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(directory))


@pytest.fixture(scope="module")
def sparse_run():
    return run_mapping(
        MappingConfig(
            duration_s=10,
            robot_count=2,
            gp_backend="sogp",
            sogp_max_basis=2,
            grid_shape=(6, 4),
            dp_grid_shape=(4, 3),
            dp_horizon_steps=2,
        ),
        "dp",
    )


def test_replay_and_forecast_studies(audit_module):
    stream = audit_module.synthetic_stream(40)
    replay = audit_module.replay_stream(stream, capacities=(4, 8))
    assert len(replay["records"]) == 3
    assert all(r["pruned_count"] > 0 for r in replay["records"][1:])
    ordering = audit_module.ordering_study(stream, capacity=4)
    assert not ordering["same_order_different_labels_retained_set_equal"]
    forecast = audit_module.forecast_approximation_study(stream, capacities=(4, 8))
    assert all(r["future_pruned_count"] > 0 for r in forecast["records"])
    assert max(r["variance_max_absolute_gap"] for r in forecast["records"]) > 0.01


def test_belief_and_prefix_audits_accept_real_run(audit_module, sparse_run):
    assert audit_module.audit_sogp_run(sparse_run)["observations_replayed"] == 6
    assert audit_module.audit_plans(sparse_run)["prefixes_recomputed"] == 5


@pytest.mark.parametrize("corruption", ["frame", "count", "capacity", "event", "sample_order"])
def test_belief_audit_rejects_corruption(audit_module, sparse_run, corruption):
    invalid = copy.deepcopy(sparse_run)
    if corruption == "frame":
        invalid["frames"][-1]["mean"][0][0] += 0.1
    elif corruption == "count":
        invalid["gp_telemetry"]["observation_count"] += 1
    elif corruption == "capacity":
        invalid["gp_telemetry"]["max_basis"] += 1
    elif corruption == "event":
        invalid["gp_updates"][-1]["gamma"] += 0.1
    else:
        invalid["samples"][0], invalid["samples"][1] = invalid["samples"][1], invalid["samples"][0]
    with pytest.raises(AssertionError):
        audit_module.audit_sogp_run(invalid)


@pytest.mark.parametrize("corruption", ["prefix", "candidate", "received_keys", "scope"])
def test_plan_audit_rejects_corruption(audit_module, sparse_run, corruption):
    invalid = copy.deepcopy(sparse_run)
    plan = invalid["plans"][0]
    if corruption == "prefix":
        plan["forecast"][-1]["mean_variance"] += 0.1
    elif corruption == "candidate":
        next(c for c in plan["candidates"] if c["status"] == "accepted")[
            "terminal_mean_variance"
        ] += 0.1
    elif corruption == "received_keys":
        plan["received_sample_keys"].pop()
    else:
        plan["forecast_scope"] = "exact_gp_future"
    with pytest.raises(AssertionError):
        audit_module.audit_plans(invalid)
