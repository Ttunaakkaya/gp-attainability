"""Bounded end-to-end checks for independent comparison, replay and local HTTP UI."""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import select
import socket
import threading
import zipfile
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import pyarrow.parquet as pq
import pytest

from attain_sampling import cli
from attain_sampling.demo import runner
from attain_sampling.demo import server as demo_server
from attain_sampling.demo.render import load_comparison, render_figures, render_video
from attain_sampling.demo.server import DemoServer
from attain_sampling.eval.artifacts import canonical_digest
from attain_sampling.sim import mapping
from attain_sampling.sim.mapping import MappingConfig


@pytest.fixture(scope="module")
def tiny_comparison() -> dict[str, Any]:
    config = MappingConfig(
        duration_s=10.0,
        robot_count=2,
        grid_shape=(8, 6),
        seed=19,
        dropout_prob=0.3,
        drift_strength=0.35,
    )
    return runner.run_comparison(config, scenario="combined")


@pytest.fixture(scope="module")
def saved_comparison(
    tmp_path_factory: pytest.TempPathFactory, tiny_comparison: dict[str, Any]
) -> Path:
    return runner.save_comparison(tiny_comparison, tmp_path_factory.mktemp("demo-artifacts"))


@pytest.fixture
def local_server(tmp_path: Path) -> Iterator[DemoServer]:
    with DemoServer(0, tmp_path / "runs") as server:
        worker = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join(timeout=2.0)
            assert not worker.is_alive()


