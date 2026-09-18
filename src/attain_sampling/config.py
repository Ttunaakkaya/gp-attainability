"""Small, strict configuration loader for research infrastructure.

Paper-specific configuration deliberately lives outside this schema until Gate 0 is
complete. The loader rejects unknown keys so spelling mistakes cannot silently alter an
experiment.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a project configuration violates the declared schema."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConfigError("YAML mapping keys must be hashable") from exc
        if duplicate:
            raise ConfigError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _as_mapping(value: object, section: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{section} must be a mapping")
    return value


def _require_exact_keys(mapping: Mapping[str, Any], expected: set[str], section: str) -> None:
    actual = {str(key) for key in mapping}
    missing = expected - actual
    unknown = actual - expected
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing={sorted(missing)}")
        if unknown:
            details.append(f"unknown={sorted(unknown)}")
        raise ConfigError(f"invalid keys in {section}: {', '.join(details)}")


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ConfigError(f"{name} must be finite and positive")
    return result


def _non_empty_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value.strip()


def _repository_relative_path(value: object, name: str) -> Path:
    raw = _non_empty_text(value, name)
    result = Path(raw)
    if result.is_absolute() or result == Path(".") or ".." in result.parts:
        raise ConfigError(f"{name} must be a non-empty repository-relative path")
    return result


@dataclass(frozen=True, slots=True)
class ClockConfig:
    """Periods for the deterministic integer-tick event scheduler."""

    control_s: float
    sampling_s: float
    planning_s: float
    logging_s: float

    def validate(self) -> None:
        for name, period in (
            ("control_s", self.control_s),
            ("sampling_s", self.sampling_s),
            ("planning_s", self.planning_s),
            ("logging_s", self.logging_s),
        ):
            if isinstance(period, bool) or not math.isfinite(period) or period <= 0.0:
                raise ConfigError(f"{name} must be finite and positive")

        for name, period in (
            ("sampling_s", self.sampling_s),
            ("planning_s", self.planning_s),
            ("logging_s", self.logging_s),
        ):
            ratio = period / self.control_s
            ticks = round(ratio)
            if ticks < 1 or not math.isclose(ratio, ticks, rel_tol=0.0, abs_tol=1e-9):
                raise ConfigError(f"{name} must be an integer multiple of control_s")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ClockConfig:
        expected = {"control_s", "sampling_s", "planning_s", "logging_s"}
        _require_exact_keys(raw, expected, "clocks")
        clocks = cls(
            control_s=_positive_float(raw["control_s"], "clocks.control_s"),
            sampling_s=_positive_float(raw["sampling_s"], "clocks.sampling_s"),
            planning_s=_positive_float(raw["planning_s"], "clocks.planning_s"),
            logging_s=_positive_float(raw["logging_s"], "clocks.logging_s"),
        )
        clocks.validate()
        return clocks


@dataclass(frozen=True, slots=True)
class PathConfig:
    """Repository-relative paths used by infrastructure commands."""

    output_root: Path
    private_reference_root: Path

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> PathConfig:
        expected = {"output_root", "private_reference_root"}
        _require_exact_keys(raw, expected, "paths")
        return cls(
            output_root=_repository_relative_path(raw["output_root"], "paths.output_root"),
            private_reference_root=_repository_relative_path(
                raw["private_reference_root"], "paths.private_reference_root"
            ),
        )


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Gate-independent project settings."""

    schema_version: int
    name: str
    phase: str
    master_seed: int
    clocks: ClockConfig
    paths: PathConfig

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ProjectConfig:
        expected = {"schema_version", "name", "phase", "master_seed", "clocks", "paths"}
        _require_exact_keys(raw, expected, "root")

        schema_version = raw["schema_version"]
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ConfigError("schema_version must be an integer")
        if schema_version != 1:
            raise ConfigError(f"unsupported schema_version={schema_version}")

        master_seed = raw["master_seed"]
        if isinstance(master_seed, bool) or not isinstance(master_seed, int):
            raise ConfigError("master_seed must be an integer")
        if master_seed < 0:
            raise ConfigError("master_seed must be non-negative")

        name = _non_empty_text(raw["name"], "name")
        phase = _non_empty_text(raw["phase"], "phase")

        return cls(
            schema_version=schema_version,
            name=name,
            phase=phase,
            master_seed=master_seed,
            clocks=ClockConfig.from_mapping(_as_mapping(raw["clocks"], "clocks")),
            paths=PathConfig.from_mapping(_as_mapping(raw["paths"], "paths")),
        )


def load_project_config(path: str | Path) -> ProjectConfig:
    """Load and validate a YAML project configuration."""

    config_path = Path(path)
    try:
        parsed = yaml.load(
            config_path.read_text(encoding="utf-8"),
            Loader=_UniqueKeyLoader,
        )
    except OSError as exc:
        raise ConfigError(f"cannot read config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    return ProjectConfig.from_mapping(_as_mapping(parsed, "root"))
