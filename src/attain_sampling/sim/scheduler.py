"""Integer-tick scheduler for the project's four explicit clocks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from attain_sampling.config import ClockConfig


class Event(StrEnum):
    SAMPLE = "sample"
    PLAN = "plan"
    CONTROL = "control"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class EventSchedule:
    """Represent event periods as exact multiples of the control tick."""

    control_s: float
    sample_every: int
    plan_every: int
    log_every: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.control_s, bool)
            or not math.isfinite(self.control_s)
            or self.control_s <= 0.0
        ):
            raise ValueError("control_s must be finite and positive")
        for name, every in (
            ("sample_every", self.sample_every),
            ("plan_every", self.plan_every),
            ("log_every", self.log_every),
        ):
            if isinstance(every, bool) or not isinstance(every, int) or every < 1:
                raise ValueError(f"{name} must be a positive integer")

    @classmethod
    def from_clocks(cls, clocks: ClockConfig) -> EventSchedule:
        clocks.validate()
        return cls(
            control_s=clocks.control_s,
            sample_every=round(clocks.sampling_s / clocks.control_s),
            plan_every=round(clocks.planning_s / clocks.control_s),
            log_every=round(clocks.logging_s / clocks.control_s),
        )

    def events_at(self, tick: int) -> tuple[Event, ...]:
        """Return events in the required sample-plan-control-log order."""

        if tick < 0:
            raise ValueError("tick must be non-negative")
        events: list[Event] = []
        if tick % self.sample_every == 0:
            events.append(Event.SAMPLE)
        if tick % self.plan_every == 0:
            events.append(Event.PLAN)
        events.append(Event.CONTROL)
        if tick % self.log_every == 0:
            events.append(Event.LOG)
        return tuple(events)

    def time_s(self, tick: int) -> float:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        return tick * self.control_s

    def ticks_for_duration(self, duration_s: float) -> int:
        if not math.isfinite(duration_s) or duration_s < 0.0:
            raise ValueError("duration_s must be finite and non-negative")
        return math.ceil(duration_s / self.control_s)