def _request(
    server: DemoServer,
    path: str,
    *,
    method: str = "GET",
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_comparison_preserves_paired_experiment_and_units(tiny_comparison: dict[str, Any]) -> None:
    comparison = tiny_comparison
    assert comparison["mode"] == "independent_exact_gp"
    assert comparison["config_hash"] == canonical_digest(comparison["config"])
    assert [run["method"] for run in comparison["runs"]] == list(runner.METHODS)
    reference = comparison["runs"][0]
    for run in comparison["runs"]:
        assert run["config"] == comparison["config"]
        assert run["field"] == reference["field"]
        assert run["initial_positions"] == reference["initial_positions"]
        assert run["seed_manifest"] == reference["seed_manifest"]
        assert run["scope"]["variance"] == "latent"
        assert run["summary"]["samples_attempted"] == 6
        for actual, paired in zip(run["samples"], reference["samples"], strict=True):
            for key in ("time_s", "robot_id", "received", "noise_innovation", "dropout_uniform"):
                assert actual[key] == paired[key]
    assert comparison["claims"]["ecc_reproduction"] is False
    assert comparison["claims"]["formal_safety_certificate"] is False
    assert comparison["claims"]["field_error_guarantee"] is False


@pytest.mark.parametrize(
    "mismatch",
    ["dropout", "field", "initial_positions", "noise", "event_key", "missing", "seed_manifest"],
)
def test_comparison_rejects_broken_pairing(
    mismatch: str, monkeypatch: pytest.MonkeyPatch, tiny_comparison: dict[str, Any]
) -> None:
    runs = {run["method"]: copy.deepcopy(run) for run in tiny_comparison["runs"]}
    modified = runs["adaptive"]
    if mismatch == "dropout":
        modified["samples"][0]["received"] = not modified["samples"][0]["received"]
    elif mismatch == "field":
        modified["field"]["truth"][0][0] += 1.0
    elif mismatch == "initial_positions":
        modified["initial_positions"][0][0] += 1.0
    elif mismatch == "noise":
        modified["samples"][0]["noise_innovation"] += 0.1
    elif mismatch == "event_key":
        modified["samples"][0]["robot_id"] = 1
    elif mismatch == "missing":
        modified["samples"] = modified["samples"][:-2]
    else:
        modified["seed_manifest"]["dropout_key"] += 1
    monkeypatch.setattr(runner, "run_mapping", lambda config, method: runs[method])
    with pytest.raises(RuntimeError):
        runner.run_comparison(MappingConfig(**tiny_comparison["config"]))


def test_saved_artifacts_match_manifest_and_source_snapshot(saved_comparison: Path) -> None:
    assert (saved_comparison / "DONE").is_file()
    loaded = load_comparison(saved_comparison / "comparison.json")
    assert loaded["config_hash"] == canonical_digest(loaded["config"])
    manifest = json.loads((saved_comparison / "artifact_manifest.json").read_text())
    for relative, expected_hash in manifest.items():
        artifact = saved_comparison / relative
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_hash
    metadata = json.loads((saved_comparison / "metadata.json").read_text())
    assert metadata["source_sha256"]
    assert metadata["package_versions"]["osqp"]
    assert metadata["comparison_status"] == "completed"
    assert metadata["controller_config"]["controller"] == "filter"
    assert "attain_sampling/gp/exact.py" in metadata["source_sha256"]
    assert "attain_sampling/sim/mapping.py" in metadata["source_sha256"]
    summaries = json.loads((saved_comparison / "summary.json").read_text())
    with zipfile.ZipFile(saved_comparison / "source_snapshot.zip") as snapshot:
        for relative, expected_hash in metadata["source_sha256"].items():
            assert hashlib.sha256(snapshot.read(relative)).hexdigest() == expected_hash
        assert "uv.lock" in snapshot.namelist()
        assert not any(
            "references/private" in name or ".venv" in name for name in snapshot.namelist()
        )
    for run in loaded["runs"]:
        summary = summaries[run["method"]]
        assert summary["status"] == "completed" and summary["failure"] is None
        assert summary["requested_duration_s"] == loaded["config"]["duration_s"]
        assert summary["metric_scope"] == "completed_full_horizon"
        assert all(summary[key] == value for key, value in run["summary"].items())
        directory = saved_comparison / run["method"]
        assert pq.read_table(directory / "robots.parquet").to_pylist() == run["motion"]
        assert pq.read_table(directory / "samples.parquet").to_pylist() == run["samples"]
        assert pq.read_table(directory / "controls.parquet").to_pylist() == run["controls"]
        assert json.loads((directory / "controls.json").read_text()) == run["controls"]
        assert json.loads((directory / "status.json").read_text()) == {
            "status": "completed",
            "failure": None,
        }
        metrics = pq.read_table(directory / "timeseries.parquet").to_pylist()
        assert len(metrics) == len(run["frames"])
        assert metrics[-1]["rmse"] == run["summary"]["rmse"]


def test_save_is_unique_and_latest_ignores_unfinished_runs(
    tmp_path: Path, tiny_comparison: dict[str, Any]
) -> None:
    assert runner.latest_comparison(tmp_path) is None
    first = runner.save_comparison(tiny_comparison, tmp_path)
    first_bytes = (first / "comparison.json").read_bytes()
    second = runner.save_comparison(tiny_comparison, tmp_path)
    assert first != second
    assert (first / "comparison.json").read_bytes() == first_bytes
    unfinished = tmp_path / "99999999-unfinished"
    unfinished.mkdir()
    (unfinished / "comparison.json").write_text("{}", encoding="utf-8")
    assert runner.latest_comparison(tmp_path) == second / "comparison.json"


def test_failed_config_hash_never_gets_done_marker(
    tmp_path: Path, tiny_comparison: dict[str, Any]
) -> None:
    invalid = copy.deepcopy(tiny_comparison)
    invalid["config_hash"] = "bad-configuration-hash"
    with pytest.raises(RuntimeError, match="configuration hash"):
        runner.save_comparison(invalid, tmp_path)
    assert not list(tmp_path.glob("*/DONE"))
    assert runner.latest_comparison(tmp_path) is None


def test_benchmark_records_every_requested_job(tmp_path: Path) -> None:
    report = runner.benchmark(
        MappingConfig(duration_s=5.0, robot_count=2, grid_shape=(6, 4)),
        seeds=[3],
        scenarios=["nominal", "dropout"],
        output_root=tmp_path,
    )
    assert len(report["records"]) == 6
    assert report["pilot_comparison_s"] > 0
    assert {(row["scenario"], row["seed"], row["method"]) for row in report["records"]} == {
        (scenario, 3, method) for scenario in ("nominal", "dropout") for method in runner.METHODS
    }
    assert Path(report["report_path"]).is_file()
    assert all((Path(row["path"]) / "DONE").is_file() for row in report["records"])
    assert report["status"] == "completed"
    assert report["failure_count"] == 0
    assert all(row["status"] == "completed" for row in report["records"])
    assert all(row["requested_duration_s"] == 5.0 for row in report["records"])
    assert all(row["metric_scope"] == "completed_full_horizon" for row in report["records"])


@pytest.fixture(scope="module")
def failed_qp_comparison() -> dict[str, Any]:
    return runner.run_comparison(
        MappingConfig(
            duration_s=10.0,
            robot_count=2,
            grid_shape=(8, 6),
            controller="qp",
            qp_max_iter=1,
        )
    )


def test_failed_qp_prefixes_are_retained_and_serialized(
    tmp_path: Path, failed_qp_comparison: dict[str, Any]
) -> None:
    comparison = failed_qp_comparison
    assert comparison["status"] == "completed_with_failures"
    assert comparison["failure_count"] == 3
    # Open-loop planning fails before sensing, adaptive after the first epoch.
    assert [len(run["samples"]) for run in comparison["runs"]] == [0, 0, 2]
    directory = runner.save_comparison(comparison, tmp_path)
    assert "artifact serialization complete" in (directory / "DONE").read_text()
    assert runner.latest_comparison(tmp_path) == directory / "comparison.json"
    assert load_comparison(directory / "comparison.json") == json.loads(json.dumps(comparison))
    summaries = json.loads((directory / "summary.json").read_text())
    for run in comparison["runs"]:
        summary = summaries[run["method"]]
        assert summary["status"] == "failed" and summary["failure"] == run["failure"]
        assert summary["requested_duration_s"] == comparison["config"]["duration_s"]
        assert summary["metric_scope"] == "partial_mission_at_last_executed_time"
        assert all(summary[key] == value for key, value in run["summary"].items())
        assert run["status"] == "failed" and run["failure"]
        assert run["summary"]["completion_time_s"] < comparison["config"]["duration_s"]
        assert run["controls"][-1]["success"] is False
        method_dir = directory / run["method"]
        assert pq.read_table(method_dir / "samples.parquet").to_pylist() == run["samples"]
        assert pq.read_table(method_dir / "robots.parquet").to_pylist() == run["motion"]
        saved_controls = pq.read_table(method_dir / "controls.parquet").to_pylist()
        assert saved_controls == run["controls"]
        assert json.loads((method_dir / "status.json").read_text())["failure"] == run["failure"]
    manifest = json.loads((directory / "artifact_manifest.json").read_text())
    for relative, expected_hash in manifest.items():
        assert hashlib.sha256((directory / relative).read_bytes()).hexdigest() == expected_hash


def test_mixed_completed_and_failed_comparison_keeps_all_methods(
    monkeypatch: pytest.MonkeyPatch, failed_qp_comparison: dict[str, Any]
) -> None:
    config = MappingConfig(**failed_qp_comparison["config"])
    completed = runner.run_mapping(replace(config, qp_max_iter=10000), "adaptive")
    # A synthetic mixed-status fixture tests retention, not solver convergence.
    # Real failures from the forced iteration cap are exercised separately.
    completed["config"] = dict(failed_qp_comparison["config"])
    runs = {run["method"]: run for run in failed_qp_comparison["runs"]}
    monkeypatch.setattr(
        runner,
        "run_mapping",
        lambda config, method: completed if method == "adaptive" else runs[method],
    )
    result = runner.run_comparison(config)
    assert result["failure_count"] == 2
    assert len(result["runs"]) == 3
    assert result["runs"][-1]["status"] == "completed"


def test_benchmark_retains_failed_jobs(tmp_path: Path) -> None:
    result = runner.benchmark(
        MappingConfig(
            duration_s=5.0,
            robot_count=2,
            grid_shape=(6, 4),
            controller="qp",
            qp_max_iter=1,
        ),
        seeds=[7],
        scenarios=["nominal", "combined"],
        output_root=tmp_path,
    )
    assert len(result["records"]) == result["failure_count"] == 6
    assert result["status"] == "completed_with_failures"
    assert all(row["status"] == "failed" and row["failure"] for row in result["records"])
    assert all(row["requested_duration_s"] == 5.0 for row in result["records"])
    assert all(
        row["metric_scope"] == "partial_mission_at_last_executed_time" for row in result["records"]
    )
    assert all((Path(row["path"]) / "DONE").is_file() for row in result["records"])


def test_failed_prefix_cannot_include_samples_after_actual_stop(
    monkeypatch: pytest.MonkeyPatch,
    tiny_comparison: dict[str, Any],
) -> None:
    runs = {run["method"]: copy.deepcopy(run) for run in tiny_comparison["runs"]}
    failed = runs["adaptive"]
    failed.update(status="failed", failure={"reason": "synthetic failure fixture"})
    failed["summary"]["completion_time_s"] = 0.0
    monkeypatch.setattr(runner, "run_mapping", lambda config, method: runs[method])
    with pytest.raises(RuntimeError, match="last executed time"):
        runner.run_comparison(MappingConfig(**tiny_comparison["config"]))


def test_started_failed_mission_cannot_omit_elapsed_sensor_epoch(
    monkeypatch: pytest.MonkeyPatch,
    tiny_comparison: dict[str, Any],
) -> None:
    runs = {run["method"]: copy.deepcopy(run) for run in tiny_comparison["runs"]}
    failed = runs["adaptive"]
    failed.update(status="failed", failure={"reason": "synthetic failure", "phase": "execution"})
    failed["motion"] = [state for state in failed["motion"] if state["time_s"] <= 6.0]
    failed["samples"] = failed["samples"][:2]  # Deliberately omit the elapsed t=5 epoch.
    received = sum(sample["received"] for sample in failed["samples"])
    failed["summary"].update(
        completion_time_s=6.0,
        samples_attempted=2,
        samples_received=received,
        samples_lost=2 - received,
    )
    monkeypatch.setattr(runner, "run_mapping", lambda config, method: runs[method])
    with pytest.raises(RuntimeError, match="missing elapsed sensor epochs"):
        runner.run_comparison(MappingConfig(**tiny_comparison["config"]))


@pytest.mark.parametrize("count", ["samples_attempted", "samples_received", "samples_lost"])
def test_pairing_rejects_inconsistent_sample_summary_counts(
    monkeypatch: pytest.MonkeyPatch,
    tiny_comparison: dict[str, Any],
    count: str,
) -> None:
    runs = {run["method"]: copy.deepcopy(run) for run in tiny_comparison["runs"]}
    runs["adaptive"]["summary"][count] += 1
    monkeypatch.setattr(runner, "run_mapping", lambda config, method: runs[method])
    with pytest.raises(RuntimeError, match="sample counts"):
        runner.run_comparison(MappingConfig(**tiny_comparison["config"]))


def test_server_gets_are_read_only_and_traversal_is_rejected(local_server: DemoServer) -> None:
    assert local_server.server_address[0] == "127.0.0.1"
    status, headers, body = _request(local_server, "/api/status")
    assert status == 200
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"
    assert json.loads(body)["latest_available"] is False
    for path in ("/", "/index.html", "/app.js", "/styles.css"):
        code, _, asset = _request(local_server, path)
        assert code == 200
        assert asset
    for path in ("/api/latest", "/api/video", "/../../pyproject.toml", "/unknown"):
        assert _request(local_server, path)[0] == 404
    assert not local_server.output_root.exists()


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        '{"extra": 1}',
        '{"robots": 3.0}',
        '{"seed": true}',
        '{"seed": -1}',
        '{"duration_s": true}',
        '{"duration_s": 301}',
        '{"duration_s": 10.25}',
        '{"scenario": "unknown"}',
        '{"controller": "unknown"}',
        '{"controller": "qp", "model": "usv"}',
        '{"controller": "qp", "qp_max_iter": true}',
        '{"controller": "qp", "qp_alpha": "1.0"}',
        '{"methods": []}',
        '{"methods": "dp"}',
        '{"methods": ["dp", "dp"]}',
        '{"methods": ["unknown"]}',
        '{"methods": [true]}',
        '{"methods": ["dp"], "model": "usv"}',
        '{"dp_horizon_steps": true}',
        '{"dp_horizon_steps": 0}',
        '{"dp_grid_shape": "4,3"}',
        '{"dp_grid_shape": [4]}',
        '{"dp_grid_shape": [4, false]}',
        '{"dp_travel_weight": -1}',
        '{"dp_travel_weight": "0.1"}',
        '{"gp_backend": "unknown"}',
        '{"gp_backend": true}',
        '{"sogp_max_basis": true}',
        '{"sogp_max_basis": 32.0}',
        '{"sogp_max_basis": 0}',
        '{"sogp_max_basis": 513}',
        '{"sogp_novelty_tolerance": "0.01"}',
        '{"sogp_novelty_tolerance": true}',
        '{"sogp_novelty_tolerance": 0}',
        '{"sogp_novelty_tolerance": 1}',
        '{"sogp_novelty_tolerance": NaN}',
    ],
)
def test_invalid_http_run_requests_do_not_write_artifacts(
    local_server: DemoServer, body: str
) -> None:
    status, _, response = _request(local_server, "/api/run", method="POST", body=body)
    assert status == 400
    assert "error" in json.loads(response)
    assert not local_server.run_lock.locked()
    assert not local_server.output_root.exists()


