"""Remaining-mission budget that outlives any single plan.

Masterplan v2 §9.1 step 2 requires the budget never to be reset by replanning. The
values here are therefore derived only from the global clock and the common mission
deadline, never from a plan's own generation time or horizon. A new plan inherits
whatever time and sensing epochs the mission has left, so shortening a horizon or
replacing a plan cannot buy back budget.

The sensing epochs come from :mod:`attain_sampling.planning.clock`, the same source
the M2 plan horizon reads, so a plan and its budget cannot disagree.

``fleet_travel_budget_m`` is a kinematic upper bound (every robot at maximum speed
for the remaining time). It is not an energy model, and it ignores the controller,
safety constraints and disturbances, so reaching it is not claimed to be executable.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from attain_sampling.attainability.protocol import Budget
from attain_sampling.planning.clock import remaining_sample_times

__all__ = ["MissionBudget", "mission_budget"]


@dataclass(frozen=True, slots=True)
class MissionBudget:
    """What the mission still has, measured against the fixed common deadline."""

    now_s: float
    mission_end_s: float
    sample_period_s: float
    remaining_time_s: float
    remaining_sample_times_s: tuple[float, ...]
    remaining_sample_epochs: int
    elapsed_sample_epochs: int
    total_sample_epochs: int
    robot_count: int
    fleet_travel_budget_m: float

    def as_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["remaining_sample_times_s"] = list(self.remaining_sample_times_s)
        record["scope"] = (
            "global mission clock; kinematic travel bound only, not energy or executability"
        )
        return record

    def as_protocol_budget(self) -> Budget:
        """Narrow view used by the reserved attainability estimator protocol."""
        return Budget(
            remaining_samples=self.remaining_sample_epochs,
            remaining_time_s=self.remaining_time_s,
        )

    def is_successor_of(self, earlier: MissionBudget) -> bool:
        """Check that time and sensing epochs only ever run down, never reset."""
        return (
            math.isclose(self.mission_end_s, earlier.mission_end_s, rel_tol=0, abs_tol=1e-9)
            and math.isclose(self.sample_period_s, earlier.sample_period_s, rel_tol=0, abs_tol=1e-9)
            and self.robot_count == earlier.robot_count
            and self.total_sample_epochs == earlier.total_sample_epochs
            and self.now_s >= earlier.now_s - 1e-9
            and self.remaining_time_s <= earlier.remaining_time_s + 1e-9
            and self.remaining_sample_epochs <= earlier.remaining_sample_epochs
        )


def mission_budget(
    *,
    now_s: float,
    mission_end_s: float,
    sample_period_s: float,
    robot_count: int,
    max_speed: float,
) -> MissionBudget:
    """Compute the remaining budget from the global clock alone.

    ``now_s`` may sit between sensing epochs: an event-triggered replan does not
    gain or lose an epoch by being early. Epoch zero is counted as elapsed because
    every mission takes its first fleet measurement there.
    """
    for name, value in (
        ("now_s", now_s),
        ("mission_end_s", mission_end_s),
        ("sample_period_s", sample_period_s),
        ("max_speed", max_speed),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a real number")
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
    if sample_period_s <= 0 or max_speed <= 0:
        raise ValueError("sample_period_s and max_speed must be positive")
    if isinstance(robot_count, bool) or not isinstance(robot_count, int) or robot_count < 1:
        raise ValueError("robot_count must be a positive integer")
    now, end, period = float(now_s), float(mission_end_s), float(sample_period_s)
    if now < 0 or end < now:
        raise ValueError("mission_end_s must not precede a non-negative now_s")
    remaining = remaining_sample_times(now, end, period)
    # Epoch zero is a real fleet measurement, so it belongs to the elapsed count.
    total = len(remaining_sample_times(0.0, end, period)) + 1
    remaining_time = max(0.0, end - now)
    travel = robot_count * float(max_speed) * remaining_time
    if not math.isfinite(travel):
        raise ValueError("fleet travel budget must be finite")
    return MissionBudget(
        now_s=now,
        mission_end_s=end,
        sample_period_s=period,
        remaining_time_s=remaining_time,
        remaining_sample_times_s=tuple(remaining),
        remaining_sample_epochs=len(remaining),
        elapsed_sample_epochs=total - len(remaining),
        total_sample_epochs=total,
        robot_count=robot_count,
        fleet_travel_budget_m=travel,
    )
