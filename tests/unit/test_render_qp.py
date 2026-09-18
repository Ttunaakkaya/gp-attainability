"""M1 replay honesty: preserve partial failures and legacy completed artifacts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.figure import Figure
from matplotlib.text import Text

from attain_sampling.demo import render


def _comparison(*, all_failed: bool = False, failure_time: float = 1.0) -> dict[str, Any]:
    config = {
        "seed": 7,
        "domain": [2.0, 2.0],
        "duration_s": 90.0,
        "signal_variance": 1.0,
        "robot_count": 2,
        "model": "holonomic",
        "controller": "qp",
    }
    runs = []
    for index, method in enumerate(("sweep", "greedy", "adaptive")):
        failed = all_failed or index == 0
        end = failure_time if failed else 2.0
        frames = []
        for moment in sorted({0.0, end}):
            frames.append(
                {
                    "time_s": moment,
                    "positions": [[0.0, 0.0], [2.0, 2.0]],
                    "mean": [[0.0, 0.2], [0.1, 0.0]],
                    "std": [[0.5, 0.5], [0.5, 0.5]],
                    "error": [[0.0, -0.1], [0.1, 0.0]],
                    "rmse": 0.07,
                    "mean_variance": 0.25,
                    "planned_mean_variance": None if failed else 0.25,
                    "path_length": 0.0,
                    "samples_received": 0,
                }
            )
        run = {
            "method": method,
            "config": config,
            "field": {"truth": [[0.0, 0.3], [0.0, 0.0]]},
            "frames": frames,
            "motion": [{"time_s": f["time_s"], "positions": f["positions"]} for f in frames],
        }
        if failed:
            run.update(status="failed", failure={"reason": "solver rejected"})
        elif index == 2:
            run.update(status="completed", failure=None)
        # Index 1 intentionally has no M1 status/failure/controls/summary fields.
        runs.append(run)
    return {"schema_version": 1, "scenario": "nominal", "config": config, "runs": runs}


def test_partial_replay_uses_actual_records_not_requested_duration() -> None:
    comparison = _comparison()
    failed, legacy, completed = comparison["runs"]
    before = copy.deepcopy(comparison)
    assert render._recorded_end(failed) == 1.0
    assert "FAILED @ 1 s" in render._run_label(failed)
    assert "FAILED" not in render._run_label(legacy)
    assert "FAILED" not in render._run_label(completed)
    frames, motion = render._replay_state(failed, 90.0)
    assert frames[-1]["time_s"] == motion[-1]["time_s"] == 1.0
    assert all(frame["planned_mean_variance"] is None for frame in frames)
    assert render._replay_state(failed, 0.0)[0][-1]["time_s"] == 0.0
    assert comparison == before


def test_legacy_frame_only_replay_still_loads() -> None:
    legacy = _comparison()["runs"][1]
    del legacy["motion"]
    assert not render._failed(legacy)
    assert render._recorded_end(legacy) == 2.0
    frames, motion = render._replay_state(legacy, 90.0)
    assert frames == motion == legacy["frames"]


def test_partial_figures_label_failures_without_mutating_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparison = _comparison()
    before = copy.deepcopy(comparison)
    captions: list[str] = []
    savefig = Figure.savefig

    def record_savefig(figure: Figure, *args: Any, **kwargs: Any) -> Any:
        captions.extend(text.get_text() for text in figure.findobj(match=Text))
        return savefig(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", record_savefig)
    paths = render.render_figures(comparison, tmp_path)
    assert all(path.is_file() and path.stat().st_size > 1000 for path in paths)
    assert any("FAILED @ 1 s" in caption for caption in captions)
    assert any("partial, not final scores" in caption for caption in captions)
    assert comparison == before


@pytest.mark.parametrize("all_failed,failure_time", [(False, 1.0), (True, 1.0), (True, 0.0)])
def test_video_stops_at_recorded_horizon_and_marks_frozen_failed_panels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, all_failed: bool, failure_time: float
) -> None:
    comparison = _comparison(all_failed=all_failed, failure_time=failure_time)
    before = copy.deepcopy(comparison)
    captures: list[list[str]] = []

    class RecordedWriter:
        def __enter__(self) -> RecordedWriter:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def append_data(self, pixels: np.ndarray[Any, Any]) -> None:
            assert pixels.shape == (720, 1280, 3)
            captures.append([text.get_text() for text in plt.gcf().findobj(match=Text)])

    monkeypatch.setattr(render.imageio, "get_writer", lambda *args, **kwargs: RecordedWriter())
    render.render_video(comparison, tmp_path / "unused.mp4", seconds=1, fps=2)
    assert len(captures) == 2
    end = failure_time if all_failed else 2.0
    assert f"GP MAPPING LAB    /    {end:05.1f} s" in captures[-1]
    assert any(f"FAILED @ {failure_time:g} s · partial" in text for text in captures[-1])
    assert not any("90.0 s" in text for capture in captures for text in capture)
    assert comparison == before