def test_http_origin_and_concurrent_run_guards(local_server: DemoServer) -> None:
    code, _, _ = _request(
        local_server,
        "/api/run",
        method="POST",
        body="{}",
        headers={"Origin": "https://example.invalid"},
    )
    assert code == 403
    with local_server.run_lock:
        assert _request(local_server, "/api/run", method="POST", body="{}")[0] == 409
    assert _request(local_server, "/not-an-endpoint", method="POST", body="{}")[0] == 404
    assert not local_server.output_root.exists()


@pytest.mark.parametrize("guard,expected", [("origin", 403), ("busy", 409), ("path", 404)])
def test_http_rejection_drains_delayed_bounded_body_before_socket_close(
    local_server: DemoServer, guard: str, expected: int
) -> None:
    """Unread POST data must not reset a valid rejection response on Windows."""
    connection = http.client.HTTPConnection("127.0.0.1", local_server.server_port, timeout=3)
    if guard == "busy":
        local_server.run_lock.acquire()
    try:
        connection.putrequest("POST", "/unknown" if guard == "path" else "/api/run")
        connection.putheader("Content-Length", "2")
        if guard == "origin":
            connection.putheader("Origin", "https://example.invalid")
        connection.endheaders()
        assert connection.sock is not None
        # An eager response here recreates the old unread-body close race.
        assert not select.select([connection.sock], [], [], 0.025)[0]
        connection.send(b"{")
        assert not select.select([connection.sock], [], [], 0.025)[0]
        connection.send(b"}")
        response = connection.getresponse()
        assert response.status == expected
        assert response.getheader("Connection") == "close"
        assert "error" in json.loads(response.read())
    finally:
        connection.close()
        if guard == "busy":
            local_server.run_lock.release()
    assert not local_server.output_root.exists()


