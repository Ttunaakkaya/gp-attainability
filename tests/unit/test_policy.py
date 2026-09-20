"""M4 decision contract: equal remaining budget, plan retention and target risk."""

from __future__ import annotations

import copy
import json
from typing import Any

import numpy as np
import pytest

from attain_sampling.attainability.budget import mission_budget
from attain_sampling.attainability.policy import PolicySettings, manage_plan
from attain_sampling.attainability.rollout import StepOutcome
from attain_sampling.gp.exact import ExactGP
from attain_sampling.planning.timed_dp import DPSettings, plan_timed_dp

DOMAIN = (12.0, 12.0)
POSITIONS = np.asarray([[1.0, 1.0], [1.0, 9.0]])
HEADINGS = np.zeros(2)
QUERY = np.stack(np.meshgrid(np.linspace(0, 12, 7), np.linspace(0, 12, 7)), axis=-1).reshape(-1, 2)


def tracking_stepper(fraction: float = 1.0):
    def step(positions, headings, targets, *, tick, tracking_time_s):
        return StepOutcome(
            accepted=True,
            positions=positions + fraction * (targets - positions),
            headings=headings,
            intervention=False,
            min_separation=4.0,
        )

    return step


def refusing_stepper():
    def step(positions, headings, targets, *, tick, tracking_time_s):
        return StepOutcome(
            accepted=False,
            positions=positions,
            headings=headings,
            intervention=False,
            min_separation=float("nan"),
            failure_reason="solver_rejected",
        )

    return step


def hold_only_stepper():
    """Reject moving candidates, but leave a genuinely executable hold available."""

    def step(positions, headings, targets, *, tick, tracking_time_s):
        tracker = tracking_stepper() if np.array_equal(positions, targets) else refusing_stepper()
        return tracker(positions, headings, targets, tick=tick, tracking_time_s=tracking_time_s)

    return step


def setup(now: float = 0.0, end: float = 20.0, horizon: int = 2):
    gp = ExactGP(length_scale=2.0, noise_variance=0.04)
    gp.update(POSITIONS, np.asarray([2.0, -1.0]))
    dp = plan_timed_dp(
        gp,
        POSITIONS,
        QUERY,
        domain=DOMAIN,
        max_speed=3.0,
        min_separation=1.0,
        sample_period_s=5.0,
        now_s=now,
        mission_end_s=end,
        plan_version=0,
        settings=DPSettings(
            horizon_steps=horizon, grid_shape=(5, 5), include_greedy_candidates=True
        ),
    )
    budget = mission_budget(
        now_s=now, mission_end_s=end, sample_period_s=5.0, robot_count=2, max_speed=3.0
    )
    return gp, dp, budget


def decide(**overrides: Any) -> dict[str, Any]:
    gp, dp, budget = setup(
        now=overrides.pop("now", 0.0),
        end=overrides.pop("end", 20.0),
        horizon=overrides.pop("horizon", 2),
    )
    options: dict[str, Any] = {
        "gp": gp,
        "query": QUERY,
        "positions": POSITIONS,
        "headings": HEADINGS,
        "budget": budget,
        "dp_plan": dp,
        "retained_plan": None,
        "stepper": tracking_stepper(),
        "start_tick": round(budget.now_s / 0.5),
        "dt": 0.5,
        "domain": DOMAIN,
        "min_separation": 1.0,
        "trigger": "initial",
        "plan_version": 0,
        "settings": PolicySettings(),
    }
    options.update(overrides)
    return manage_plan(**options)


def accepted(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in plan["candidates"] if row["status"] == "accepted"]


def test_every_candidate_is_scored_over_the_same_remaining_sensing_budget():
    _, _, budget = setup()
    plan = decide()
    assert budget.remaining_sample_epochs == 4
    scored = {row["scored_sample_epochs"] for row in accepted(plan)}
    assert scored == {budget.remaining_sample_epochs}
    for row in accepted(plan):
        assert row["horizon_epochs"] + row["continuation_epochs"] == budget.remaining_sample_epochs


