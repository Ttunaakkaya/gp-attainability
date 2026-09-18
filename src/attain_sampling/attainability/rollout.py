"""Nominal controller rollout of a candidate sampling plan.

M2/B3 scored candidates on the geometric straight-line schedule: it assumed each
robot simply arrives at its planned cell by the sampling deadline. The actual
low-level controller may refuse that command, be pulled off it by a separation
constraint, or arrive somewhere else. This module replays a candidate through the
*same* controller the mission will execute, and reports where the fleet would
actually be when each measurement is taken.

The rollout is **nominal**: it uses no future disturbance, no future dropout and no
hidden ground truth. It therefore predicts execution under the controller, not under
the weather. A feasible rollout is an executable candidate, never a robust guarantee
for the whole admitted deviation set (masterplan v2 §9.1).

The stepper is injected so this package never imports the simulator, and a rejected
command is reported through :class:`StepOutcome`, never through a hidden fallback:
an infeasible candidate leaves the candidate set, it does not silently become a
shorter plan, and it does not prove the mission target is unreachable.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from attain_sampling.gp.protocol import FloatArray

__all__ = ["CandidateRollout", "NominalStepper", "StepOutcome", "rollout_plan"]


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """One nominal control interval, including an explicit rejection."""

    accepted: bool
    positions: FloatArray
    headings: FloatArray
    intervention: bool
    min_separation: float
    failure_reason: str | None = None


class NominalStepper(Protocol):
    """Advance the fleet one control interval with no disturbance and no sensing."""

    def __call__(
        self,
        positions: FloatArray,
        headings: FloatArray,
        targets: FloatArray,
        *,
        tick: int,
        tracking_time_s: float,
    ) -> StepOutcome: ...


@dataclass(frozen=True, slots=True)
class CandidateRollout:
    """Where the controller would actually sample, and whether it can get there."""

    feasible: bool
    failure_reason: str | None
    failed_epoch: int | None
    sample_positions: FloatArray
    completed_epochs: int
    final_positions: FloatArray
    final_headings: FloatArray
    interventions: int
    # No accepted control interval means no measured separation, not a NaN or zero.
    min_separation: float | None
    control_calls: int
    wall_s: float
    max_target_error_m: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe summary; the dense path stays out of the plan record."""
        return {
            "feasible": self.feasible,
            "failure_reason": self.failure_reason,
            "failed_epoch": self.failed_epoch,
            "completed_epochs": self.completed_epochs,
            "sample_positions": self.sample_positions.tolist(),
            "final_positions": self.final_positions.tolist(),
            "interventions": self.interventions,
            "min_separation_m": self.min_separation,
            "max_target_error_m": self.max_target_error_m,
            "control_calls": self.control_calls,
            "wall_s": self.wall_s,
            "scope": (
                "nominal controller rollout: no future disturbance, dropout or ground truth; "
                "executable candidate, not a robust guarantee"
            ),
        }


def rollout_plan(
    stepper: NominalStepper,
    positions: FloatArray,
    headings: FloatArray,
    targets_by_epoch: FloatArray,
    *,
    start_tick: int,
    epoch_ticks: Sequence[int],
    dt: float,
) -> CandidateRollout:
    """Replay a timed candidate through the controller and return its sample sites.

    ``epoch_ticks`` are absolute control ticks of the candidate's sampling epochs,
    strictly increasing and strictly after ``start_tick``. Each interval requests
    arrival at its own deadline, matching how the mission executes a plan, so a
    rollout is not a shortcut geometry with a different speed profile.
    """
    started = time.perf_counter()
    starts = np.asarray(positions, dtype=np.float64)
    orientation = np.asarray(headings, dtype=np.float64)
    targets = np.asarray(targets_by_epoch, dtype=np.float64)
    if starts.ndim != 2 or starts.shape[1] != 2 or not len(starts):
        raise ValueError("positions must have nonempty shape (robots, 2)")
    if orientation.shape != (len(starts),):
        raise ValueError("headings must supply one angle per robot")
    if targets.ndim != 3 or targets.shape[1:] != starts.shape:
        raise ValueError("targets_by_epoch must have shape (epochs, robots, 2)")
    if len(targets) != len(epoch_ticks):
        raise ValueError("targets_by_epoch and epoch_ticks must agree in length")
    if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be finite and positive")
    if isinstance(start_tick, bool) or not isinstance(start_tick, int) or start_tick < 0:
        raise ValueError("start_tick must be a non-negative integer")
    previous = start_tick
    for epoch_tick in epoch_ticks:
        if isinstance(epoch_tick, bool) or not isinstance(epoch_tick, (int, np.integer)):
            raise ValueError("epoch_ticks must contain integers")
        if int(epoch_tick) <= previous:
            raise ValueError("epoch_ticks must be strictly increasing after start_tick")
        previous = int(epoch_tick)

    current = starts.copy()
    current_headings = orientation.copy()
    sites: list[FloatArray] = []
    interventions = 0
    control_calls = 0
    minimum = math.inf
    target_error = 0.0
    tick = start_tick
    failure_reason: str | None = None
    failed_epoch: int | None = None
    for epoch, epoch_tick in enumerate(epoch_ticks):
        steps = int(epoch_tick) - tick
        for offset in range(steps):
            # Ask for arrival at this epoch's own deadline, never earlier.
            remaining_s = (steps - offset) * float(dt)
            outcome = stepper(
                current,
                current_headings,
                targets[epoch],
                tick=tick + offset + 1,
                tracking_time_s=remaining_s,
            )
            control_calls += 1
            if not outcome.accepted:
                failure_reason = outcome.failure_reason or "controller_rejected_candidate_command"
                failed_epoch = epoch
                break
            current = np.asarray(outcome.positions, dtype=np.float64)
            current_headings = np.asarray(outcome.headings, dtype=np.float64)
            interventions += int(outcome.intervention)
            minimum = min(minimum, float(outcome.min_separation))
        if failure_reason is not None:
            break
        sites.append(current.copy())
        target_error = max(
            target_error, float(np.max(np.linalg.norm(current - targets[epoch], axis=1)))
        )
        tick = int(epoch_tick)
    completed = len(sites)
    sample_positions = (
        np.asarray(sites, dtype=np.float64)
        if sites
        else np.empty((0, len(starts), 2), dtype=np.float64)
    )
    return CandidateRollout(
        feasible=failure_reason is None,
        failure_reason=failure_reason,
        failed_epoch=failed_epoch,
        sample_positions=sample_positions,
        completed_epochs=completed,
        final_positions=current,
        final_headings=current_headings,
        interventions=interventions,
        min_separation=minimum if math.isfinite(minimum) else None,
        control_calls=control_calls,
        wall_s=time.perf_counter() - started,
        max_target_error_m=target_error,
    )