def test_http_repeated_busy_rejections_are_delivered_as_json(local_server: DemoServer) -> None:
    with local_server.run_lock:
        for _ in range(25):
            code, _, body = _request(local_server, "/api/run", method="POST", body="{}")
            assert code == 409
            assert "comparison is running" in json.loads(body)["error"]
    assert not local_server.output_root.exists()


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("Content-Length", "0")],
        [("Content-Length", "16385")],
        [("Content-Length", "invalid")],
        [("Content-Length", "2"), ("Content-Length", "2")],
        [("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
    ],
)
def test_http_invalid_framing_is_rejected_without_waiting_or_locking(
    local_server: DemoServer, headers: list[tuple[str, str]]
) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", local_server.server_port, timeout=3)
    try:
        connection.putrequest("POST", "/api/run")
        for name, value in headers:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 400
        assert "error" in json.loads(response.read())
    finally:
        connection.close()
    assert not local_server.run_lock.locked()
    assert not local_server.output_root.exists()


@pytest.mark.parametrize("incomplete", ["timeout", "truncated"])
def test_http_incomplete_body_has_bounded_failure_without_simulation_lock(
    local_server: DemoServer, monkeypatch: pytest.MonkeyPatch, incomplete: str
) -> None:
    monkeypatch.setattr(demo_server, "REQUEST_BODY_TIMEOUT_S", 0.05)
    connection = http.client.HTTPConnection("127.0.0.1", local_server.server_port, timeout=3)
    try:
        connection.putrequest("POST", "/api/run")
        connection.putheader("Content-Length", "2")
        connection.endheaders()
        if incomplete == "truncated":
            connection.send(b"{")
            assert connection.sock is not None
            connection.sock.shutdown(socket.SHUT_WR)
        response = connection.getresponse()
        assert response.status == (408 if incomplete == "timeout" else 400)
        assert "error" in json.loads(response.read())
    finally:
        connection.close()
    assert not local_server.run_lock.locked()
    assert not local_server.output_root.exists()


