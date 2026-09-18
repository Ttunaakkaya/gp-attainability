"""M4 inside the simulator: decisions, triggers, budget provenance and ablations."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from attain_sampling.demo.runner import scenario_config
from attain_sampling.sim.mapping import run_mapping


def run(**overrides: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "scenario": "combined",
        "robots": 2,
        "seed": 7,
        "duration_s": 20.0,
        "controller": "qp",
    }
    options.update(overrides)
    scenario = options.pop("scenario")
    return run_mapping(scenario_config(scenario, **options), "p")


def periodic_epochs(duration: float = 20.0, period: float = 5.0) -> list[float]:
    return [index * period for index in range(round(duration / period))]


def test_a_managed_mission_completes_and_decides_at_every_periodic_epoch():
    result = run()
    assert result["status"] == "completed"
    generated = [plan["generated_at_s"] for plan in result["plans"]]
    for epoch in periodic_epochs():
        assert any(math.isclose(epoch, value, abs_tol=1e-9) for value in generated)
    assert generated == sorted(generated)
    assert len(result["plan_events"]) == len(result["plans"])


def test_decision_events_mirror_their_plans():
    result = run()
    for plan, event in zip(result["plans"], result["plan_events"], strict=True):
        assert event["plan_id"] == plan["plan_id"]
        assert event["action"] == plan["decision"]["action"]
        assert event["trigger"] == plan["decision"]["trigger"]
        assert event["time_s"] == pytest.approx(plan["generated_at_s"])


def test_the_remaining_budget_only_ever_runs_down():
    result = run()
    remaining = [plan["budget"]["remaining_sample_epochs"] for plan in result["plans"]]
    assert remaining == sorted(remaining, reverse=True)
    for plan in result["plans"]:
        assert plan["budget"]["mission_end_s"] == pytest.approx(20.0)
        assert plan["budget"]["now_s"] == pytest.approx(plan["generated_at_s"])
        covered = plan["horizon_steps"] + plan["mission_end_forecast"]["continuation_epochs"]
        assert covered == plan["budget"]["remaining_sample_epochs"]


def test_only_the_first_decision_is_initial_and_later_ones_name_a_real_trigger():
    result = run()
    events = result["plan_events"]
    assert events[0]["trigger"] == "initial"
    assert events[0]["action"] == "initial"
    assert all(event["trigger"] != "initial" for event in events[1:])
    assert all(event["action"] in {"retained", "replaced"} for event in events[1:])


def test_a_sensitive_deviation_threshold_adds_event_triggered_decisions():
    quiet = run(p_deviation_trigger_m=1000.0, p_intervention_trigger_mps=1000.0)
    sensitive = run(p_deviation_trigger_m=0.05, p_intervention_trigger_mps=1000.0)
    assert len(quiet["plans"]) == len(periodic_epochs())
    assert len(sensitive["plans"]) > len(quiet["plans"])
    extra = [
        event for event in sensitive["plan_events"] if event["trigger"] == "execution_deviation"
    ]
    assert extra
    assert all(event["deviation_m"] > 0.05 for event in extra)
    # Event-triggered plans land inside an interval, not on the sensing clock.
    assert any(
        not math.isclose(event["time_s"] % 5.0, 0.0, abs_tol=1e-9)
        for event in sensitive["plan_events"]
    )


def test_event_trigger_ablation_keeps_exactly_the_periodic_decisions():
    result = run(p_event_triggers=False, p_deviation_trigger_m=0.01)
    assert [plan["generated_at_s"] for plan in result["plans"]] == pytest.approx(periodic_epochs())


def test_rollout_ablation_removes_rollout_work_but_still_decides():
    rolled = run()
    geometric = run(p_controller_rollout=False)
    assert rolled["summary"]["rollout_control_calls"] > 0
    assert geometric["summary"]["rollout_control_calls"] == 0
    assert geometric["status"] == "completed"
    assert all(
        plan["targets_by_epoch"] == plan["predicted_sample_sites"] for plan in geometric["plans"]
    )


def test_retention_ablation_never_records_a_retained_decision():
    result = run(p_retain_plan=False)
    assert all(event["action"] != "retained" for event in result["plan_events"])


def test_retention_is_actually_exercised_with_the_default_settings():
    result = run(duration_s=40.0)
    actions = {event["action"] for event in result["plan_events"]}
    assert "retained" in actions


def test_candidate_rollout_controls_are_a_distinct_phase_without_an_executing_plan():
    result = run()
    rolled = [event for event in result["controls"] if event["phase"] == "candidate_rollout"]
    executed = [event for event in result["controls"] if event["phase"] == "execution"]
    assert rolled and executed
    assert all(event["plan_id"] is None for event in rolled)
    assert all(event["plan_id"] is not None for event in executed)
    assert result["summary"]["rollout_control_calls"] == len(rolled)


def test_a_configured_mission_target_is_reported_on_every_decision():
    result = run(target_mean_variance=0.02)
    for plan in result["plans"]:
        risk = plan["target_risk"]
        assert risk["target_mean_variance"] == pytest.approx(0.02)
        assert risk["status"] in {
            "forecast_attainable_in_candidate_set",
            "no_candidate_forecast_reaches_target",
        }
        assert any("not impossibility" in limit for limit in risk["claim_limits"])


def test_planning_cost_is_recorded_separately_from_applied_control():
    result = run()
    summary = result["summary"]
    assert summary["control_rollout_s"] > 0
    assert summary["control_rollout_s"] <= summary["planning_s"]
    assert summary["rollout_qp_failures"] == 0
    assert summary["qp_solves"] == len(
        [event for event in result["controls"] if event["phase"] == "execution"]
    )


def test_managed_planning_rejects_a_turn_limited_vehicle():
    with pytest.raises(ValueError):
        run_mapping(scenario_config("combined", robots=2, model="usv"), "p")


def test_rejected_qp_candidates_do_not_abort_a_mission_with_an_executable_hold():
    # Real solver regression: some moving rollouts hit the low iteration limit,
    # while the hold and applied commands remain acceptable. No solver mocks.
    result = run(scenario="nominal", duration_s=10.0, qp_max_iter=25)
    assert result["status"] == "completed"
    assert result["summary"]["rollout_qp_failures"] > 0
    assert result["summary"]["qp_failures"] == 0
    assert result["plans"][0]["selected_candidate_id"] == "nominal-hold"
    assert any(row["status"] == "rejected" for row in result["plans"][0]["candidates"])
    json.dumps(result, allow_nan=False)