def test_mission_end_forecast_matches_an_independent_joint_conditioning():
    gp, dp, budget = setup()
    plan = manage_plan(
        gp=gp,
        query=QUERY,
        positions=POSITIONS,
        headings=HEADINGS,
        budget=budget,
        dp_plan=dp,
        retained_plan=None,
        stepper=tracking_stepper(),
        start_tick=0,
        dt=0.5,
        domain=DOMAIN,
        min_separation=1.0,
        trigger="initial",
        plan_version=0,
        settings=PolicySettings(),
    )
    sites = np.asarray(plan["predicted_sample_sites"], dtype=float)
    held = np.repeat(sites[-1][None], plan["mission_end_forecast"]["continuation_epochs"], axis=0)
    combined = np.concatenate((sites, held)).reshape(-1, 2)
    expected = float(np.mean(gp.fantasy_variance(QUERY, combined)))
    assert plan["mission_end_forecast"]["mean_variance"] == pytest.approx(expected)


def test_rollout_scores_reached_positions_while_execution_keeps_commanded_cells():
    plan = decide(stepper=tracking_stepper(0.4))
    targets = np.asarray(plan["targets_by_epoch"], dtype=float)
    sites = np.asarray(plan["predicted_sample_sites"], dtype=float)
    assert targets.shape == sites.shape
    assert not np.allclose(targets, sites)
    assert plan["rollout_scope"].startswith("nominal")
    for row in accepted(plan):
        if row["horizon_epochs"]:
            assert row["rollout"]["feasible"] is True


def test_rollout_ablation_falls_back_to_the_geometric_assumption():
    plan = decide(settings=PolicySettings(controller_rollout=False))
    assert plan["targets_by_epoch"] == plan["predicted_sample_sites"]
    assert "rollout ablation" in plan["planning_scope"]
    assert all(row.get("rollout") is None for row in plan["candidates"])


def test_a_still_good_plan_is_retained_instead_of_being_swapped_for_an_equal_one():
    first = decide()
    second = decide(retained_plan=first, trigger="periodic_sampling_epoch", plan_version=1)
    assert second["decision"]["action"] == "retained"
    assert second["selected_candidate_id"] == "retained-plan"
    assert second["decision"]["expected_gain"] <= second["decision"]["switch_margin_variance"]


def test_a_clearly_worse_retained_plan_is_replaced_with_a_recorded_gain():
    first = decide()
    stale = copy.deepcopy(first)
    # Park the whole retained route in one corner the fleet has already measured.
    stale["targets_by_epoch"] = [[[1.0, 1.0], [1.0, 9.0]] for _ in stale["sample_times_s"]]
    second = decide(retained_plan=stale, trigger="periodic_sampling_epoch", plan_version=1)
    assert second["decision"]["action"] == "replaced"
    assert second["selected_candidate_id"] != "retained-plan"
    assert second["decision"]["expected_gain"] > second["decision"]["switch_margin_variance"]


def test_retention_ablation_never_offers_or_selects_the_retained_plan():
    first = decide()
    second = decide(
        retained_plan=first,
        trigger="periodic_sampling_epoch",
        plan_version=1,
        settings=PolicySettings(retain_plan=False),
    )
    assert second["decision"]["action"] == "replaced"
    assert all(row["candidate_id"] != "retained-plan" for row in second["candidates"])
    assert second["decision"]["retained_candidate_id"] is None


def test_the_rollout_candidate_cap_is_bounded_and_records_what_it_skipped():
    plan = decide(settings=PolicySettings(max_rollout_candidates=2))
    skipped = [row for row in plan["candidates"] if row["status"] == "not_evaluated"]
    assert skipped
    assert all(row["rejection_reason"] == "bounded_rollout_candidate_cap" for row in skipped)
    assert all("no claim about this route" in row["claim_limit"] for row in skipped)
    # The always-executable hold is never dropped by the cap.
    assert any(row["candidate_id"] == "nominal-hold" for row in accepted(plan))
    assert len(accepted(plan)) == 3
    assert len(skipped) == 2
    assert plan["decision"]["candidates_evaluated"] == 3
    assert plan["decision"]["candidates_rejected"] == 0
    assert plan["decision"]["candidates_not_evaluated"] == 2