def test_server_serves_saved_latest(local_server: DemoServer, saved_comparison: Path) -> None:
    local_server.latest = saved_comparison / "comparison.json"
    code, _, body = _request(local_server, "/api/latest")
    assert code == 200
    assert body == local_server.latest.read_bytes()
    assert json.loads(_request(local_server, "/api/status")[2])["latest_available"] is True


def test_valid_http_run_updates_latest_after_complete_artifact(local_server: DemoServer) -> None:
    code, _, body = _request(
        local_server,
        "/api/run",
        method="POST",
        body=json.dumps({"duration_s": 10, "robots": 2, "scenario": "nominal", "seed": 11}),
    )
    assert code == 200
    result = json.loads(body)
    assert result["config"]["seed"] == 11
    assert result["config"]["robot_count"] == 2
    assert local_server.latest is not None
    assert (local_server.latest.parent / "DONE").is_file()
    assert json.loads(_request(local_server, "/api/latest")[2]) == result
    assert not local_server.run_lock.locked()


@pytest.mark.parametrize("iterations,failed", [(10000, False), (1, True)])
def test_http_qp_success_and_failure_evidence(
    local_server: DemoServer,
    iterations: int,
    failed: bool,
) -> None:
    code, _, body = _request(
        local_server,
        "/api/run",
        method="POST",
        body=json.dumps(
            {
                "duration_s": 10,
                "robots": 2,
                "scenario": "nominal",
                "controller": "qp",
                "qp_max_iter": iterations,
            }
        ),
    )
    assert code == 200  # Successful API request; mission status is separate.
    result = json.loads(body)
    assert result["status"] == ("completed_with_failures" if failed else "completed")
    assert result["failure_count"] == (3 if failed else 0)
    assert result["config"]["controller"] == "qp"
    assert local_server.latest is not None
    assert json.loads(local_server.latest.read_text()) == result
    assert (local_server.latest.parent / "DONE").is_file()
    info = json.loads(_request(local_server, "/api/status")[2])
    assert info["controller_models"]["qp"] == ["holonomic"]
    assert not local_server.run_lock.locked()


def test_cli_parser_and_independent_smoke_without_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli.build_parser().parse_args(
        ["simulate", "--scenario", "nominal", "--robots", "2", "--model", "usv"]
    )
    assert (args.command, args.scenario, args.robots, args.model) == (
        "simulate",
        "nominal",
        2,
        "usv",
    )
    result = cli.run(
        ["simulate", "--duration", "5", "--robots", "2", "--no-figures", "--output", str(tmp_path)]
    )
    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "independent_exact_gp"
    assert set(report["summary"]) == set(runner.METHODS)
    assert (Path(report["output"]) / "DONE").is_file()


def test_cli_invalid_simulation_returns_actionable_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.run(["simulate", "--duration", "-1", "--no-figures"]) == 2
    assert "independent simulation error" in capsys.readouterr().err
    with pytest.raises(SystemExit) as failure:
        cli.build_parser().parse_args(["simulate", "--robots", "5"])
    assert failure.value.code == 2


