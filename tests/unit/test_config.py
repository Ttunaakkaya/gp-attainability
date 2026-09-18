from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from attain_sampling.config import ClockConfig, ConfigError, ProjectConfig, load_project_config


def valid_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": "infrastructure-test",
        "phase": "G0_source_lock",
        "master_seed": 42,
        "clocks": {
            "control_s": 0.2,
            "sampling_s": 1.0,
            "planning_s": 2.0,
            "logging_s": 0.4,
        },
        "paths": {
            "output_root": "outputs",
            "private_reference_root": "references/private",
        },
    }


def write_config(path: Path, raw: str) -> Path:
    path.write_text(raw, encoding="utf-8")
    return path


def test_project_config_accepts_exact_valid_schema() -> None:
    config = ProjectConfig.from_mapping(valid_config())

    assert config.schema_version == 1
    assert config.name == "infrastructure-test"
    assert config.phase == "G0_source_lock"
    assert config.master_seed == 42
    assert config.clocks == ClockConfig(0.2, 1.0, 2.0, 0.4)
    assert config.paths.output_root == Path("outputs")
    assert config.paths.private_reference_root == Path("references/private")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda config: config.pop("phase"), "missing=['phase']"),
        (lambda config: config.update({"typo": True}), "unknown=['typo']"),
        (lambda config: config["clocks"].update({"typo": 1}), "invalid keys in clocks"),
        (lambda config: config["paths"].pop("output_root"), "invalid keys in paths"),
    ],
)
def test_project_config_rejects_missing_or_unknown_keys(
    mutation: Any,
    message: str,
) -> None:
    raw = valid_config()
    mutation(raw)

    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        ProjectConfig.from_mapping(raw)


@pytest.mark.parametrize("schema_version", [True, 1.0, "1"])
def test_project_config_rejects_non_integer_schema_version(schema_version: object) -> None:
    raw = valid_config()
    raw["schema_version"] = schema_version

    with pytest.raises(ConfigError, match="schema_version must be an integer"):
        ProjectConfig.from_mapping(raw)


def test_project_config_rejects_unsupported_schema_version() -> None:
    raw = valid_config()
    raw["schema_version"] = 2

    with pytest.raises(ConfigError, match="unsupported schema_version=2"):
        ProjectConfig.from_mapping(raw)


@pytest.mark.parametrize("master_seed", [True, 1.5, "1"])
def test_project_config_rejects_non_integer_master_seed(master_seed: object) -> None:
    raw = valid_config()
    raw["master_seed"] = master_seed

    with pytest.raises(ConfigError, match="master_seed must be an integer"):
        ProjectConfig.from_mapping(raw)


def test_project_config_rejects_negative_master_seed() -> None:
    raw = valid_config()
    raw["master_seed"] = -1

    with pytest.raises(ConfigError, match="master_seed must be non-negative"):
        ProjectConfig.from_mapping(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [("name", "  "), ("phase", ""), ("name", None), ("phase", ["G0"])],
)
def test_project_config_requires_text_name_and_phase(field: str, value: object) -> None:
    raw = valid_config()
    raw[field] = value

    with pytest.raises(ConfigError, match=rf"{field} must be a non-empty string"):
        ProjectConfig.from_mapping(raw)


@pytest.mark.parametrize("value", [True, "0.2", 0.0, -0.2, float("inf"), float("nan")])
def test_clock_config_requires_finite_positive_numbers(value: object) -> None:
    raw = valid_config()
    raw["clocks"]["control_s"] = value

    with pytest.raises(ConfigError, match="clocks.control_s must be"):
        ProjectConfig.from_mapping(raw)


def test_clock_periods_must_be_integer_control_multiples() -> None:
    raw = valid_config()
    raw["clocks"]["sampling_s"] = 0.3

    with pytest.raises(ConfigError, match="sampling_s must be an integer multiple"):
        ProjectConfig.from_mapping(raw)


def test_load_project_config_reads_yaml(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "valid.yaml",
        """
schema_version: 1
name: loaded-config
phase: G0_source_lock
master_seed: 7
clocks:
  control_s: 0.5
  sampling_s: 1.0
  planning_s: 2.0
  logging_s: 0.5
paths:
  output_root: outputs
  private_reference_root: references/private
""".lstrip(),
    )

    config = load_project_config(config_path)

    assert config.name == "loaded-config"
    assert config.master_seed == 7


def test_load_project_config_wraps_yaml_errors(tmp_path: Path) -> None:
    config_path = write_config(tmp_path / "invalid.yaml", "root: [unterminated")

    with pytest.raises(ConfigError, match="invalid YAML"):
        load_project_config(config_path)


def test_load_project_config_wraps_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read config"):
        load_project_config(tmp_path / "missing.yaml")


def test_load_project_config_requires_mapping_root(tmp_path: Path) -> None:
    config_path = write_config(tmp_path / "list.yaml", "- not\n- a\n- mapping\n")

    with pytest.raises(ConfigError, match="root must be a mapping"):
        load_project_config(config_path)


def test_load_project_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "duplicate.yaml",
        "schema_version: 1\nschema_version: 1\n",
    )

    with pytest.raises(ConfigError, match="duplicate YAML key"):
        load_project_config(config_path)


@pytest.mark.parametrize("bad_path", ["../outputs", ".", "", None, True])
def test_project_paths_must_be_non_empty_repository_relative_paths(bad_path: object) -> None:
    raw = valid_config()
    raw["paths"]["output_root"] = bad_path

    with pytest.raises(ConfigError, match="paths.output_root must be"):
        ProjectConfig.from_mapping(raw)


def test_validation_does_not_mutate_source_mapping() -> None:
    raw = valid_config()
    before = deepcopy(raw)

    ProjectConfig.from_mapping(raw)

    assert raw == before