@pytest.mark.parametrize("cap", [2, 6])
def test_rejected_candidates_do_not_poison_an_executable_hold(cap):
    plan = decide(stepper=hold_only_stepper(), settings=PolicySettings(max_rollout_candidates=cap))
    assert plan["selected_candidate_id"] == "nominal-hold"
    rejected = [row for row in plan["candidates"] if row["status"] == "rejected"]
    skipped = [row for row in plan["candidates"] if row["status"] == "not_evaluated"]
    assert rejected
    assert all(row["rollout"]["failed_epoch"] == 0 for row in rejected)
    assert all(row["rollout"]["min_separation_m"] is None for row in rejected)
    decision = plan["decision"]
    assert decision["candidates_evaluated"] == len(accepted(plan)) + len(rejected)
    assert decision["candidates_rejected"] == len(rejected)
    assert decision["candidates_not_evaluated"] == len(skipped)
    assert decision["candidates_evaluated"] + len(skipped) == len(plan["candidates"])
    json.dumps(plan, allow_nan=False)


def test_holding_is_a_real_candidate_and_is_worse_than_moving_on_a_fresh_field():
    plan = decide()
    hold = next(row for row in accepted(plan) if row["candidate_id"] == "nominal-hold")
    assert hold["continuation"]["accepted"] is True
    assert hold["mission_end_mean_variance"] > plan["mission_end_forecast"]["mean_variance"]


def test_target_risk_reports_the_candidate_set_not_an_impossibility():
    reachable = decide(settings=PolicySettings(target_mean_variance=10.0))
    assert reachable["target_risk"]["status"] == "forecast_attainable_in_candidate_set"
    assert reachable["target_risk"]["margin"] > 0
    missed = decide(settings=PolicySettings(target_mean_variance=1e-6))
    assert missed["target_risk"]["status"] == "no_candidate_forecast_reaches_target"
    assert missed["target_risk"]["margin"] < 0
    assert any("not impossibility" in limit for limit in missed["target_risk"]["claim_limits"])
    assert decide()["target_risk"]["status"] == "no_mission_target_configured"


def test_a_decision_records_its_trigger_and_budget_without_resetting_it():
    plan = decide(now=5.0, trigger="missed_measurement", start_tick=10)
    assert plan["decision"]["trigger"] == "missed_measurement"
    assert plan["budget"]["remaining_sample_epochs"] == 3
    assert plan["budget"]["mission_end_s"] == pytest.approx(20.0)


def test_when_no_candidate_is_executable_the_decision_fails_explicitly():
    with pytest.raises(FloatingPointError):
        decide(stepper=refusing_stepper())


def test_a_horizon_outside_the_remaining_budget_is_rejected():
    gp, dp, _ = setup()
    wrong = mission_budget(
        now_s=10.0, mission_end_s=20.0, sample_period_s=5.0, robot_count=2, max_speed=3.0
    )
    with pytest.raises(ValueError):
        manage_plan(
            gp=gp,
            query=QUERY,
            positions=POSITIONS,
            headings=HEADINGS,
            budget=wrong,
            dp_plan=dp,
            retained_plan=None,
            stepper=tracking_stepper(),
            start_tick=20,
            dt=0.5,
            domain=DOMAIN,
            min_separation=1.0,
            trigger="periodic_sampling_epoch",
            plan_version=1,
            settings=PolicySettings(),
        )


def test_plan_record_is_json_safe_and_states_its_claim_limits():
    plan = decide()
    json.dumps(plan, allow_nan=False)
    assert "executable_upper_candidate_not_an_attainability_floor" in plan["claim_limits"]
    assert plan["plan_id"].startswith("p-")


@pytest.mark.parametrize(
    "settings",
    [
        {"max_rollout_candidates": 0},
        {"max_rollout_candidates": True},
        {"deviation_trigger_m": -1.0},
        {"switch_margin": float("nan")},
        {"target_mean_variance": 0.0},
        {"controller_rollout": 1},
    ],
)
def test_invalid_policy_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        PolicySettings(**settings)


def test_an_undeclared_trigger_is_rejected():
    with pytest.raises(ValueError):
        decide(trigger="because_i_felt_like_it")


@pytest.fixture
def slightly_worse_retained_plan():
    stale = copy.deepcopy(decide())
    targets = np.asarray(stale["targets_by_epoch"], dtype=float)
    targets[:, :, 0] = np.maximum(0.0, targets[:, :, 0] - 0.1)
    stale["targets_by_epoch"] = targets.tolist()
    return stale