def test_figures_and_two_frame_video_render_recorded_results(
    tmp_path: Path, tiny_comparison: dict[str, Any]
) -> None:
    before = copy.deepcopy(tiny_comparison)
    paths = render_figures(tiny_comparison, tmp_path / "figures")
    assert len(paths) == 2
    for path in paths:
        pixels = imageio.imread(path)
        assert pixels.shape[0] > 100 and pixels.shape[1] > 100
        assert pixels.std() > 1
    with pytest.raises(FileExistsError):
        render_figures(tiny_comparison, tmp_path / "figures")
    video = render_video(tiny_comparison, tmp_path / "demo.mp4", seconds=1, fps=2)
    assert video.is_file() and video.stat().st_size > 1000
    recording = imageio.mimread(str(video))
    assert len(recording) == 2
    assert recording[0].shape[:2] == (720, 1280)
    with pytest.raises(FileExistsError):
        render_video(tiny_comparison, video, seconds=1, fps=2)
    assert tiny_comparison == before


@pytest.mark.parametrize(
    "seconds,fps", [(0.0, 12), (float("nan"), 12), (1.0, 0), (1.0, 61), (0.1, 1)]
)
def test_invalid_video_options_are_rejected(
    tmp_path: Path, tiny_comparison: dict[str, Any], seconds: float, fps: int
) -> None:
    with pytest.raises(ValueError):
        render_video(tiny_comparison, tmp_path / "invalid.mp4", seconds=seconds, fps=fps)
    assert not (tmp_path / "invalid.mp4").exists()


def test_invalid_replay_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"schema_version": 2, "runs": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema-v1"):
        load_comparison(path)


@pytest.fixture(scope="module")
def tiny_dp_comparison() -> dict[str, Any]:
    config = MappingConfig(
        duration_s=12.0,
        robot_count=2,
        grid_shape=(8, 6),
        seed=19,
        dropout_prob=0.3,
        drift_strength=0.35,
        controller="qp",
        dp_grid_shape=(4, 3),
        dp_horizon_steps=2,
    )
    return runner.run_comparison(config, scenario="combined", methods=("dp",))


