"""The M4 evidence contract must actually reject tampered decision records."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from attain_sampling.demo.runner import _validate_plans, scenario_config
from attain_sampling.sim.mapping import run_mapping


@pytest.fixture(scope="module")
def managed() -> tuple[Any, dict[str, Any]]:
    config = scenario_config("combined", robots=2, seed=7, duration_s=20.0, controller="qp")
    return config, run_mapping(config, "p")


def mutated(managed: tuple[Any, dict[str, Any]], change) -> tuple[Any, dict[str, Any]]:
    config, run = managed
    clone = copy.deepcopy(run)
    change(clone)
    return config, clone


def test_a_genuine_managed_run_passes(managed):
    config, run = managed
    _validate_plans(config, run)


@pytest.mark.parametrize(
    "field", ["candidates_evaluated", "candidates_rejected", "candidates_not_evaluated"]
)
@pytest.mark.parametrize("value", [999, True])
def test_incorrect_candidate_counters_are_rejected(managed, field, value):
    config, run = mutated(
        managed, lambda item: item["plans"][0]["decision"].__setitem__(field, value)
    )
    with pytest.raises(RuntimeError, match="candidate counters must match"):
        _validate_plans(config, run)


def test_legacy_candidate_counters_do_not_require_rewriting_old_bundles(managed):
    config, run = mutated(managed, lambda item: None)
    for plan in run["plans"]:
        decision = plan["decision"]
        decision.pop("candidates_not_evaluated")
        decision["candidates_evaluated"] = len(plan["candidates"])
        decision["candidates_rejected"] = sum(
            row["status"] != "accepted" for row in plan["candidates"]
        )
    _validate_plans(config, run)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda run: run["plan_events"].pop(), "one decision event per generated plan"),
        (
            lambda run: run["plans"][1].pop("budget"),
            "requires a budget and a decision record",
        ),
        (
            lambda run: run["plans"][1].pop("target_risk"),
            "requires target-risk and mission-end forecast records",
        ),
        (
            lambda run: run["plans"][1]["budget"].__setitem__("remaining_sample_epochs", 99),
            "must match the global clock",
        ),
        (
            lambda run: run["plans"][1]["budget"].__setitem__("mission_end_s", 999.0),
            "must keep the common mission deadline",
        ),
        (
            lambda run: run["plans"][1]["decision"].__setitem__("action", "improvised"),
            "not one of initial/retained/replaced",
        ),
        (
            lambda run: run["plans"][1]["decision"].__setitem__("action", "initial"),
            "only the first P plan may record the initial decision",
        ),
        (
            lambda run: run["plans"][1]["decision"].__setitem__("trigger", "vibes"),
            "not a declared trigger",
        ),
        (
            lambda run: run["plans"][1]["decision"].__setitem__("trigger", "initial"),
            "only the first P plan may use the initial trigger",
        ),
        (
            lambda run: [
                candidate.__setitem__("selected", True)
                for candidate in run["plans"][1]["candidates"]
            ],
            "exactly one recorded candidate",
        ),
        (
            lambda run: run["plans"][1]["mission_end_forecast"].__setitem__(
                "continuation_epochs", 99
            ),
            "must cover exactly the epochs beyond the plan",
        ),
        (
            lambda run: run["plans"][1]["target_risk"].__setitem__("target_mean_variance", 0.123),
            "must report the configured mission target",
        ),
        (
            lambda run: run["plan_events"][1].__setitem__("plan_id", "p-999999-deadbeef"),
            "decision events must align with their plans",
        ),
    ],
)
def test_tampered_decision_records_are_rejected(managed, change, message):
    config, run = mutated(managed, change)
    with pytest.raises(RuntimeError, match=message):
        _validate_plans(config, run)


def test_a_rewound_budget_is_rejected(managed):
    def rewind(run: dict[str, Any]) -> None:
        # Pretend a later replan bought back the epochs it had already spent.
        earlier = run["plans"][0]["budget"]["remaining_sample_epochs"]
        run["plans"][-1]["budget"]["remaining_sample_epochs"] = earlier + 1

    config, run = mutated(managed, rewind)
    with pytest.raises(RuntimeError, match="must match the global clock"):
        _validate_plans(config, run)


def test_a_rejected_candidate_cannot_be_the_selected_one(managed):
    def promote(run: dict[str, Any]) -> None:
        plan = run["plans"][1]
        for candidate in plan["candidates"]:
            candidate["selected"] = False
        plan["candidates"][0].update({"selected": True, "status": "rejected"})
        plan["selected_candidate_id"] = plan["candidates"][0]["candidate_id"]

    config, run = mutated(managed, promote)
    with pytest.raises(RuntimeError, match="must not select a rejected candidate"):
        _validate_plans(config, run)


def test_a_retained_action_must_select_the_retained_candidate(managed):
    def mislabel(run: dict[str, Any]) -> None:
        plan = next(
            candidate for candidate in run["plans"] if candidate["decision"]["action"] == "replaced"
        )
        plan["decision"]["action"] = "retained"

    config, run = mutated(managed, mislabel)
    with pytest.raises(RuntimeError, match="must select the retained candidate"):
        _validate_plans(config, run)


def test_missing_rollout_evidence_is_rejected_when_rollout_is_enabled(managed):
    def erase(run: dict[str, Any]) -> None:
        for candidate in run["plans"][1]["candidates"]:
            if candidate.get("horizon_epochs"):
                candidate["rollout"] = None

    config, run = mutated(managed, erase)
    with pytest.raises(RuntimeError, match="candidate rollout evidence is missing"):
        _validate_plans(config, run)


def test_a_rollout_control_may_not_claim_an_executing_plan(managed):
    def claim(run: dict[str, Any]) -> None:
        event = next(item for item in run["controls"] if item["phase"] == "candidate_rollout")
        event["plan_id"] = run["plans"][0]["plan_id"]

    config, run = mutated(managed, claim)
    with pytest.raises(RuntimeError, match="must not claim an executing plan"):
        _validate_plans(config, run)


def test_a_shortened_horizon_is_only_allowed_for_a_retained_plan(managed):
    def shorten(run: dict[str, Any]) -> None:
        plan = next(
            candidate
            for candidate in run["plans"]
            if candidate["decision"]["action"] == "replaced" and candidate["horizon_steps"] > 1
        )
        plan["sample_times_s"] = plan["sample_times_s"][:-1]
        plan["targets_by_epoch"] = plan["targets_by_epoch"][:-1]
        plan["forecast"] = plan["forecast"][:-1]

    config, run = mutated(managed, shorten)
    with pytest.raises(RuntimeError, match="must follow the remaining physical clock"):
        _validate_plans(config, run)
