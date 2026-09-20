"""M4 execution-aware plan management: the proposed policy P.

B3 replans periodically from the real posterior and scores each candidate on the
geometric assumption that a robot simply arrives at its planned cell. P adds the
three things masterplan v2 §9 asks for, and nothing else:

1. **Controller rollout.** Each candidate is replayed through the same low-level
   controller the mission executes, and scored at the positions the fleet would
   actually reach, not at the cells it was aimed at.
2. **Retained plan.** The still-future remainder of the plan already in force is
   re-checked from the *current* actual state and competes as a candidate. It is
   abandoned only when another candidate improves the mission-end forecast by more
   than an explicit margin, so the fleet does not oscillate between equal plans.
   A configured fixed target takes priority: a retained miss cannot displace an
   already-evaluated candidate whose deadline forecast meets that target.
3. **Remaining-mission budget.** Every candidate is extended to the common deadline
   by an explicitly defined hold continuation, so all candidates are scored over the
   *same* remaining sensing epochs. A short horizon is never presented as a
   mission-end value.

The hold continuation is what makes the mission-end number honest: it belongs to a
plan the fleet can actually execute, so it is an **upper candidate** for the best
attainable value, never a floor and never a certificate. Consequently a candidate
set that misses the mission target proves only that *this bounded search* missed it.

With SOGP the forecast conditions the current approximate posterior and does not
model future dictionary pruning, so it carries no bound property at all.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from attain_sampling.attainability.budget import MissionBudget
from attain_sampling.attainability.rollout import CandidateRollout, NominalStepper, rollout_plan
from attain_sampling.gp.protocol import CovarianceBelief, FloatArray

__all__ = ["PolicySettings", "manage_plan"]

_GEOMETRY_TOLERANCE = 1e-7
TRIGGERS = (
    "initial",
    "periodic_sampling_epoch",
    "missed_measurement",
    "execution_deviation",
    "control_intervention",
)


@dataclass(frozen=True, slots=True)
class PolicySettings:
    """Explicit development settings; the three flags are the mandatory ablations."""

    controller_rollout: bool = True
    retain_plan: bool = True
    event_triggers: bool = True
    deviation_trigger_m: float = 1.5
    intervention_trigger_mps: float = 0.25
    switch_margin: float = 0.01
    max_rollout_candidates: int = 6
    target_mean_variance: float | None = None

    def __post_init__(self) -> None:
        for name in ("controller_rollout", "retain_plan", "event_triggers"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        cap = self.max_rollout_candidates
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= 64:
            raise ValueError("max_rollout_candidates must be an integer in [1, 64]")
        for name in ("deviation_trigger_m", "intervention_trigger_mps", "switch_margin"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, float(value))
        target = self.target_mean_variance
        if target is not None and (
            isinstance(target, bool)
            or not isinstance(target, (int, float))
            or not math.isfinite(float(target))
            or float(target) <= 0
        ):
            raise ValueError("target_mean_variance must be None or finite and positive")
        if target is not None:
            object.__setattr__(self, "target_mean_variance", float(target))


def _hold_feasible(
    positions: FloatArray,
    domain: tuple[float, float],
    min_separation: float,
    scope: str = "static_hold_geometric_check_holonomic_zero_velocity",
) -> dict[str, Any]:
    """Check the continuation the mission-end forecast actually relies on.

    Holding applies zero velocity, so for the holonomic model the static geometry
    *is* the complete check: the domain and separation constraints are unchanged and
    the speed bound is trivially met. The M7 curvature USV may also stop; its
    controller keeps a private loiter circle for every robot at every executed step,
    and ``scope`` records which vehicle the check describes. This is not a
    controller rollout.
    """
    bounds = np.asarray(domain, dtype=np.float64)
    inside = float(max(0.0, -float(np.min(positions)), float(np.max(positions - bounds))))
    minimum = math.inf
    for first in range(len(positions)):
        for second in range(first + 1, len(positions)):
            minimum = min(minimum, float(np.linalg.norm(positions[first] - positions[second])))
    shortfall = 0.0 if math.isinf(minimum) else max(0.0, min_separation - minimum)
    return {
        "accepted": bool(max(inside, shortfall) <= _GEOMETRY_TOLERANCE),
        "policy": "hold_final_positions_for_every_remaining_epoch",
        "scope": scope,
        "max_bounds_violation_m": inside,
        "min_pair_distance_m": None if math.isinf(minimum) else minimum,
        "max_separation_violation_m": shortfall,
    }


def _prefix_forecast(
    gp: CovarianceBelief, query: FloatArray, sites: FloatArray, times: list[float], now: float
) -> list[dict[str, Any]]:
    current = gp.predict(query, variance="latent").variance
    forecast = [
        {
            "time_s": now,
            "mean_variance": float(np.mean(current)),
            "max_variance": float(np.max(current)),
        }
    ]
    for epoch, sample_time in enumerate(times):
        variance = gp.fantasy_variance(query, sites[: epoch + 1].reshape(-1, 2))
        forecast.append(
            {
                "time_s": sample_time,
                "mean_variance": float(np.mean(variance)),
                "max_variance": float(np.max(variance)),
            }
        )
    return forecast


def _retained_remainder(
    retained_plan: dict[str, Any] | None, times: list[float]
) -> FloatArray | None:
    """Take the still-future part of the plan in force, aligned to the new epochs.

    A retained candidate is only offered for epochs both plans share. The remainder
    is *not* assumed still valid: the caller rolls it out from the current actual
    state exactly like every other candidate.
    """
    if retained_plan is None or not times:
        return None
    previous_times = retained_plan.get("sample_times_s") or []
    previous_targets = retained_plan.get("targets_by_epoch") or []
    if len(previous_times) != len(previous_targets):
        return None
    aligned: list[Any] = []
    for sample_time in times:
        match = next(
            (
                targets
                for previous, targets in zip(previous_times, previous_targets, strict=True)
                if math.isclose(previous, sample_time, rel_tol=0, abs_tol=1e-9)
            ),
            None,
        )
        if match is None:
            break
        aligned.append(match)
    if not aligned:
        return None
    return np.asarray(aligned, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class _PlanDecision:
    """Scalar selection evidence; the input candidate records remain caller-owned."""

    selected_index: int
    action: str
    reason: str
    retained_id: str | None
    retained_mean: float | None
    selected_mean: float
    best_mean: float
    switch_margin: float
    target_margin: float | None
    target_status: str


def _decide_plan(
    evaluated: list[dict[str, Any]],
    *,
    current_mean_variance: float,
    had_plan: bool,
    retained_id: str | None,
    settings: PolicySettings,
) -> _PlanDecision:
    """Rank the existing candidates and apply retention without mutating evidence.

    The fixed target takes priority over hysteresis only for a forecast crossing.
    Candidate-set risk remains distinct from the selected route's forecast.
    """
    accepted = [candidate for candidate in evaluated if candidate["status"] == "accepted"]
    if not accepted:
        raise FloatingPointError(
            "no candidate survived execution-aware evaluation at this decision point"
        )
    # Equal remaining epochs for every candidate, so mission-end value is comparable.
    best = min(
        accepted,
        key=lambda candidate: (
            candidate["mission_end_mean_variance"],
            candidate["travel_m"],
            candidate["candidate_id"],
        ),
    )
    retained = next(
        (candidate for candidate in accepted if candidate["candidate_id"] == retained_id), None
    )
    margin = settings.switch_margin * current_mean_variance
    chosen = best
    action = "initial" if not had_plan else "replaced"
    # The reason must say what actually happened, so an ablation that never compared
    # against the plan in force cannot report that a candidate beat it.
    if not had_plan:
        reason = "no_plan_in_force"
    elif not settings.retain_plan:
        reason = "plan_retention_disabled_by_ablation"
    elif retained_id is None:
        reason = "retained_plan_shares_no_remaining_epoch"
    elif retained is None:
        reason = "retained_plan_no_longer_executable_from_here"
    else:
        reason = "candidate_improves_mission_forecast_beyond_switch_margin"
    if retained is not None:
        gain = retained["mission_end_mean_variance"] - best["mission_end_mean_variance"]
        target = settings.target_mean_variance
        if (
            target is not None
            and best["mission_end_mean_variance"] <= target < retained["mission_end_mean_variance"]
        ):
            reason = "candidate_reaches_target_while_retained_plan_misses"
        elif gain <= margin:
            chosen, action = retained, "retained"
            reason = "retained_plan_within_switch_margin_of_the_best_candidate"
    target = settings.target_mean_variance
    best_mean = float(best["mission_end_mean_variance"])
    if target is None:
        target_status = "no_mission_target_configured"
    elif best_mean <= target:
        target_status = "forecast_attainable_in_candidate_set"
    else:
        target_status = "no_candidate_forecast_reaches_target"
    return _PlanDecision(
        selected_index=next(index for index, row in enumerate(evaluated) if row is chosen),
        action=action,
        reason=reason,
        retained_id=retained_id if retained is not None else None,
        retained_mean=(
            float(retained["mission_end_mean_variance"]) if retained is not None else None
        ),
        selected_mean=float(chosen["mission_end_mean_variance"]),
        best_mean=best_mean,
        switch_margin=margin,
        target_margin=None if target is None else target - best_mean,
        target_status=target_status,
    )


def manage_plan(
    *,
    gp: CovarianceBelief,
    query: FloatArray,
    positions: FloatArray,
    headings: FloatArray,
    budget: MissionBudget,
    dp_plan: dict[str, Any],
    retained_plan: dict[str, Any] | None,
    stepper: NominalStepper,
    start_tick: int,
    dt: float,
    domain: tuple[float, float],
    min_separation: float,
    trigger: str,
    plan_version: int,
    settings: PolicySettings,
    hold_scope: str = "static_hold_geometric_check_holonomic_zero_velocity",
) -> dict[str, Any]:
    """Choose, or deliberately keep, the joint sampling plan for the next interval.

    ``dp_plan`` supplies the bounded candidate routes; this function re-scores them
    under execution and budget. It never mutates the belief, the positions or the
    retained plan, and it never invents a route the search did not produce.
    """
    started = time.perf_counter()
    if not isinstance(settings, PolicySettings):
        raise ValueError("settings must be PolicySettings")
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}")
    starts = np.asarray(positions, dtype=np.float64)
    orientation = np.asarray(headings, dtype=np.float64)
    queries = np.asarray(query, dtype=np.float64)
    times = [float(value) for value in dp_plan.get("sample_times_s") or []]
    remaining = list(budget.remaining_sample_times_s)
    if times != remaining[: len(times)]:
        raise ValueError("candidate horizon must be a prefix of the remaining mission epochs")
    epoch_ticks = [round(value / dt) for value in times]
    # Continuation length is per candidate: a retained remainder covers fewer epochs
    # than a fresh route, and the hold has to make up exactly that difference so every
    # candidate is still scored over the same remaining sensing budget.
    total_remaining = len(remaining)

    searched: list[tuple[str, str, FloatArray, float]] = []
    for candidate in dp_plan.get("candidates") or []:
        if candidate.get("status") != "accepted":
            continue
        targets = np.asarray(candidate["targets_by_epoch"], dtype=np.float64)
        searched.append(
            (
                str(candidate["candidate_id"]),
                str(candidate["generator"]),
                targets,
                float(candidate.get("terminal_mean_variance", math.inf)),
            )
        )
    if not any(candidate_id == "nominal-hold" for candidate_id, _, _, _ in searched):
        # Either no sampling epoch remains, or the bounded search returned nothing.
        # Holding is genuinely executable, so it is always available as a candidate;
        # that is not a claim that holding is good or that no route exists.
        searched.append(
            ("nominal-hold", "nominal_hold", np.repeat(starts[None], len(times), axis=0), math.inf)
        )
    # Rolling every candidate through the controller dominates the decision cost, so
    # the rollout set is explicitly bounded. Candidates are pre-ranked by the cheap
    # geometric score the search already produced; the always-executable hold and the
    # retained plan are never dropped. Skipped candidates are recorded, not hidden,
    # and a bounded search is not a statement about the routes it never scored.
    searched.sort(key=lambda item: (item[3], item[0]))
    forced = {"nominal-hold"}
    keep: list[tuple[str, str, FloatArray, float]] = []
    skipped: list[tuple[str, str]] = []
    for candidate in searched:
        if len(keep) < settings.max_rollout_candidates or candidate[0] in forced:
            keep.append(candidate)
        else:
            skipped.append((candidate[0], candidate[1]))
    sources: list[tuple[str, str, FloatArray]] = [
        (candidate_id, generator, targets) for candidate_id, generator, targets, _ in keep
    ]
    retained_targets = _retained_remainder(retained_plan, times) if settings.retain_plan else None
    retained_id: str | None = None
    if retained_targets is not None:
        retained_id = "retained-plan"
        sources.insert(0, (retained_id, "retained_plan_remainder", retained_targets))

    evaluated: list[dict[str, Any]] = [
        {
            "candidate_id": candidate_id,
            "generator": generator,
            "source": "search",
            "status": "not_evaluated",
            "rejection_reason": "bounded_rollout_candidate_cap",
            "selected": False,
            "claim_limit": "not scored here; no claim about this route",
        }
        for candidate_id, generator in skipped
    ]
    for candidate_id, generator, targets in sources:
        candidate_started = time.perf_counter()
        covered = len(targets)
        rollout: CandidateRollout | None = None
        if settings.controller_rollout and covered:
            rollout = rollout_plan(
                stepper,
                starts,
                orientation,
                targets,
                start_tick=start_tick,
                epoch_ticks=epoch_ticks[:covered],
                dt=dt,
            )
            sites = rollout.sample_positions
            reached = rollout.final_positions
        else:
            sites = targets.copy()
            reached = targets[-1].copy() if covered else starts.copy()
        feasible = rollout is None or rollout.feasible
        record: dict[str, Any] = {
            "candidate_id": candidate_id,
            "generator": generator,
            "source": "retained" if candidate_id == retained_id else "search",
            "horizon_epochs": covered,
            "sample_sites_scope": (
                "controller_rollout_reached_positions"
                if settings.controller_rollout
                else "geometric_targets_assumed_reached"
            ),
            "rollout": rollout.as_dict() if rollout is not None else None,
            "selected": False,
        }
        if not feasible:
            record.update(
                {
                    "status": "rejected",
                    "rejection_reason": "controller_rollout_rejected_this_candidate",
                    "claim_limit": "candidate not executable here; not a mission impossibility",
                    "evaluation_wall_s": time.perf_counter() - candidate_started,
                }
            )
            evaluated.append(record)
            continue
        continuation = _hold_feasible(reached, domain, min_separation, hold_scope)
        if not continuation["accepted"]:
            record.update(
                {
                    "status": "rejected",
                    "rejection_reason": "hold_continuation_failed_its_geometric_check",
                    "continuation": continuation,
                    "claim_limit": "candidate not executable here; not a mission impossibility",
                    "evaluation_wall_s": time.perf_counter() - candidate_started,
                }
            )
            evaluated.append(record)
            continue
        continuation_epochs = total_remaining - covered
        if continuation_epochs < 0:
            raise ValueError("a candidate cannot cover more epochs than the mission has left")
        held = np.repeat(reached[None], continuation_epochs, axis=0)
        mission_sites = (
            np.concatenate((sites, held)) if len(sites) else held.copy() if len(held) else sites
        )
        horizon_variance = (
            gp.fantasy_variance(queries, sites.reshape(-1, 2))
            if len(sites)
            else gp.predict(queries, variance="latent").variance
        )
        mission_variance = (
            gp.fantasy_variance(queries, mission_sites.reshape(-1, 2))
            if len(mission_sites)
            else horizon_variance
        )
        movements = np.diff(np.concatenate((starts[None], sites)), axis=0) if len(sites) else None
        record.update(
            {
                "status": "accepted",
                "rejection_reason": None,
                "continuation": continuation,
                "continuation_epochs": continuation_epochs,
                "scored_sample_epochs": len(mission_sites),
                "targets_by_epoch": targets.tolist(),
                "predicted_sample_sites": sites.tolist(),
                "horizon_mean_variance": float(np.mean(horizon_variance)),
                "horizon_max_variance": float(np.max(horizon_variance)),
                "mission_end_mean_variance": float(np.mean(mission_variance)),
                "mission_end_max_variance": float(np.max(mission_variance)),
                "travel_m": (
                    float(np.sum(np.linalg.norm(movements, axis=2)))
                    if movements is not None
                    else 0.0
                ),
                "evaluation_wall_s": time.perf_counter() - candidate_started,
            }
        )
        evaluated.append(record)

    selection = _decide_plan(
        evaluated,
        current_mean_variance=float(np.mean(gp.predict(queries, variance="latent").variance)),
        had_plan=retained_plan is not None,
        retained_id=retained_id,
        settings=settings,
    )
    chosen = evaluated[selection.selected_index]
    chosen["selected"] = True
    # Execution steers toward the commanded cells; the forecast is computed at the
    # positions the rollout says the controller would actually reach.
    selected_targets = np.asarray(chosen["targets_by_epoch"], dtype=np.float64)
    selected_sites = np.asarray(chosen["predicted_sample_sites"], dtype=np.float64)
    selected_times = times[: chosen["horizon_epochs"]]
    forecast = _prefix_forecast(gp, queries, selected_sites, selected_times, budget.now_s)

    target = settings.target_mean_variance
    mission_end_mean = selection.selected_mean
    target_risk = {
        "target_mean_variance": target,
        "selected_mission_end_mean_variance": mission_end_mean,
        "best_candidate_mission_end_mean_variance": selection.best_mean,
        "margin": selection.target_margin,
        "status": selection.target_status,
        "remaining_time_s": budget.remaining_time_s,
        "remaining_sample_epochs": budget.remaining_sample_epochs,
        "forecast_covers_mission_end": True,
        "continuation": chosen["continuation"]["policy"],
        "claim_limits": [
            "upper candidate from an executable plan, not an attainability floor",
            "a missed target here reflects this bounded candidate set, not impossibility",
            "approximate SOGP forecasts carry no bound property",
        ],
    }

    identity = {
        "plan_version": plan_version,
        "generated_at_s": budget.now_s,
        "mission_end_s": budget.mission_end_s,
        "belief_observation_count": gp.observation_count,
        "starts": starts.tolist(),
        "targets_by_epoch": selected_targets.tolist(),
        "predicted_sample_sites": selected_sites.tolist(),
        "sample_times_s": selected_times,
        "forecast": forecast,
        "settings": asdict(settings),
        "gp_backend": gp.backend_name,
        "forecast_scope": gp.forecast_scope,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()[:12]
    result = {
        **identity,
        "plan_id": f"p-{plan_version:06d}-{digest}",
        "status": "planned" if selected_times else "no_remaining_samples",
        "horizon_end_s": selected_times[-1] if selected_times else budget.now_s,
        "horizon_steps": len(selected_times),
        "selected_candidate_id": chosen["candidate_id"],
        "candidates": evaluated,
        "nominal_checks": dp_plan.get("nominal_checks"),
        "budget": budget.as_dict(),
        "decision": {
            "action": selection.action,
            "trigger": trigger,
            "reason": selection.reason,
            "retained_candidate_id": selection.retained_id,
            "retained_mission_end_mean_variance": selection.retained_mean,
            "selected_mission_end_mean_variance": mission_end_mean,
            "expected_gain": (
                selection.retained_mean - mission_end_mean
                if selection.retained_mean is not None
                else None
            ),
            "switch_margin_variance": selection.switch_margin,
            # Capped routes were never evaluated; they are not failed rollouts.
            "candidates_evaluated": sum(
                candidate["status"] in {"accepted", "rejected"} for candidate in evaluated
            ),
            "candidates_rejected": sum(
                candidate["status"] == "rejected" for candidate in evaluated
            ),
            "candidates_not_evaluated": sum(
                candidate["status"] == "not_evaluated" for candidate in evaluated
            ),
        },
        "mission_end_forecast": {
            "time_s": budget.mission_end_s,
            "mean_variance": mission_end_mean,
            "max_variance": chosen["mission_end_max_variance"],
            "continuation_epochs": chosen["continuation_epochs"],
            "scope": (
                "selected plan plus its executable hold continuation over every remaining epoch"
            ),
        },
        "target_risk": target_risk,
        "planning_scope": (
            "M4 execution-aware management: bounded candidate set re-scored under "
            + (
                "controller rollout"
                if settings.controller_rollout
                else "geometric arrival (rollout ablation)"
            )
            + " with a hold continuation to the common deadline"
        ),
        "forecast_scope": gp.forecast_scope,
        "gp_backend": gp.backend_name,
        "rollout_scope": (
            "nominal: no future disturbance, dropout or ground truth"
            if settings.controller_rollout
            else "disabled: geometric targets assumed reached"
        ),
        "candidate_selection": (
            "mission_end_mean_latent_variance_over_equal_remaining_epochs_then_travel; "
            "retained plan kept within an explicit switch margin"
        ),
        "claim_limits": [
            "not_a_full_belief_mdp_or_global_route_optimum",
            "executable_upper_candidate_not_an_attainability_floor",
            "no_task_impossibility_or_recovery_certificate",
            "nominal_rollout_is_not_a_robust_guarantee_over_admitted_deviations",
        ],
        "planning_wall_s": time.perf_counter() - started,
    }
    json.dumps(result, allow_nan=False)
    return result
