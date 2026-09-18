from __future__ import annotations

import json
from pathlib import Path

import pytest

from attain_sampling import cli


@pytest.mark.parametrize("command", ["simulate", "benchmark"])
def test_sogp_cli_roundtrip(tmp_path, capsys, command):
    arguments = [
        command,
        "--gp-backend",
        "sogp",
        "--sogp-max-basis",
        "2",
        "--sogp-novelty-tolerance",
        "0.0001",
        "--robots",
        "2",
        "--duration",
        "10",
        "--methods",
        "dp",
        "--output",
        str(tmp_path),
    ]
    if command == "simulate":
        arguments += ["--no-figures", "--scenario", "nominal"]
    else:
        arguments += ["--scenarios", "nominal", "--seeds", "7"]
    assert cli.run(arguments) == 0
    capsys.readouterr()
    paths = list(tmp_path.glob("*/comparison.json"))
    assert len(paths) == 1
    result = json.loads(paths[0].read_text())
    assert result["config"]["gp_backend"] == "sogp"
    assert result["config"]["sogp_max_basis"] == 2
    assert result["config"]["sogp_novelty_tolerance"] == 0.0001
    assert result["runs"][0]["gp_telemetry"]["pruned_count"] > 0


def write_config(path: Path, *, private_reference_root: str = "references/private") -> Path:
    # `_find_repository_root` walks up for a pyproject.toml; without one it falls back to
    # the real checkout and would read the developer's licensed anchor PDF.
    (path.parent / "pyproject.toml").write_text('[project]\nname = "cli-test"\n', encoding="utf-8")
    path.write_text(
        f"""
schema_version: 1
name: cli-test
phase: G0_source_lock
master_seed: 9
clocks:
  control_s: 0.2
  sampling_s: 1.0
  planning_s: 2.0
  logging_s: 0.4
paths:
  output_root: outputs
  private_reference_root: {private_reference_root}
""".lstrip(),
        encoding="utf-8",
    )
    return path


def test_validate_config_reports_valid_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = write_config(tmp_path / "valid.yaml")

    result = cli.run(["validate-config", str(config_path)])

    captured = capsys.readouterr()
    assert result == 0
    assert "valid schema v1: cli-test (G0_source_lock)" in captured.out
    assert captured.err == ""


def test_validate_config_reports_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("not: the expected schema\n", encoding="utf-8")

    result = cli.run(["validate-config", str(config_path)])

    captured = capsys.readouterr()
    assert result == 2
    assert "configuration error:" in captured.err


@pytest.mark.parametrize("command", ["reproduce", "compare", "figures"])
def test_research_commands_remain_locked(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.run([command])

    captured = capsys.readouterr()
    assert result == 2
    assert f"'{command}' is reserved but locked" in captured.err


def test_doctor_reports_gate_block_without_full_paper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = write_config(tmp_path / "doctor.yaml")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_package_versions", lambda: {"numpy": "2.0"})
    monkeypatch.setattr(cli, "_environment_issues", lambda versions: ([], ["CLARABEL", "OSQP"]))

    result = cli.run(["doctor", "--config", str(config_path)])

    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert report["environment"] == "ready"
    assert report["paper_full_text"] == "missing"
    assert report["research_status"] == "G0_blocked_on_full_text"


def test_doctor_strict_paper_guard_has_distinct_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = write_config(tmp_path / "doctor.yaml")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_package_versions", lambda: {"numpy": "2.0"})
    monkeypatch.setattr(cli, "_environment_issues", lambda versions: ([], ["CLARABEL", "OSQP"]))

    result = cli.run(["doctor", "--strict-paper", "--config", str(config_path)])

    report = json.loads(capsys.readouterr().out)
    assert result == 3
    assert report["research_status"] == "G0_blocked_on_full_text"


def test_doctor_detects_full_paper_and_missing_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test-root'\n", encoding="utf-8")
    config_path = write_config(tmp_path / "doctor.yaml")
    private_references = tmp_path / "references" / "private"
    private_references.mkdir(parents=True)
    paper = private_references / cli.EXPECTED_ANCHOR_FILENAME
    paper.write_bytes(b"%PDF-1.7\n" + (b"0" * 2048) + b"\n%%EOF\n")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        cli,
        "_package_versions",
        lambda: {"numpy": "2.0", "cvxpy": "MISSING"},
    )
    monkeypatch.setattr(
        cli,
        "_environment_issues",
        lambda versions: (["missing_distribution:cvxpy"], []),
    )

    result = cli.run(["doctor", "--strict-paper", "--config", str(config_path)])

    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert report["environment"] == "incomplete"
    assert report["paper_full_text"] == "present_unreviewed"
    assert report["research_status"] == "ecc2025_source_audited"