def test_selected_methods_preserve_defaults_and_reject_invalid_before_execution(
    monkeypatch: pytest.MonkeyPatch, tiny_comparison: dict[str, Any]
) -> None:
    assert tiny_comparison["selected_methods"] == list(runner.METHODS)
    assert (*runner.METHODS, "dp", "p") == runner.AVAILABLE_METHODS

    def must_not_execute(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid method selection started a mission")

    monkeypatch.setattr(runner, "run_mapping", must_not_execute)
    for invalid in ((), ("dp", "dp"), ("nope",), "dp", (True,)):
        with pytest.raises(ValueError, match="nonempty unique"):
            runner.run_comparison(MappingConfig(), methods=invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="original turn-in-place USV"):
        runner.run_comparison(MappingConfig(model="usv"), methods=("dp",))


def test_dp_plan_artifacts_roundtrip_and_tail_clock(
    tmp_path: Path, tiny_dp_comparison: dict[str, Any]
) -> None:
    directory = runner.save_comparison(tiny_dp_comparison, tmp_path)
    run = tiny_dp_comparison["runs"][0]
    assert run["status"] == "completed"
    assert run["plans"][-1]["sample_times_s"] == []
    assert run["plans"][-1]["targets_by_epoch"] == []
    assert json.loads((directory / "dp" / "plans.json").read_text()) == json.loads(
        json.dumps(run["plans"])
    )
    expected = [
        {"plan_id": plan["plan_id"], "time_s": time_s, "robot_id": robot, "position": position}
        for plan in run["plans"]
        for time_s, epoch in zip(plan["sample_times_s"], plan["targets_by_epoch"], strict=True)
        for robot, position in enumerate(epoch)
    ]
    assert pq.read_table(directory / "dp" / "planned_samples.parquet").to_pylist() == expected
    for name, key in (("robots", "motion"), ("samples", "samples"), ("controls", "controls")):
        assert pq.read_table(directory / "dp" / f"{name}.parquet").to_pylist() == run[key]
    metadata = json.loads((directory / "metadata.json").read_text())
    assert metadata["selected_methods"] == ["dp"]
    assert metadata["planner_config"]["dp_horizon_steps"] == 2
    assert "not controller-in-the-loop" in metadata["claims"]["dp_forecast"]
    assert "attain_sampling/planning/timed_dp.py" in metadata["source_sha256"]
    manifest = json.loads((directory / "artifact_manifest.json").read_text())
    for relative, digest in manifest.items():
        assert hashlib.sha256((directory / relative).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "corruption",
    [
        "deadline",
        "time",
        "target_count",
        "forecast_time",
        "unknown_link",
        "duplicate_id",
        "future_link",
        "version",
        "missing_plan",
        "observation_count",
        "belief_prefix",
        "sample_keys",
        "start_positions",
        "missing_link",
        "previous_plan",
    ],
)
def test_dp_corrupt_plan_evidence_is_rejected_before_saving(
    tmp_path: Path, tiny_dp_comparison: dict[str, Any], corruption: str
) -> None:
    invalid = copy.deepcopy(tiny_dp_comparison)
    run = invalid["runs"][0]
    plan = run["plans"][0]
    if corruption == "deadline":
        plan["mission_end_s"] += 5
    elif corruption == "time":
        plan["sample_times_s"][0] = 0.0
    elif corruption == "target_count":
        plan["targets_by_epoch"][0].pop()
    elif corruption == "forecast_time":
        plan["forecast"][0]["time_s"] = 1.0
    elif corruption == "unknown_link":
        run["samples"][-1]["plan_id"] = "missing-plan"
    elif corruption == "duplicate_id":
        run["plans"][1]["plan_id"] = plan["plan_id"]
    elif corruption == "future_link":
        run["motion"][0]["plan_id"] = run["plans"][1]["plan_id"]
    elif corruption == "version":
        run["plans"][1]["plan_version"] = plan["plan_version"]
    elif corruption == "missing_plan":
        run["plans"] = []
    elif corruption == "belief_prefix":
        plan["belief_observation_count"] += 1
    elif corruption == "sample_keys":
        plan["received_sample_keys"].append([100.0, 0])
    elif corruption == "start_positions":
        plan["start_positions"][0][0] += 1.0
    elif corruption == "missing_link":
        run["samples"][-1].pop("plan_id")
    elif corruption == "previous_plan":
        run["plans"][1]["previous_plan_id"] = None
    else:
        plan["belief_observation_count"] = -1
    with pytest.raises(RuntimeError):
        runner.save_comparison(invalid, tmp_path)
    assert not list(tmp_path.iterdir())


def test_http_dp_selection_and_config_roundtrip(local_server: DemoServer) -> None:
    code, _, body = _request(
        local_server,
        "/api/run",
        method="POST",
        body=json.dumps(
            {
                "duration_s": 10,
                "robots": 2,
                "scenario": "nominal",
                "methods": ["dp"],
                "dp_grid_shape": [4, 3],
                "dp_horizon_steps": 2,
                "dp_travel_weight": 0.02,
            }
        ),
    )
    assert code == 200
    result = json.loads(body)
    assert result["selected_methods"] == ["dp"]
    assert result["config"]["controller"] == "filter"
    assert result["config"]["dp_grid_shape"] == [4, 3]
    assert result["config"]["dp_horizon_steps"] == 2
    assert result["config"]["dp_travel_weight"] == 0.02
    assert result["runs"][0]["plans"]
    info = json.loads(_request(local_server, "/api/status")[2])
    assert info["methods"] == list(runner.METHODS)
    assert info["available_methods"] == list(runner.AVAILABLE_METHODS)
    assert info["method_models"]["dp"] == ["holonomic", "usv_curvature"]


def test_http_sogp_selection_and_saved_evidence(local_server: DemoServer) -> None:
    code, _, body = _request(
        local_server,
        "/api/run",
        method="POST",
        body=json.dumps(
            {
                "duration_s": 10,
                "robots": 2,
                "scenario": "nominal",
                "methods": ["dp"],
                "gp_backend": "sogp",
                "sogp_max_basis": 2,
                "sogp_novelty_tolerance": 0.0001,
                "dp_grid_shape": [4, 3],
            }
        ),
    )
    assert code == 200
    result = json.loads(body)
    assert result["mode"] == "independent_sogp"
    assert result["config"]["sogp_novelty_tolerance"] == 0.0001
    run = result["runs"][0]
    assert run["gp_telemetry"]["dictionary_size"] == 2
    assert run["gp_telemetry"]["pruned_count"] > 0
    assert local_server.latest is not None
    directory = local_server.latest.parent
    assert json.loads((directory / "dp/gp_updates.json").read_text()) == run["gp_updates"]
    assert json.loads((directory / "dp/gp_failures.json").read_text()) == []
    assert pq.read_table(directory / "dp/samples.parquet").to_pylist() == run["samples"]
    assert (
        json.loads((directory / "metadata.json").read_text())["gp_config"]["gp_backend"] == "sogp"
    )
    info = json.loads(_request(local_server, "/api/status")[2])
    assert info["gp_backends"] == ["exact", "sogp"]
    assert info["default_gp_backend"] == "exact"


def test_benchmark_supports_opt_in_dp(tmp_path: Path) -> None:
    report = runner.benchmark(
        MappingConfig(duration_s=5.0, robot_count=2, grid_shape=(6, 4), dp_grid_shape=(4, 3)),
        seeds=[3],
        scenarios=["nominal"],
        methods=("sweep", "dp"),
        output_root=tmp_path,
    )
    assert report["selected_methods"] == ["sweep", "dp"]
    assert [record["method"] for record in report["records"]] == ["sweep", "dp"]


@pytest.mark.parametrize("failed_version", [0, 1])
def test_dp_planning_failure_retains_real_prefix_and_partial_artifacts(
    failed_version: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = mapping.plan_timed_dp

    def fail_selected_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["plan_version"] == failed_version:
            raise ValueError("controlled planner-rejection fixture")
        return original(*args, **kwargs)

    monkeypatch.setattr(mapping, "plan_timed_dp", fail_selected_plan)
    comparison = runner.run_comparison(
        MappingConfig(duration_s=10.0, robot_count=2, dp_grid_shape=(4, 3)), methods=("dp",)
    )
    assert comparison["status"] == "completed_with_failures"
    run = comparison["runs"][0]
    assert run["failure"]["phase"] == "planning"
    assert run["summary"]["completion_time_s"] == failed_version * 5.0
    assert len(run["samples"]) == (failed_version + 1) * 2
    assert len(run["plans"]) == failed_version
    assert len(run["planning_failures"]) == 1
    directory = runner.save_comparison(comparison, tmp_path)
    saved = json.loads((directory / "comparison.json").read_text())
    assert saved["runs"][0]["planning_failures"] == run["planning_failures"]
    assert (directory / "DONE").is_file()
    assert pq.read_table(directory / "dp" / "samples.parquet").to_pylist() == run["samples"]
    summaries = json.loads((directory / "summary.json").read_text())
    assert summaries["dp"]["metric_scope"] == "partial_mission_at_last_executed_time"


@pytest.mark.parametrize("record_kind", ["motion", "samples", "controls", "frames", "forecast"])
def test_dp_rejects_stale_known_plan_links(
    tmp_path: Path, tiny_dp_comparison: dict[str, Any], record_kind: str
) -> None:
    invalid = copy.deepcopy(tiny_dp_comparison)
    run = invalid["runs"][0]
    old_id = run["plans"][0]["plan_id"]
    if record_kind == "forecast":
        record = next(frame for frame in run["frames"] if frame["time_s"] == 10.0)
        record["forecast_plan_id"] = old_id
    else:
        record = next(record for record in run[record_kind] if record["time_s"] > 5.0)
        record["plan_id"] = old_id
    with pytest.raises(RuntimeError, match="active"):
        runner.save_comparison(invalid, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("record_kind", ["motion", "samples", "controls"])
def test_dp_epoch_arrival_belongs_to_incoming_not_new_plan(
    tmp_path: Path, tiny_dp_comparison: dict[str, Any], record_kind: str
) -> None:
    invalid = copy.deepcopy(tiny_dp_comparison)
    run = invalid["runs"][0]
    record = next(record for record in run[record_kind] if record["time_s"] == 5.0)
    record["plan_id"] = run["plans"][1]["plan_id"]
    with pytest.raises(RuntimeError, match="active incoming"):
        runner.save_comparison(invalid, tmp_path)


def test_dp_cannot_drop_a_periodic_plan_and_relabel_later_evidence(
    tmp_path: Path, tiny_dp_comparison: dict[str, Any]
) -> None:
    invalid = copy.deepcopy(tiny_dp_comparison)
    run = invalid["runs"][0]
    dropped = run["plans"].pop(1)
    old_id = run["plans"][0]["plan_id"]
    run["plans"][1]["previous_plan_id"] = old_id
    for records in (run["motion"], run["samples"], run["controls"], run["frames"]):
        for record in records:
            for key in ("plan_id", "forecast_plan_id"):
                if record.get(key) == dropped["plan_id"]:
                    record[key] = old_id
    with pytest.raises(RuntimeError, match="periodic generation epoch"):
        runner.save_comparison(invalid, tmp_path)


def test_dp_execution_failure_after_replanning_requires_new_epoch_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = mapping._advance

    def fail_after_second_plan(
        positions: Any, headings: Any, targets: Any, config: MappingConfig, tick: int, **kwargs: Any
    ) -> Any:
        if tick == 11 and kwargs.get("phase") == "execution":
            config = replace(config, qp_max_iter=1)
        return original(positions, headings, targets, config, tick, **kwargs)

    monkeypatch.setattr(mapping, "_advance", fail_after_second_plan)
    comparison = runner.run_comparison(
        MappingConfig(
            duration_s=10.0,
            robot_count=2,
            controller="qp",
            dp_grid_shape=(4, 3),
            drift_strength=0.35,
        ),
        methods=("dp",),
    )
    run = comparison["runs"][0]
    assert run["status"] == "failed" and run["failure"]["phase"] == "execution"
    assert run["summary"]["completion_time_s"] == 5.0
    assert [plan["generated_at_s"] for plan in run["plans"]] == [0.0, 5.0]
    directory = runner.save_comparison(comparison, tmp_path)
    assert (directory / "DONE").is_file()
    invalid = copy.deepcopy(comparison)
    invalid["runs"][0]["plans"].pop()
    with pytest.raises(RuntimeError, match="periodic generation epoch"):
        runner.save_comparison(invalid, tmp_path)


def test_dp_artifact_validator_accepts_ulp_rounded_control_and_sample_clocks() -> None:
    comparison = runner.run_comparison(
        MappingConfig(
            duration_s=6.3,
            dt=0.7,
            sample_period_s=2.1,
            robot_count=2,
            dp_grid_shape=(4, 3),
            grid_shape=(8, 6),
        ),
        methods=("dp",),
    )
    assert comparison["status"] == "completed"
    assert len(comparison["runs"][0]["plans"]) == 3
