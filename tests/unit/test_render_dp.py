"""Renderer-only synthetic fixtures: never scientific DP performance evidence."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.figure import Figure
from matplotlib.text import Text

from attain_sampling.demo import render


def _synthetic_comparison() -> dict[str, Any]:
    """Handwritten tiny images and plans isolate display contracts from planning."""
    config = {
        "seed": 7,
        "domain": [2.0, 2.0],
        "duration_s": 2.0,
        "signal_variance": 1.0,
        "robot_count": 2,
        "model": "holonomic",
    }
    frames = []
    for moment in (0.0, 1.0, 2.0):
        frames.append(
            {
                "time_s": moment,
                "positions": [[0.1 * moment, 0.0], [2.0 - 0.1 * moment, 2.0]],
                "mean": [[0.0, 0.2], [0.1, 0.0]],
                "std": [[0.5, 0.5], [0.5, 0.5]],
                "error": [[0.0, -0.1], [0.1, 0.0]],
                "rmse": 0.07,
                "mean_variance": 0.25,
                "planned_mean_variance": 0.25,
                "path_length": 0.2 * moment,
                "samples_received": int(2 * moment),
            }
        )
    template = {
        "config": config,
        "field": {"truth": [[0.0, 0.3], [0.0, 0.0]]},
        "frames": frames,
        "motion": [{"time_s": f["time_s"], "positions": f["positions"]} for f in frames],
    }
    runs = []
    for method in ("sweep", "greedy", "adaptive", "dp"):
        run = copy.deepcopy(template)
        run["method"] = method
        runs.append(run)
    dp = runs[-1]
    dp["plans"] = [
        {
            "plan_id": "fixture-plan-0",
            "plan_version": 0,
            "generated_at_s": 0.0,
            "mission_end_s": 2.0,
            "targets_by_epoch": [[[0.1, 0.0], [1.9, 2.0]], [[0.2, 0.0], [1.8, 2.0]]],
            "sample_times_s": [1.0, 2.0],
            "forecast": [{"time_s": 0.0, "mean_variance": 0.25}],
        },
        {
            "plan_id": "fixture-plan-1",
            "plan_version": 1,
            "generated_at_s": 1.0,
            "mission_end_s": 2.0,
            "targets_by_epoch": [[[0.2, 0.1], [1.8, 1.9]]],
            "sample_times_s": [2.0],
            "forecast": [{"time_s": 1.0, "mean_variance": 0.25}],
        },
    ]
    # Arriving motion uses the old plan; outgoing frame already sees the update.
    dp["motion"][1]["plan_id"] = "fixture-plan-0"
    dp["frames"][1]["plan_id"] = "fixture-plan-1"
    return {"schema_version": 1, "scenario": "nominal", "config": config, "runs": runs}


def test_plan_replay_never_leaks_a_future_generation() -> None:
    comparison = _synthetic_comparison()
    run = comparison["runs"][-1]
    before = copy.deepcopy(run)
    assert render._replay_plan(run, -1.0) is None
    assert render._replay_plan(run, 0.0)["plan_id"] == "fixture-plan-0"
    assert render._replay_plan(run, 0.5)["plan_id"] == "fixture-plan-0"
    assert render._replay_plan(run, 1.0)["plan_id"] == "fixture-plan-1"
    assert render._replay_plan(run, 100.0)["plan_id"] == "fixture-plan-1"
    assert render._replay_plan(comparison["runs"][0], 1.0) is None
    assert run == before


def test_failed_replay_clamps_plan_selection_at_last_executed_time() -> None:
    run = _synthetic_comparison()["runs"][-1]
    run["motion"] = run["motion"][:1]
    run["frames"] = run["frames"][:1]
    run["status"] = "failed"
    assert render._replay_plan(run, 100.0)["plan_id"] == "fixture-plan-0"


def test_four_method_figures_include_b3_without_mutating_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparison = _synthetic_comparison()
    before = copy.deepcopy(comparison)
    captions: list[str] = []
    savefig = Figure.savefig

    def record_savefig(figure: Figure, *args: Any, **kwargs: Any) -> Any:
        captions.extend(text.get_text() for text in figure.findobj(match=Text))
        return savefig(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", record_savefig)
    paths = render.render_figures(comparison, tmp_path)
    assert all(path.stat().st_size > 1000 for path in paths)
    assert any("B3 periodic DP" in caption for caption in captions)
    assert comparison == before


@pytest.mark.parametrize("method_count", [1, 3, 4])
def test_video_layout_tracks_method_count_and_only_shows_known_plans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method_count: int
) -> None:
    comparison = _synthetic_comparison()
    comparison["runs"] = comparison["runs"][-method_count:]
    before = copy.deepcopy(comparison)
    captures: list[list[str]] = []

    class RecordedWriter:
        def __enter__(self) -> RecordedWriter:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def append_data(self, pixels: np.ndarray[Any, Any]) -> None:
            assert pixels.shape == (720, 1280, 3)
            assert len(plt.gcf().axes) == method_count + 2
            captures.append([text.get_text() for text in plt.gcf().findobj(match=Text)])

    monkeypatch.setattr(render.imageio, "get_writer", lambda *args, **kwargs: RecordedWriter())
    render.render_video(comparison, tmp_path / "synthetic.mp4", seconds=1, fps=2)
    assert len(captures) == 2
    assert any("Plan 0 @ 0 s; end 2 s" in text for text in captures[0])
    assert not any("Plan 1 @" in text for text in captures[0])
    assert any("Plan 1 @ 1 s; end 2 s" in text for text in captures[-1])
    assert comparison == before


def test_one_second_four_method_video_encodes_and_decodes(tmp_path: Path) -> None:
    output = render.render_video(
        _synthetic_comparison(), tmp_path / "synthetic-dp.mp4", seconds=1, fps=2
    )
    frames = imageio.mimread(str(output))
    assert len(frames) == 2
    assert frames[0].shape == (720, 1280, 3)
    assert output.stat().st_size > 1000
