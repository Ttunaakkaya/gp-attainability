"""M7 curvature USV inside the simulator: every method runs, audits and keeps invariants."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from attain_sampling.demo.runner import run_comparison, scenario_config
from attain_sampling.sim import usv
from attain_sampling.sim.mapping import (
    MappingConfig,
    initial_positions,
    run_mapping,
    usv_turn_radius,
)

METHODS = ("sweep", "greedy", "adaptive", "dp", "p")


def _config(**overrides):
    base = scenario_config(
        "combined", robots=4, seed=7, duration_s=15.0, controller="filter", model="usv_curvature"
    )
    return replace(base, target_mean_variance=0.2, **overrides)


@pytest.fixture(scope="module")
def comparison():
    return run_comparison(_config(), scenario="combined", methods=METHODS)


def test_the_curvature_model_is_configured_explicitly():
    config = _config()
    assert usv_turn_radius(config) == pytest.approx(2.0 / 0.45)
    starts = initial_positions(config)
    assert starts[1, 0] - starts[0, 0] == pytest.approx(2 * usv_turn_radius(config) + 2.0)
    assert (
        usv.loiter_assignment(
            starts,
            np.zeros(4),
            radius=usv_turn_radius(config),
            domain=config.domain,
            min_separation=config.min_separation,
        )
        is not None
    )
    holonomic = scenario_config("combined", robots=4)
    assert np.all(initial_positions(holonomic)[:, 0] == 3.0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"controller": "qp"}, "holonomic"),
        ({"domain": (10.0, 10.0)}, "too small"),
        ({"dp_motion_primitives": 1}, "boolean"),
        ({"model": "boat"}, "model must be one of"),
    ],
)
def test_invalid_curvature_settings_are_rejected(overrides, message):
    base = {
        "model": "usv_curvature",
        "controller": "filter",
        "robot_count": 2,
    }
    base.update(overrides)
    with pytest.raises(ValueError, match=message):
        MappingConfig(**base)


def test_every_method_completes_with_paired_events(comparison):
    assert comparison["status"] == "completed"
    assert [run["method"] for run in comparison["runs"]] == list(METHODS)
    schedules = {
        tuple((s["time_s"], s["robot_id"], s["received"]) for s in run["samples"])
        for run in comparison["runs"]
    }
    assert len(schedules) == 1


@pytest.mark.parametrize("method", METHODS)
def test_executed_motion_keeps_the_vehicle_invariants(comparison, method):
    run = next(run for run in comparison["runs"] if run["method"] == method)
    config = _config()
    radius = usv_turn_radius(config)
    executed = [event for event in run["controls"] if event["phase"] == "execution"]
    assert executed and all(event["backend"] == "arc_filter" for event in executed)
    for state in run["motion"]:
        positions = np.asarray(state["positions"])
        assert np.all(positions >= 0) and np.all(positions <= np.asarray(config.domain))
        assert (
            usv.loiter_assignment(
                positions,
                np.asarray(state["headings"]),
                radius=radius,
                domain=config.domain,
                min_separation=config.min_separation,
            )
            is not None
        )
        assert max(state["speeds"]) <= config.max_speed + 1e-9
    assert run["summary"]["min_separation"] >= config.min_separation - 1e-9
    for event in executed:
        assert np.all(np.abs(event["applied_curvatures"]) <= 1 / radius + 1e-12)
        assert event["certified_arc_separation"] >= (
            config.min_separation - usv.ARC_SEPARATION_TOLERANCE_M
        )


def test_planners_use_motion_primitives_and_p_rolls_them_out(comparison):
    dp = next(run for run in comparison["runs"] if run["method"] == "dp")
    p = next(run for run in comparison["runs"] if run["method"] == "p")
    assert dp["plans"] and all(
        plan["planning_scope"].startswith("independent_motion_primitive_tree")
        for plan in dp["plans"]
    )
    assert all(plan["motion_model"]["model"] == "usv_curvature" for plan in dp["plans"])
    decisions = p["plans"]
    assert decisions and all(
        "static_hold_geometric_check_stopped_curvature_usv" in candidate["continuation"]["scope"]
        for plan in decisions
        for candidate in plan["candidates"]
        if candidate.get("status") == "accepted"
    )
    assert any(
        candidate.get("rollout") is not None
        for plan in decisions
        for candidate in plan["candidates"]
    )


def test_the_straight_line_planner_is_a_selectable_variant():
    run = run_mapping(_config(dp_motion_primitives=False, duration_s=10.0), "dp")
    assert run["status"] == "completed"
    assert all(
        plan["planning_scope"].startswith("independent_coarse_frozen_reward_bellman")
        for plan in run["plans"]
    )
    inset = usv_turn_radius(_config()) + 0.5
    for plan in run["plans"]:
        for epoch in plan["targets_by_epoch"]:
            targets = np.asarray(epoch)
            assert np.all(targets >= inset - 1e-9)
            assert np.all(targets <= np.asarray(_config().domain) - inset + 1e-9)


def test_the_original_usv_still_cannot_use_the_planners():
    config = scenario_config("combined", robots=2, model="usv")
    with pytest.raises(ValueError, match="original turn-in-place USV"):
        run_comparison(config, methods=("dp",))
