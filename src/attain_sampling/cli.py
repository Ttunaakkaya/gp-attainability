"""Command-line interface and explicit research-gate guards."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from attain_sampling.config import ConfigError, ProjectConfig, load_project_config
from attain_sampling.sources.ecc2025 import audit_status, blocked_topics, difference_report

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
# The M5 source-profile configurations; see scripts/validate_m5.py and decisions D042-D043.
ECC_STARTS = {"paper": (0.0, 75.0), "edge": (0.0, 58.0)}
ECC_SCALES = {"theorem": 1.0, "figure": 4.0}
EXPECTED_ANCHOR_FILENAME = "suenaga_et_al_ecc2025.pdf"
REQUIRED_PACKAGES = {
    "clarabel": "clarabel",
    "cvxpy": "cvxpy",
    "imageio": "imageio",
    "imageio-ffmpeg": "imageio_ffmpeg",
    "matplotlib": "matplotlib",
    "networkx": "networkx",
    "numpy": "numpy",
    "osqp": "osqp",
    "pyarrow": "pyarrow",
    "pyyaml": "yaml",
    "scipy": "scipy",
    "seaborn": "seaborn",
    "shapely": "shapely",
    "zarr": "zarr",
}
DEFAULT_CONFIG_DATA = {
    "schema_version": 1,
    "name": "attainable-gp-sampling-smoke",
    "phase": "G0_source_lock",
    "master_seed": 20260901,
    "clocks": {
        "control_s": 0.2,
        "sampling_s": 10.0,
        "planning_s": 20.0,
        "logging_s": 10.0,
    },
    "paths": {
        "output_root": "outputs",
        "private_reference_root": "references/private",
    },
}


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in REQUIRED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "MISSING"
    return versions


def _environment_issues(versions: dict[str, str]) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    if sys.version_info[:2] != (3, 11):
        issues.append(f"python_requires_3.11_found_{platform.python_version()}")

    for distribution, module in REQUIRED_PACKAGES.items():
        if versions.get(distribution) == "MISSING":
            issues.append(f"missing_distribution:{distribution}")
            continue
        try:
            importlib.import_module(module)
        except Exception as exc:  # pragma: no cover - depends on the local binary stack
            issues.append(f"import_failed:{module}:{type(exc).__name__}")

    installed_solvers: list[str] = []
    if "missing_distribution:cvxpy" not in issues and not any(
        issue.startswith("import_failed:cvxpy") for issue in issues
    ):
        cvxpy = importlib.import_module("cvxpy")
        installed_solvers = sorted(str(solver) for solver in cvxpy.installed_solvers())
        for required_solver in ("CLARABEL", "OSQP"):
            if required_solver not in installed_solvers:
                issues.append(f"missing_cvxpy_solver:{required_solver}")
    return issues, installed_solvers


def _paper_pdf_status(reference_root: Path) -> tuple[str, Path]:
    paper_path = reference_root / EXPECTED_ANCHOR_FILENAME
    if not paper_path.is_file():
        return "missing", paper_path
    try:
        size = paper_path.stat().st_size
        with paper_path.open("rb") as stream:
            header = stream.read(5)
            if size >= 4096:
                stream.seek(-4096, 2)
            else:
                stream.seek(0)
            trailer = stream.read()
    except OSError:
        return "invalid", paper_path
    if size < 1024 or header != b"%PDF-" or b"%%EOF" not in trailer:
        return "invalid", paper_path
    return "present_unreviewed", paper_path


def _find_repository_root(config_path: Path | None) -> Path:
    starts: list[Path] = []
    if config_path is not None:
        starts.append(config_path.resolve().parent)
    starts.extend((REPOSITORY_ROOT.resolve(), Path.cwd().resolve()))
    visited: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in visited:
                continue
            visited.add(candidate)
            if (candidate / "pyproject.toml").is_file():
                return candidate
    return Path.cwd().resolve()


def _doctor(config_path: Path | None, *, strict_paper: bool, source_report: bool = False) -> int:
    try:
        config = (
            ProjectConfig.from_mapping(DEFAULT_CONFIG_DATA)
            if config_path is None
            else load_project_config(config_path)
        )
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    repository_root = _find_repository_root(config_path)
    reference_root = repository_root / config.paths.private_reference_root
    versions = _package_versions()
    environment_issues, installed_solvers = _environment_issues(versions)
    paper_status, paper_path = _paper_pdf_status(reference_root)
    if source_report:
        # The M5 deliverable while the anchor text is absent: a stated, itemised gap.
        print(json.dumps(difference_report(), indent=2, sort_keys=True))
        return 0 if paper_status != "invalid" else 2

    result = {
        "config": "built-in:development/smoke" if config_path is None else str(config_path),
        "repository_root": str(repository_root),
        "python": platform.python_version(),
        "environment": "ready" if not environment_issues else "incomplete",
        "environment_issues": environment_issues,
        "independent_application": "ready" if not environment_issues else "incomplete",
        "paper_gate_applies_to": "ECC reproduction only; independent demo is not gated",
        "cvxpy_solvers": installed_solvers,
        "gate": config.phase,
        "paper_full_text": paper_status,
        "paper_path": str(paper_path),
        "ecc2025_audit": audit_status(),
        "research_status": (
            "G0_blocked_on_full_text"
            if paper_status != "present_unreviewed"
            else "G0_audit_pending"
            if blocked_topics()
            else "ecc2025_source_audited"
        ),
        "package_versions": versions,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if environment_issues:
        return 2
    if strict_paper and paper_status != "present_unreviewed":
        return 3
    return 0


def _reserved_command(command: str) -> int:
    blocked = blocked_topics()
    detail = ", ".join(topic.topic_id for topic in blocked) if blocked else "none"
    print(
        f"'{command}' is reserved but locked: complete the documented research gates "
        f"first. ECC source topics still open: {detail}. "
        "Run 'doctor --source-report' for the itemised gap.",
        file=sys.stderr,
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="attain-sampling")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check environment and Gate 0 inputs")
    doctor.add_argument("--config", type=Path)
    doctor.add_argument("--strict-paper", action="store_true")
    doctor.add_argument("--source-report", action="store_true")

    validate = subparsers.add_parser("validate-config", help="validate infrastructure YAML")
    validate.add_argument("config", type=Path)

    demo = subparsers.add_parser("demo", help="start the independent local mapping dashboard")
    demo.add_argument("--port", type=int, default=8765)
    demo.add_argument("--output", type=Path, default=Path("outputs/mapping"))

    for name in ("simulate", "benchmark"):
        simulation = subparsers.add_parser(name, help=f"independent paired mapping {name}")
        simulation.add_argument(
            "--scenario", choices=("nominal", "dropout", "drift", "combined"), default="combined"
        )
        simulation.add_argument("--robots", type=int, choices=(2, 3, 4), default=3)
        simulation.add_argument("--seed", type=int, default=7)
        simulation.add_argument("--duration", type=float, default=90.0)
        simulation.add_argument(
            "--model", choices=("holonomic", "usv", "usv_curvature"), default="holonomic"
        )
        simulation.add_argument(
            "--gp-backend",
            choices=("exact", "sogp"),
            default="exact",
            help="exact reference (default), or M3 bounded sparse-online GP",
        )
        simulation.add_argument("--sogp-max-basis", type=int, default=64)
        simulation.add_argument("--sogp-novelty-tolerance", type=float, default=1e-6)
        simulation.add_argument(
            "--controller",
            choices=("filter", "qp"),
            default="filter",
            help="reference filter (default), or M1 holonomic tracking QP",
        )
        simulation.add_argument("--qp-alpha", type=float, default=1.0)
        simulation.add_argument("--qp-polygon-sides", type=int, default=16)
        simulation.add_argument("--qp-max-iter", type=int, default=10000)
        simulation.add_argument("--qp-acceptance-tol", type=float, default=1e-7)
        simulation.add_argument(
            "--methods",
            default="sweep,greedy,adaptive",
            help="comma-separated unique methods; opt in to M2 with sweep,greedy,adaptive,dp",
        )
        simulation.add_argument("--dp-horizon-steps", type=int, default=4)
        simulation.add_argument("--dp-grid-nx", type=int, default=9)
        simulation.add_argument("--dp-grid-ny", type=int, default=7)
        simulation.add_argument("--dp-travel-weight", type=float, default=0.01)
        # The three M4 ablations of masterplan v2 section 10 are plain flags.
        simulation.add_argument("--p-no-rollout", dest="p_controller_rollout", action="store_false")
        simulation.add_argument("--p-no-retain", dest="p_retain_plan", action="store_false")
        simulation.add_argument("--p-periodic-only", dest="p_event_triggers", action="store_false")
        simulation.add_argument("--p-deviation-trigger", type=float, default=1.5)
        simulation.add_argument("--p-intervention-trigger", type=float, default=0.25)
        simulation.add_argument("--p-switch-margin", type=float, default=0.01)
        simulation.add_argument("--p-max-rollout-candidates", type=int, default=6)
        simulation.add_argument("--target-mean-variance", type=float, default=None)
        simulation.add_argument("--output", type=Path, default=Path("outputs/mapping"))
        if name == "benchmark":
            simulation.add_argument("--seeds", default="7,19,31")
            simulation.add_argument("--scenarios", default="nominal,dropout,drift,combined")
        else:
            simulation.add_argument("--no-figures", action="store_true")

    for name in ("record", "export"):
        export = subparsers.add_parser(name, help="render from saved independent comparison data")
        export.add_argument("input", type=Path, help="path to comparison.json")
        if name == "record":
            export.add_argument("--seconds", type=float, default=30.0)
            export.add_argument("--fps", type=int, default=12)
            export.add_argument("--output", type=Path)
        else:
            export.add_argument("--output", type=Path)

    ecc = subparsers.add_parser(
        "ecc-profile",
        help="ECC 2025 source profile: constraint-only vs hierarchical, qualitative only",
    )
    ecc.add_argument("--seed", type=int, default=7)
    ecc.add_argument(
        "--start",
        choices=tuple(ECC_STARTS),
        default="paper",
        help="paper: the starting square (0, 75); edge: (0, 58), a recorded sensitivity",
    )
    ecc.add_argument(
        "--scale",
        choices=tuple(ECC_SCALES),
        default="theorem",
        help="theorem: k(x,x) = 1 as in Theorem 1; figure: k(x,x) = 4 as Figs. 3 and 6 suggest",
    )
    ecc.add_argument("--duration", type=float, default=1000.0)
    ecc.add_argument("--output", type=Path, default=Path("outputs/ecc2025"))
    ecc.add_argument("--no-figures", action="store_true")

    for command in ("reproduce", "compare", "figures"):
        subparsers.add_parser(command, help=f"reserved {command} contract (currently locked)")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"demo", "simulate", "benchmark", "record", "export"}:
        # Before numerical imports: keep the CPU workload predictable on laptops.
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(variable, "1")
        try:
            return _independent_command(args)
        except (ValueError, OSError) as exc:
            print(f"independent simulation error: {exc}", file=sys.stderr)
            return 2
    if args.command == "ecc-profile":
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(variable, "1")
        try:
            return _ecc_profile_command(args)
        except (ValueError, OSError) as exc:
            print(f"ecc profile error: {exc}", file=sys.stderr)
            return 2
    if args.command == "doctor":
        return _doctor(
            args.config, strict_paper=args.strict_paper, source_report=args.source_report
        )
    if args.command == "validate-config":
        try:
            config = load_project_config(args.config)
        except ConfigError as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2
        print(f"valid schema v{config.schema_version}: {config.name} ({config.phase})")
        return 0
    return _reserved_command(str(args.command))


def _ecc_profile_command(args: argparse.Namespace) -> int:
    """Run one paired E0/E1 source-profile comparison and save it with its figures."""
    import gzip
    from datetime import UTC, datetime

    from attain_sampling.sim.ecc2025 import CONTROLLERS, EccProfileConfig, run_ecc_profile

    # Build both configurations first so invalid settings fail before anything is written.
    configs = {
        controller: EccProfileConfig(
            controller=controller,
            seed=args.seed,
            duration_s=args.duration,
            signal_variance=ECC_SCALES[args.scale],
            start_center=ECC_STARTS[args.start],
        )
        for controller in CONTROLLERS
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output / f"{stamp}-{args.scale}-{args.start}-s{args.seed}"
    destination.mkdir(parents=True, exist_ok=False)
    runs = {}
    for controller, config in configs.items():
        runs[controller] = run_ecc_profile(config)
        tag = "e0" if controller == "constraint_only" else "e1"
        with gzip.open(destination / f"{tag}.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(runs[controller], stream, allow_nan=False)
    e0, e1 = runs["constraint_only"], runs["hierarchical"]
    summary = {
        "scope": "ECC 2025 source profile; qualitative comparison, not a numerical reproduction",
        "configuration": {
            "seed": args.seed,
            "start": args.start,
            "start_center": list(ECC_STARTS[args.start]),
            "scale": args.scale,
            "signal_variance": ECC_SCALES[args.scale],
            "duration_s": args.duration,
        },
        "E0": {"status": e0["status"], "failure": e0["failure"], **e0["summary"]},
        "E1": {"status": e1["status"], "failure": e1["failure"], **e1["summary"]},
        "project_choices": e1["project_choices"],
        "claim_limits": e1["claim_limits"],
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    if not args.no_figures:
        from attain_sampling.sim.ecc2025_figures import render_ecc_pair

        render_ecc_pair(e0, e1, destination / "figures", "pair")
    for label, run in (("E0 constraint-only (10)", e0), ("E1 hierarchical (17)", e1)):
        values = run["summary"]
        print(
            f"{label}: {run['status']} at {run['completed_time_s']:g} s, "
            f"J {values['J0']:.0f} -> {values['final_J']:.1f}, "
            f"MSE {values['initial_mse']:.0f} -> {values['final_mse']:.1f}"
        )
    print("Qualitative source-profile comparison; not a numerical reproduction of the paper.")
    print(f"Saved: {destination.resolve()}")
    return 0 if e0["status"] == e1["status"] == "completed" else 4


def _independent_command(args: argparse.Namespace) -> int:
    if args.command == "demo":
        from attain_sampling.demo.server import serve

        serve(args.port, args.output)
        return 0
    if args.command in {"record", "export"}:
        from attain_sampling.demo.render import load_comparison, render_figures, render_video

        comparison = load_comparison(args.input)
        if args.command == "record":
            output = args.output or args.input.parent / "demo.mp4"
            render_video(comparison, output, seconds=args.seconds, fps=args.fps)
            print(f"Video: {output.resolve()}")
        else:
            output = args.output or args.input.parent / "figures"
            print(render_figures(comparison, output))
        return 0

    from attain_sampling.demo.runner import (
        benchmark,
        run_comparison,
        save_comparison,
        scenario_config,
    )

    config = scenario_config(
        args.scenario,
        robots=args.robots,
        seed=args.seed,
        duration_s=args.duration,
        model=args.model,
        gp_backend=args.gp_backend,
        sogp_max_basis=args.sogp_max_basis,
        sogp_novelty_tolerance=args.sogp_novelty_tolerance,
        controller=args.controller,
        qp_alpha=args.qp_alpha,
        qp_polygon_sides=args.qp_polygon_sides,
        qp_max_iter=args.qp_max_iter,
        qp_acceptance_tol=args.qp_acceptance_tol,
        dp_horizon_steps=args.dp_horizon_steps,
        dp_grid_shape=(args.dp_grid_nx, args.dp_grid_ny),
        dp_travel_weight=args.dp_travel_weight,
        p_controller_rollout=args.p_controller_rollout,
        p_retain_plan=args.p_retain_plan,
        p_event_triggers=args.p_event_triggers,
        p_deviation_trigger_m=args.p_deviation_trigger,
        p_intervention_trigger_mps=args.p_intervention_trigger,
        p_switch_margin=args.p_switch_margin,
        p_max_rollout_candidates=args.p_max_rollout_candidates,
        target_mean_variance=args.target_mean_variance,
    )
    methods = tuple(method.strip() for method in args.methods.split(","))
    if args.command == "benchmark":
        result = benchmark(
            config,
            seeds=[int(seed) for seed in args.seeds.split(",")],
            scenarios=args.scenarios.split(","),
            output_root=args.output,
            methods=methods,
        )
        print(f"Benchmark: {result['report_path']}")
        return 4 if result["failure_count"] else 0
    result = run_comparison(config, scenario=args.scenario, methods=methods)
    destination = save_comparison(result, args.output)
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "status": result["status"],
                "failure_count": result["failure_count"],
                "selected_methods": result["selected_methods"],
                "runtime_s": result["runtime_s"],
                "output": str(destination),
                "mission_status": {
                    run["method"]: {"status": run["status"], "failure": run["failure"]}
                    for run in result["runs"]
                },
                "summary": {run["method"]: run["summary"] for run in result["runs"]},
            },
            indent=2,
        )
    )
    if not args.no_figures:
        from attain_sampling.demo.render import render_figures

        render_figures(result, destination / "figures")
    return 4 if result["failure_count"] else 0


def main() -> None:
    raise SystemExit(run())
