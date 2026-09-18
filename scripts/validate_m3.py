"""Bounded M3 same-data SOGP replay and closed-loop development validation.

The default is a measured replay plus a representative pilot, not the larger
development matrix. Pass ``--matrix`` explicitly after inspecting pilot costs.
All output paths are unique and all failed closed-loop runs are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from validate_m1 import audit_bundle, audit_run

from attain_sampling.demo.runner import run_comparison, save_comparison, scenario_config
from attain_sampling.gp.exact import ExactGP
from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sim.mapping import segment_min_separation

Belief = ExactGP | SparseOnlineGP


def make_belief(config: dict[str, Any]) -> Belief:
    parameters = {
        "length_scale": config["length_scale"],
        "signal_variance": config["signal_variance"],
        "noise_variance": config["noise_std"] ** 2,
    }
    if config.get("gp_backend", "exact") == "sogp":
        return SparseOnlineGP(
            **parameters,
            max_basis=config["sogp_max_basis"],
            novelty_tolerance=config["sogp_novelty_tolerance"],
        )
    return ExactGP(**parameters)


def received_samples(run: dict[str, Any], time_s: float) -> list[dict[str, Any]]:
    return [
        sample
        for sample in run["samples"]
        if sample["received"] and sample.get("assimilated", True) and sample["time_s"] <= time_s
    ]


def rebuild_belief(run: dict[str, Any], time_s: float) -> Belief:
    gp = make_belief(run["config"])
    samples = received_samples(run, time_s)
    if samples:
        gp.update(
            np.asarray([sample["actual_position"] for sample in samples]),
            np.asarray([sample["value"] for sample in samples]),
        )
    return gp


def query_points(run: dict[str, Any]) -> np.ndarray:
    xx, yy = np.meshgrid(run["field"]["x"], run["field"]["y"])
    return np.column_stack((xx.ravel(), yy.ravel()))


def conditional_variance(gp: Belief, query: np.ndarray, sites: np.ndarray) -> np.ndarray:
    """Independent dense Gaussian conditioning of a frozen current covariance.

    This intentionally does not call the planner's fantasy implementation. For
    SOGP it does not predict future dictionary admission or label-based deletion.
    """
    current = gp.predict(query, variance="latent").variance
    if not len(sites):
        return current
    covariance = gp.posterior_covariance(sites)
    covariance.flat[:: len(sites) + 1] += gp.noise_variance + gp.jitter
    cross = gp.posterior_covariance(query, sites)
    result = current - np.einsum("ij,ji->i", cross, np.linalg.solve(covariance, cross.T))
    assert np.min(result) >= -1e-8 * gp.signal_variance
    return np.maximum(result, 0.0)


def audit_plans(run: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct every chosen prefix and accepted candidate from actual data."""
    config, query = run["config"], query_points(run)
    maximum_error, prefixes, candidates_checked = 0.0, 0, 0
    for plan in run.get("plans", []):
        samples = received_samples(run, plan["generated_at_s"])
        assert plan["received_sample_keys"] == [[s["time_s"], s["robot_id"]] for s in samples]
        assert plan["belief_observation_count"] == len(samples)
        assert plan["mission_end_s"] == config["duration_s"]
        gp = rebuild_belief(run, plan["generated_at_s"])
        previous_variance = float("inf")
        for epoch, forecast in enumerate(plan["forecast"]):
            sites = np.asarray(plan["targets_by_epoch"][:epoch]).reshape(-1, 2)
            variance = conditional_variance(gp, query, sites)
            error = max(
                abs(float(np.mean(variance)) - forecast["mean_variance"]),
                abs(float(np.max(variance)) - forecast["max_variance"]),
            )
            assert error <= 1e-8
            assert forecast["mean_variance"] <= previous_variance + 1e-8
            previous_variance = forecast["mean_variance"]
            maximum_error = max(maximum_error, error)
            prefixes += 1
        previous = np.asarray(plan["start_positions"])
        previous_time = plan["generated_at_s"]
        for sample_time, positions in zip(
            plan["sample_times_s"], plan["targets_by_epoch"], strict=True
        ):
            current = np.asarray(positions)
            assert previous_time < sample_time <= config["duration_s"]
            epoch = sample_time / config["sample_period_s"]
            assert abs(epoch - round(epoch)) <= 1e-9
            assert np.max(np.linalg.norm(current - previous, axis=1)) <= (
                config["max_speed"] * (sample_time - previous_time) + 1e-7
            )
            assert segment_min_separation(previous, current) >= config["min_separation"] - 1e-7
            assert np.all(current >= -1e-8)
            assert np.all(current <= np.asarray(config["domain"]) + 1e-8)
            previous, previous_time = current, sample_time
        accepted = []
        for candidate in plan["candidates"]:
            if candidate["status"] != "accepted":
                assert candidate["rejection_reason"]
                continue
            sites = np.asarray(candidate["targets_by_epoch"]).reshape(-1, 2)
            value = float(np.mean(conditional_variance(gp, query, sites)))
            assert abs(value - candidate["terminal_mean_variance"]) <= 1e-8
            candidates_checked += 1
            accepted.append(candidate)
        if accepted:
            selected = [candidate for candidate in accepted if candidate["selected"]]
            assert len(selected) == 1
            assert selected[0]["candidate_id"] == plan["selected_candidate_id"]
            assert selected[0]["targets_by_epoch"] == plan["targets_by_epoch"]
            assert selected[0]["terminal_mean_variance"] <= (
                min(candidate["terminal_mean_variance"] for candidate in accepted)
                + plan["selection_variance_tolerance"]
            )
        if config.get("gp_backend") == "sogp":
            assert "exact_gp" not in plan["forecast_scope"]
            assert "sogp" in plan["forecast_scope"].lower()
    return {
        "plans": len(run.get("plans", [])),
        "prefixes_recomputed": prefixes,
        "candidates_recomputed": candidates_checked,
        "maximum_prefix_variance_error": maximum_error,
        "conditioning_scope": "independent_dense_conditioning_of_reconstructed_current_posterior",
    }


