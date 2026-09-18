"""M7 confirmation protocol v2: the v1 comparison on new tasks, corrected planner.

The v1 held-out run exposed a defect in the comparator's motion-primitive planner
(decision D057). v2 repeats v1 unchanged, with the corrected planner, on tasks no run
has used. Metrics and analysis are M7's; only the protocol file and its pin differ.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from attain_sampling.eval import m7
from attain_sampling.eval.m7 import (
    BLOCKS,
    analyze,
    enumerate_jobs,
    job_config,
    run_metrics,
    warning_series,
)

__all__ = [
    "BLOCKS",
    "FROZEN_PROTOCOL_SHA256",
    "PROTOCOL_PATH",
    "analyze",
    "enumerate_jobs",
    "job_config",
    "load_protocol",
    "run_metrics",
    "warning_series",
]

PROTOCOL_PATH = m7.PROTOCOL_PATH.with_name("m7_protocol_v2.yaml")
FROZEN_PROTOCOL_SHA256 = "1cbb33f8542faeb8b81200e23cc155c98e1a793692d4b55ef72e4bd9cecd5f88"


def load_protocol(path: Path = PROTOCOL_PATH, *, require_frozen: bool = True) -> dict[str, Any]:
    """Load the M7 v2 protocol; by default refuse anything but the frozen file."""
    return m7.load_protocol(
        path, require_frozen=require_frozen, frozen_sha256=FROZEN_PROTOCOL_SHA256
    )