def test_doctor_rejects_wrong_or_structurally_invalid_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test-root'\n", encoding="utf-8")
    config_path = write_config(tmp_path / "doctor.yaml")
    private_references = tmp_path / "references" / "private"
    private_references.mkdir(parents=True)
    (private_references / "some_other_paper.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    (private_references / cli.EXPECTED_ANCHOR_FILENAME).write_bytes(b"not a PDF")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_package_versions", lambda: {"numpy": "2.0"})
    monkeypatch.setattr(cli, "_environment_issues", lambda versions: ([], ["CLARABEL", "OSQP"]))

    result = cli.run(["doctor", "--strict-paper", "--config", str(config_path)])

    report = json.loads(capsys.readouterr().out)
    assert result == 3
    assert report["paper_full_text"] == "invalid"
    assert report["research_status"] == "G0_blocked_on_full_text"


@pytest.mark.parametrize("command", ["simulate", "benchmark"])
def test_qp_usv_combination_is_rejected_before_writing(
    command: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.run(
            [
                command,
                "--controller",
                "qp",
                "--model",
                "usv",
                "--output",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert "holonomic robots only" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("iterations,exit_code", [(10000, 0), (1, 4)])
def test_cli_qp_saves_mission_evidence_before_exit(
    iterations: int,
    exit_code: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.run(
        [
            "simulate",
            "--scenario",
            "nominal",
            "--robots",
            "2",
            "--duration",
            "5",
            "--controller",
            "qp",
            "--qp-max-iter",
            str(iterations),
            "--no-figures",
            "--output",
            str(tmp_path),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert result == exit_code
    assert report["failure_count"] == (3 if exit_code else 0)
    assert set(report["mission_status"]) == {"sweep", "greedy", "adaptive"}
    output = Path(report["output"])
    assert (output / "DONE").is_file()
    saved = json.loads((output / "comparison.json").read_text())
    assert saved["status"] == report["status"]
    assert saved["config"]["qp_max_iter"] == iterations


def test_cli_failed_benchmark_reports_path_then_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.run(
        [
            "benchmark",
            "--controller",
            "qp",
            "--qp-max-iter",
            "1",
            "--duration",
            "5",
            "--robots",
            "2",
            "--seeds",
            "7",
            "--scenarios",
            "nominal",
            "--output",
            str(tmp_path),
        ]
    )
    assert result == 4
    assert "Benchmark:" in capsys.readouterr().out
    reports = list(tmp_path.glob("benchmark-*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert len(report["records"]) == report["failure_count"] == 3


@pytest.mark.parametrize("command", ["simulate", "benchmark"])
@pytest.mark.parametrize("methods", ["", "dp,dp", "sweep,unknown", "sweep,"])
def test_cli_rejects_invalid_method_selection_before_writing(
    command: str, methods: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.run([command, "--methods", methods, "--output", str(tmp_path)]) == 2
    assert "nonempty unique selection" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_cli_rejects_dp_usv_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.run(["simulate", "--methods", "dp", "--model", "usv", "--output", str(tmp_path)]) == 2
    )
    assert "the original turn-in-place USV has no heading-state MDP" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_cli_rejects_managed_usv_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.run(["simulate", "--methods", "p", "--model", "usv", "--output", str(tmp_path)]) == 2
    assert "the original turn-in-place USV has no heading-state MDP" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_cli_curvature_usv_runs_the_planners(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ["simulate", "--model", "usv_curvature", "--robots", "2", "--duration", "5"]
    arguments += ["--scenario", "nominal", "--methods", "dp,p", "--no-figures"]
    assert cli.run([*arguments, "--output", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    comparison = json.loads((Path(report["output"]) / "comparison.json").read_text())
    assert comparison["config"]["model"] == "usv_curvature"
    assert comparison["config"]["dp_motion_primitives"] is True
    assert [run["status"] for run in comparison["runs"]] == ["completed", "completed"]
    assert cli.run([*arguments, "--controller", "qp", "--output", str(tmp_path / "qp")]) == 2
    assert "holonomic" in capsys.readouterr().err


def test_cli_dp_method_selection_and_configuration_roundtrip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.run(
            [
                "simulate",
                "--methods",
                "sweep,greedy,adaptive,dp",
                "--robots",
                "2",
                "--duration",
                "5",
                "--controller",
                "qp",
                "--scenario",
                "nominal",
                "--dp-horizon-steps",
                "2",
                "--dp-grid-nx",
                "4",
                "--dp-grid-ny",
                "3",
                "--dp-travel-weight",
                "0.02",
                "--no-figures",
                "--output",
                str(tmp_path),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["selected_methods"] == ["sweep", "greedy", "adaptive", "dp"]
    output = Path(report["output"])
    comparison = json.loads((output / "comparison.json").read_text())
    assert comparison["config"]["dp_grid_shape"] == [4, 3]
    assert comparison["config"]["dp_horizon_steps"] == 2
    assert comparison["config"]["dp_travel_weight"] == 0.02
    assert comparison["runs"][-1]["method"] == "dp"
    assert (output / "dp" / "plans.json").is_file()
    assert (output / "dp" / "planned_samples.parquet").is_file()


def test_reserved_commands_name_the_open_source_topics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.run(["reproduce"]) == 2
    captured = capsys.readouterr()
    # Every topic is audited, so the message reports none open and still points at the
    # itemised report. These commands belong to the M6-M8 research gates; the ECC source
    # profile has its own, explicitly qualitative, ``ecc-profile`` command.
    assert "ECC source topics still open: none" in captured.err
    assert "doctor --source-report" in captured.err


def test_doctor_reports_the_itemised_ecc_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = write_config(tmp_path / "doctor.yaml")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_package_versions", lambda: {"numpy": "2.0"})
    monkeypatch.setattr(cli, "_environment_issues", lambda versions: ([], ["CLARABEL", "OSQP"]))

    assert cli.run(["doctor", "--config", str(config_path)]) == 0

    audit = json.loads(capsys.readouterr().out)["ecc2025_audit"]
    assert audit["topics_total"] == 9
    assert audit["topics_verified"] == 9
    assert audit["topics_blocked"] == 0
    assert audit["blocked_topic_ids"] == []
    assert audit["reproduction_available"] is True
    # Settings the paper omits stay recorded even once every topic is audited.
    assert len(audit["unstated_in_source"]) == 9


def test_doctor_source_report_states_the_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = write_config(tmp_path / "doctor.yaml")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path)

    assert cli.run(["doctor", "--source-report", "--config", str(config_path)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ecc2025_profile_implemented_qualitative_comparison"
    assert report["open_topics"] == []
    assert len(report["audited_topics"]) == 9
    assert len(report["unstated_in_source"]) == 9
    # Independent results are reported separately from the paper's.
    assert "separately" in report["independent_profile"]


def test_ecc_profile_writes_a_paired_record_with_figures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ["ecc-profile", "--duration", "20", "--start", "edge", "--scale", "figure"]
    assert cli.run([*arguments, "--output", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "not a numerical reproduction" in output
    (destination,) = tmp_path.iterdir()
    assert destination.name.endswith("-figure-edge-s7")
    assert {path.name for path in destination.iterdir()} == {
        "e0.json.gz",
        "e1.json.gz",
        "summary.json",
        "figures",
    }
    assert len(list((destination / "figures").glob("pair_*.png"))) == 3
    summary = json.loads((destination / "summary.json").read_text(encoding="utf-8"))
    assert summary["configuration"]["start_center"] == [0.0, 58.0]
    assert summary["configuration"]["signal_variance"] == 4.0
    assert summary["E0"]["status"] == summary["E1"]["status"] == "completed"
    assert summary["E1"]["J0"] == pytest.approx(3600.0)
    assert any("qualitative" in limit for limit in summary["claim_limits"])


def test_ecc_profile_can_skip_figures(tmp_path: Path) -> None:
    arguments = ["ecc-profile", "--duration", "10", "--no-figures"]
    assert cli.run([*arguments, "--output", str(tmp_path)]) == 0
    (destination,) = tmp_path.iterdir()
    assert not (destination / "figures").exists()


@pytest.mark.parametrize("arguments", [["--duration", "0.05"], ["--seed", "-1"]])
def test_ecc_profile_rejects_invalid_settings_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], arguments: list[str]
) -> None:
    output = tmp_path / "ecc"
    assert cli.run(["ecc-profile", *arguments, "--output", str(output)]) == 2
    assert "ecc profile error:" in capsys.readouterr().err
    assert not output.exists()