def _audit_telemetry(telemetry: dict[str, Any], gp: SparseOnlineGP) -> None:
    assert telemetry["backend"] == "sogp"
    assert telemetry["max_basis"] == gp.max_basis
    for key in (
        "observation_count",
        "dictionary_size",
        "admitted_count",
        "projected_count",
        "pruned_count",
        "state_nbytes",
    ):
        assert telemetry[key] == getattr(gp, key)
    assert 0 <= telemetry["dictionary_size"] <= telemetry["max_basis"]
    assert telemetry["admitted_count"] + telemetry["projected_count"] == gp.observation_count
    assert telemetry["admitted_count"] - telemetry["pruned_count"] == gp.dictionary_size


def audit_sogp_run(run: dict[str, Any]) -> dict[str, Any]:
    """Rebuild each frame, check received-only ordered assimilation and capacity."""
    query = query_points(run)
    keys = [(sample["time_s"], sample["robot_id"]) for sample in run["samples"]]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    maximum_mean_error, maximum_variance_error, peak_state = 0.0, 0.0, 0
    for frame in run["frames"]:
        gp = rebuild_belief(run, frame["time_s"])
        predicted = gp.predict(query, variance="latent")
        mean_error = float(np.max(np.abs(np.asarray(frame["mean"]).ravel() - predicted.mean)))
        variance_error = float(
            np.max(np.abs(np.square(np.asarray(frame["std"])).ravel() - predicted.variance))
        )
        assert mean_error <= 1e-8 and variance_error <= 1e-8
        maximum_mean_error = max(maximum_mean_error, mean_error)
        maximum_variance_error = max(maximum_variance_error, variance_error)
        if isinstance(gp, SparseOnlineGP):
            _audit_telemetry(frame["gp_telemetry"], gp)
            peak_state = max(peak_state, gp.state_nbytes)
    final_gp = rebuild_belief(run, run["summary"]["completion_time_s"])
    if isinstance(final_gp, SparseOnlineGP):
        _audit_telemetry(run["gp_telemetry"], final_gp)
        samples = received_samples(run, run["summary"]["completion_time_s"])
        events = run["gp_updates"]
        assert len(events) == final_gp.observation_count == len(samples)
        assert [[event["time_s"], event["robot_id"]] for event in events] == [
            [sample["time_s"], sample["robot_id"]] for sample in samples
        ]
        # A fresh sequential replay verifies core event payloads without relying
        # on simulator counters. The simulator only augments these with clocks.
        replay = make_belief(run["config"])
        assert isinstance(replay, SparseOnlineGP)
        for sample, event in zip(samples, events, strict=True):
            replay.update(np.asarray([sample["actual_position"]]), np.asarray([sample["value"]]))
            assert len(replay.last_update_events) == 1
            expected = replay.last_update_events[0]
            for key, value in expected.items():
                if not key.endswith("_s"):
                    assert event[key] == value, (key, event[key], value)
    return {
        "frames_recomputed": len(run["frames"]),
        "observations_replayed": final_gp.observation_count,
        "maximum_mean_error": maximum_mean_error,
        "maximum_variance_error": maximum_variance_error,
        "peak_frame_state_nbytes": peak_state if isinstance(final_gp, SparseOnlineGP) else None,
    }