def test_fixed_target_takes_priority_over_retaining_a_route_that_misses_it(
    slightly_worse_retained_plan,
):
    stale = slightly_worse_retained_plan
    # Real-GP development fixture: best ~= .76409138, retained ~= .76411325.
    # This fixed target lies between them; the gain is below the 1% switch margin.
    plan = decide(
        retained_plan=stale,
        trigger="periodic_sampling_epoch",
        plan_version=1,
        settings=PolicySettings(target_mean_variance=0.76410),
    )

    assert plan["decision"]["action"] == "replaced"
    assert plan["selected_candidate_id"] != "retained-plan"
    assert plan["decision"]["reason"] == "candidate_reaches_target_while_retained_plan_misses"
    assert plan["decision"]["retained_mission_end_mean_variance"] > 0.76410
    assert plan["mission_end_forecast"]["mean_variance"] <= 0.76410
    assert 0 < plan["decision"]["expected_gain"] < plan["decision"]["switch_margin_variance"]
    assert plan["decision"]["candidates_evaluated"] == 6


@pytest.mark.parametrize("target", [None, 0.75, 0.78])
def test_retention_margin_still_applies_without_a_target_crossing(
    slightly_worse_retained_plan, target
):
    plan = decide(
        retained_plan=slightly_worse_retained_plan,
        settings=PolicySettings(target_mean_variance=target),
    )

    assert plan["decision"]["action"] == "retained"
    assert plan["decision"]["reason"] == "retained_plan_within_switch_margin_of_the_best_candidate"
    assert plan["selected_candidate_id"] == "retained-plan"
    risk = plan["target_risk"]
    assert (
        risk["selected_mission_end_mean_variance"]
        > risk["best_candidate_mission_end_mean_variance"]
    )
    if target is None:
        assert risk["margin"] is None
        assert risk["status"] == "no_mission_target_configured"
    elif target == 0.75:
        assert risk["margin"] < 0
        assert risk["status"] == "no_candidate_forecast_reaches_target"
    else:
        assert risk["margin"] > target - risk["selected_mission_end_mean_variance"] > 0
        assert risk["status"] == "forecast_attainable_in_candidate_set"


@pytest.mark.parametrize("boundary,action", [("best", "replaced"), ("retained", "retained")])
def test_equality_meets_the_fixed_target_without_relaxing_it(
    slightly_worse_retained_plan, boundary, action
):
    # Obtain the real fixture's candidate values first, then put the given target
    # exactly on one boundary. The expected action follows the fixed-target contract.
    before = decide(retained_plan=slightly_worse_retained_plan)
    target = (
        before["target_risk"]["best_candidate_mission_end_mean_variance"]
        if boundary == "best"
        else before["decision"]["retained_mission_end_mean_variance"]
    )
    plan = decide(
        retained_plan=slightly_worse_retained_plan,
        settings=PolicySettings(target_mean_variance=target),
    )

    assert plan["decision"]["action"] == action
    assert plan["mission_end_forecast"]["mean_variance"] == target


def test_target_priority_cannot_select_a_route_rejected_by_execution(
    slightly_worse_retained_plan,
):
    plan = decide(
        retained_plan=slightly_worse_retained_plan,
        stepper=hold_only_stepper(),
        settings=PolicySettings(target_mean_variance=0.76410),
    )

    assert plan["selected_candidate_id"] == "nominal-hold"
    assert plan["decision"]["reason"] == "retained_plan_no_longer_executable_from_here"
    assert plan["target_risk"]["status"] == "no_candidate_forecast_reaches_target"
    assert len(accepted(plan)) == 1


def test_configured_target_preserves_the_explicit_retention_ablation(
    slightly_worse_retained_plan,
):
    plan = decide(
        retained_plan=slightly_worse_retained_plan,
        settings=PolicySettings(retain_plan=False, target_mean_variance=0.76410),
    )

    assert plan["decision"]["action"] == "replaced"
    assert plan["decision"]["reason"] == "plan_retention_disabled_by_ablation"
    assert plan["decision"]["retained_candidate_id"] is None
    assert all(row["source"] != "retained" for row in plan["candidates"])
    assert plan["mission_end_forecast"]["mean_variance"] <= 0.76410