def synthetic_stream(count: int = 256, seed: int = 731) -> dict[str, Any]:
    """A shared ordered high-diversity stream; unrelated to policy trajectories."""
    if count < 4 or count % 4:
        raise ValueError("stream count must be a positive multiple of four, at least four")
    rng = np.random.default_rng(seed)
    columns = int(np.ceil(np.sqrt(count * 1.5)))
    rows = int(np.ceil(count / columns))
    xx, yy = np.meshgrid(
        (np.arange(columns) + 0.5) * 60 / columns, (np.arange(rows) + 0.5) * 40 / rows
    )
    points = np.column_stack((xx.ravel(), yy.ravel()))
    points = points[rng.permutation(len(points))[:count]]
    points += rng.uniform(-0.2, 0.2, size=points.shape)
    true_values = np.sin(points[:, 0] / 5.0) * np.cos(points[:, 1] / 7.0) + 0.7 * np.exp(
        -np.sum((points - [34.0, 22.0]) ** 2, axis=1) / 100
    )
    noise = rng.normal(0.0, 0.15, count)
    qx, qy = np.meshgrid(np.linspace(0, 60, 24), np.linspace(0, 40, 16))
    return {
        "seed": seed,
        "scope": "same_data_high_diversity_algorithm_diagnostic_not_closed_loop_field_evidence",
        "parameters": {
            "length_scale": 2.5,
            "signal_variance": 1.0,
            "noise_std": 0.15,
            "sogp_novelty_tolerance": 1e-6,
        },
        "team_size": 4,
        "sample_positions": points.tolist(),
        "true_values": true_values.tolist(),
        "noise": noise.tolist(),
        "observed_values": (true_values + noise).tolist(),
        "sample_keys": [[index // 4, index % 4] for index in range(count)],
        "query_positions": np.column_stack((qx.ravel(), qy.ravel())).tolist(),
    }


def timing_summary(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "sum_s": float(np.sum(values)),
        "median_s": float(np.median(values)),
        "p95_s": float(np.percentile(values, 95)),
        "max_s": float(np.max(values)),
    }


def replay_stream(
    stream: dict[str, Any],
    capacities: tuple[int, ...] = (32, 64, 128),
    *,
    require_pruning: bool = True,
) -> dict[str, Any]:
    """Charge one update plus one query per observation to both backends."""
    points = np.asarray(stream["sample_positions"])
    values = np.asarray(stream["observed_values"])
    query = np.asarray(stream["query_positions"])
    records, exact_checkpoints = [], {}
    checkpoints = sorted(set((1, *range(32, len(points) + 1, 32), len(points))))
    for capacity in (None, *capacities):
        config = {
            **stream["parameters"],
            "gp_backend": "exact" if capacity is None else "sogp",
            "sogp_max_basis": capacity,
        }
        gp = make_belief(config)
        trace, predictions, updates, queries = [], [], [], []
        before = gp.predict(query, variance="latent").variance
        peak_state, maximum_net_jump = 0, 0.0
        for index, (point, value) in enumerate(zip(points, values, strict=True), 1):
            prior_prunes = gp.pruned_count if isinstance(gp, SparseOnlineGP) else 0
            started = time.perf_counter()
            gp.update(point[None], np.asarray([value]))
            update_s = time.perf_counter() - started
            started = time.perf_counter()
            prediction = gp.predict(query, variance="latent")
            query_s = time.perf_counter() - started
            updates.append(update_s)
            queries.append(query_s)
            assert np.all(np.isfinite(prediction.mean)) and np.all(np.isfinite(prediction.variance))
            assert np.min(prediction.variance) >= 0
            pruned = isinstance(gp, SparseOnlineGP) and gp.pruned_count > prior_prunes
            net_jump = float(np.max(prediction.variance - before)) if pruned else None
            if net_jump is not None:
                maximum_net_jump = max(maximum_net_jump, net_jump)
            state = (
                gp.state_nbytes if isinstance(gp, SparseOnlineGP) else (index**2 + 4 * index) * 8
            )
            peak_state = max(peak_state, state)
            trace.append(
                {
                    "observation_count": index,
                    "update_s": update_s,
                    "query_s": query_s,
                    "total_s": update_s + query_s,
                    "dictionary_size": gp.dictionary_size
                    if isinstance(gp, SparseOnlineGP)
                    else None,
                    "state_nbytes": state,
                    "pruned": pruned,
                    "max_net_variance_change_at_pruning_update": net_jump,
                    "events": gp.last_update_events if isinstance(gp, SparseOnlineGP) else [],
                }
            )
            before = prediction.variance.copy()
            if index in checkpoints:
                if capacity is None:
                    exact_checkpoints[index] = prediction
                reference = exact_checkpoints[index]
                predictions.append(
                    {
                        "observation_count": index,
                        "mean": prediction.mean.tolist(),
                        "variance": prediction.variance.tolist(),
                        "mean_rmse_vs_exact": float(
                            np.sqrt(np.mean((prediction.mean - reference.mean) ** 2))
                        ),
                        "variance_mae_vs_exact": float(
                            np.mean(np.abs(prediction.variance - reference.variance))
                        ),
                        "variance_max_abs_vs_exact": float(
                            np.max(np.abs(prediction.variance - reference.variance))
                        ),
                    }
                )
        covariance = gp.posterior_covariance(query[::4])
        minimum_eigenvalue = float(np.min(np.linalg.eigvalsh(covariance)))
        assert minimum_eigenvalue >= -1e-8
        if isinstance(gp, SparseOnlineGP):
            assert gp.dictionary_size <= capacity
            assert gp.admitted_count + gp.projected_count == len(points)
            assert gp.admitted_count - gp.pruned_count == gp.dictionary_size
            if require_pruning:
                assert gp.dictionary_size == capacity and gp.pruned_count > 0
        records.append(
            {
                "backend": config["gp_backend"],
                "capacity": capacity,
                "trace": trace,
                "predictions": predictions,
                "observation_count": gp.observation_count,
                "dictionary_size": gp.dictionary_size if isinstance(gp, SparseOnlineGP) else None,
                "dictionary_observation_indices": gp.dictionary_observation_indices.tolist()
                if isinstance(gp, SparseOnlineGP)
                else None,
                "pruned_count": gp.pruned_count if isinstance(gp, SparseOnlineGP) else 0,
                "projected_count": gp.projected_count if isinstance(gp, SparseOnlineGP) else 0,
                "peak_state_nbytes": peak_state,
                "state_scope": (
                    "persistent_numeric_arrays_only_excludes_python_overhead_and_working_memory"
                ),
                "update_timing": timing_summary(updates),
                "query_timing": timing_summary(queries),
                "update_plus_query_timing": timing_summary(
                    [u + q for u, q in zip(updates, queries, strict=True)]
                ),
                "timing_scope": (
                    "one_update_and_one_full_query_each_observation_including_exact_lazy_factorization"
                ),
                "minimum_checked_covariance_eigenvalue": minimum_eigenvalue,
                "maximum_net_variance_increase_at_pruning_update": maximum_net_jump,
                "variance_jump_scope": (
                    "net_assimilation_plus_prune_on_recorded_query_grid_"
                    "not_isolated_prune_or_global_bound"
                ),
                "maximum_recorded_pure_pruning_variance_increase_at_removed_site": max(
                    (
                        event["pruning_variance_jump"]
                        for row in trace
                        for event in row["events"]
                        if event["pruning_variance_jump"] is not None
                    ),
                    default=0.0,
                ),
            }
        )
        print(
            f"replay: {config['gp_backend']} capacity={capacity}, "
            f"update+query={records[-1]['update_plus_query_timing']['sum_s']:.3f}s, "
            f"pruned={records[-1]['pruned_count']}, state={peak_state} bytes",
            flush=True,
        )
    return {"records": records, "checkpoint_counts": checkpoints}


def ordering_study(stream: dict[str, Any], capacity: int = 32) -> dict[str, Any]:
    points, observed = np.asarray(stream["sample_positions"]), np.asarray(stream["observed_values"])
    query = np.asarray(stream["query_positions"])
    forward = np.arange(len(points))
    reverse = forward.reshape(-1, stream["team_size"])[:, ::-1].ravel()
    records = []
    predictions: dict[tuple[str, str], Any] = {}
    dictionaries: dict[tuple[str, str], list[int]] = {}
    for order_name, order in (("forward", forward), ("reverse_within_epoch", reverse)):
        for label_name, labels in (
            ("observed", observed),
            ("zero_diagnostic", np.zeros_like(observed)),
        ):
            gp = make_belief(
                {**stream["parameters"], "gp_backend": "sogp", "sogp_max_basis": capacity}
            )
            assert isinstance(gp, SparseOnlineGP)
            gp.update(points[order], labels[order])
            prediction = gp.predict(query, variance="latent")
            predictions[order_name, label_name] = prediction
            # Core observation IDs are local update positions; compare physical
            # input identities through the explicit permutation, not raw IDs.
            ids = gp.dictionary_observation_indices
            original_ids = order[np.asarray(ids, dtype=int)].tolist()
            dictionaries[order_name, label_name] = original_ids
            records.append(
                {
                    "order": order_name,
                    "labels": label_name,
                    "update_permutation": order.tolist(),
                    "retained_original_sample_indices_zero_based": original_ids,
                    "mean": prediction.mean.tolist(),
                    "variance": prediction.variance.tolist(),
                    "pruned_count": gp.pruned_count,
                }
            )
    base = predictions["forward", "observed"]
    other_order = predictions["reverse_within_epoch", "observed"]
    other_labels = predictions["forward", "zero_diagnostic"]
    return {
        "capacity": capacity,
        "records": records,
        "canonical_simulator_order": "sample_tick_then_robot_id_ascending",
        "mean_rmse_forward_vs_reverse": float(
            np.sqrt(np.mean((base.mean - other_order.mean) ** 2))
        ),
        "variance_mae_forward_vs_reverse": float(
            np.mean(np.abs(base.variance - other_order.variance))
        ),
        "variance_mae_observed_vs_zero_labels_same_sites_order": float(
            np.mean(np.abs(base.variance - other_labels.variance))
        ),
        "same_labels_different_order_retained_set_equal": set(dictionaries["forward", "observed"])
        == set(dictionaries["reverse_within_epoch", "observed"]),
        "same_order_different_labels_retained_set_equal": set(dictionaries["forward", "observed"])
        == set(dictionaries["forward", "zero_diagnostic"]),
        "scope": "finite_stream_diagnostic_not_general_order_invariance_or_error_bound",
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def forecast_approximation_study(
    stream: dict[str, Any], capacities: tuple[int, ...] = (32, 64, 128), horizon: int = 8
) -> dict[str, Any]:
    """Measure frozen conditioning versus actual subsequent SOGP updates.

    Locations and label values are recorded, so execution/dropout differences
    cannot explain this discrepancy. This is a finite diagnostic, not a bound.
    """
    points, values = np.asarray(stream["sample_positions"]), np.asarray(stream["observed_values"])
    query = np.asarray(stream["query_positions"])
    if horizon < 1 or horizon >= len(points):
        raise ValueError("forecast horizon must leave a nonempty observed prefix")
    prefix = min(200, len(points) - horizon)
    future = points[prefix : prefix + horizon]
    records = []
    for capacity in capacities:
        config = {**stream["parameters"], "gp_backend": "sogp", "sogp_max_basis": capacity}
        current = make_belief(config)
        assert isinstance(current, SparseOnlineGP)
        current.update(points[:prefix], values[:prefix])
        frozen = conditional_variance(current, query, future)
        np.testing.assert_allclose(current.fantasy_variance(query, future), frozen, atol=1e-8)
        for label_name, future_labels in (
            ("observed", values[prefix : prefix + horizon]),
            ("zero_diagnostic", np.zeros(horizon)),
        ):
            future_gp = make_belief(config)
            assert isinstance(future_gp, SparseOnlineGP)
            future_gp.update(points[:prefix], values[:prefix])
            before_prunes = future_gp.pruned_count
            future_gp.update(future, future_labels)
            realized = future_gp.predict(query, variance="latent").variance
            records.append(
                {
                    "capacity": capacity,
                    "future_labels": label_name,
                    "future_label_values": future_labels.tolist(),
                    "frozen_forecast_variance": frozen.tolist(),
                    "actual_future_sogp_variance": realized.tolist(),
                    "variance_mean_absolute_gap": float(np.mean(np.abs(realized - frozen))),
                    "variance_max_absolute_gap": float(np.max(np.abs(realized - frozen))),
                    "signed_mean_variance_gap_actual_minus_frozen": float(
                        np.mean(realized - frozen)
                    ),
                    "future_pruned_count": future_gp.pruned_count - before_prunes,
                }
            )
    return {
        "prefix_count": prefix,
        "horizon_observations": horizon,
        "future_sample_positions": future.tolist(),
        "records": records,
        "scope": (
            "same_future_sites_no_dropout_no_execution_error_"
            "frozen_forecast_is_not_future_SOGP_pruning"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/m3-20260915/validation"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay-only", action="store_true")
    mode.add_argument("--pilot-only", action="store_true")
    mode.add_argument("--matrix", action="store_true")
    parser.add_argument("--seeds", type=int, nargs="+", default=[7])
    parser.add_argument("--observations", type=int, default=256)
    args = parser.parse_args()
    if args.observations < 160 or args.observations % 4:
        parser.error(
            "--observations must be a multiple of four and >= 160 to test capacity 128 pruning"
        )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output.resolve() / f"batch-{stamp}-{uuid.uuid4().hex[:6]}"
    destination.mkdir(parents=True, exist_ok=False)
    for filename in ("validate_m3.py", "validate_m1.py"):
        (destination / filename).write_bytes(Path(__file__).with_name(filename).read_bytes())
    report: dict[str, Any] = {
        "scope": "M3 algorithm_and_closed_loop_development_not_M6_held_out_or_ECC_reproduction",
        "created_at": datetime.now(UTC).isoformat(),
        "records": [],
        "manifest_hashes_checked": 0,
        "complete": False,
    }
    started = time.perf_counter()
    if not args.pilot_only:
        stream = synthetic_stream(args.observations)
        _write_json(destination / "replay_input.json", stream)
        replay = replay_stream(stream)
        replay["ordering_study"] = ordering_study(stream)
        replay["forecast_approximation_study"] = forecast_approximation_study(stream)
        _write_json(destination / "replay.json", replay)
        report["replay_path"] = "replay.json"
    jobs = []
    if not args.replay_only:
        jobs = [
            ("pilot", 4, "combined", 7, 300.0, backend, 64, ("adaptive", "dp"))
            for backend in ("exact", "sogp")
        ]
    if args.matrix:
        jobs += [
            (
                "matrix",
                robots,
                scenario,
                seed,
                90.0,
                backend,
                capacity,
                ("sweep", "greedy", "adaptive", "dp"),
            )
            for robots, scenario, seed, (backend, capacity) in product(
                (2, 4),
                ("nominal", "combined"),
                args.seeds,
                (("exact", 64), ("sogp", 32), ("sogp", 64), ("sogp", 128)),
            )
        ]
    for phase, robots, scenario, seed, duration, backend, capacity, methods in jobs:
        config = scenario_config(
            scenario,
            robots=robots,
            seed=seed,
            duration_s=duration,
            controller="qp",
            gp_backend=backend,
            sogp_max_basis=capacity,
        )
        comparison = run_comparison(config, scenario=scenario, methods=methods)
        bundle = save_comparison(comparison, destination / phase)
        restored, verified = audit_bundle(bundle)
        report["manifest_hashes_checked"] += verified
        for run in restored["runs"]:
            report["records"].append(
                {
                    "phase": phase,
                    "robots": robots,
                    "scenario": scenario,
                    "seed": seed,
                    "duration_s": duration,
                    "controller": "qp",
                    "gp_backend": backend,
                    "sogp_max_basis": capacity,
                    "method": run["method"],
                    "path": str(bundle),
                    "status": run["status"],
                    "failure": run["failure"],
                    "summary": run["summary"],
                    "gp_telemetry": run["gp_telemetry"],
                    "audit": audit_run(run),
                    "gp_audit": audit_sogp_run(run),
                    "plan_audit": audit_plans(run),
                }
            )
        _write_json(destination / "validation.json", report)
        print(
            f"{phase}: {robots} robots {scenario} seed={seed} {backend} M={capacity}: "
            f"{comparison['runtime_s']:.3f}s compute, {comparison['status']}; {bundle}",
            flush=True,
        )
    report["complete"] = True
    report["failure_count"] = sum(record["status"] == "failed" for record in report["records"])
    report["elapsed_including_io_s"] = time.perf_counter() - started
    _write_json(destination / "validation.json", report)
    manifest = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in destination.iterdir()
        if path.is_file()
    }
    _write_json(destination / "validation_manifest.json", manifest)
    print(
        f"Validated {len(report['records'])} closed-loop runs: {destination / 'validation.json'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
