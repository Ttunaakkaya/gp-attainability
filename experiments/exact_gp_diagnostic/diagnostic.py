"""Exact-GP tiny-world diagnostic. Run: python diagnostic.py

Dependencies: Python >= 3.10 and NumPy. No SciPy, training or GPU needed.
All candidate routes are enumerated; no approximate optimization is used.
Covariance calculations condition on locations, not synthetic observations y.
With fixed kernel/noise this is exactly the covariance of a Gaussian posterior.
"""
from __future__ import annotations

import csv
from functools import lru_cache
import itertools
import json
from pathlib import Path
import platform
import time

import numpy as np

ROOT = Path(__file__).resolve().parent


class ExactGP:
    def __init__(self, nodes, signal_variance=1.0, length_scale=1.3, noise_variance=0.25):
        self.nodes = np.asarray(nodes, dtype=float)
        self.noise = float(noise_variance)
        if self.noise <= 0 or length_scale <= 0 or signal_variance <= 0:
            raise ValueError("Kernel and noise parameters must be positive")
        distance = self.nodes[:, None] - self.nodes[None, :]
        self.prior = signal_variance * np.exp(-0.5 * (distance / length_scale) ** 2)

    def batch_covariance(self, observation_indices):
        return self._cached_covariance(tuple(sorted(int(i) for i in observation_indices)))

    @lru_cache(maxsize=None)
    def _cached_covariance(self, indices):
        if not indices:
            posterior = self.prior.copy()
        else:
            ids = np.asarray(indices, dtype=int)
            gram = self.prior[np.ix_(ids, ids)] + self.noise * np.eye(len(ids))
            chol = np.linalg.cholesky(gram)
            solved = np.linalg.solve(chol, self.prior[ids, :])
            posterior = self.prior - solved.T @ solved
        posterior = 0.5 * (posterior + posterior.T)
        posterior.setflags(write=False)
        return posterior

    def sequential_covariance(self, observation_indices):
        posterior = self.prior.copy()
        for i in observation_indices:
            column = posterior[:, i].copy()
            posterior -= np.outer(column, column) / (posterior[i, i] + self.noise)
        return 0.5 * (posterior + posterior.T)

    def integrated_variance(self, observation_indices):
        # Uniform unit-spaced graph quadrature, normalized by node count.
        return float(np.trace(self.batch_covariance(observation_indices)) / len(self.nodes))


def joint_successors(positions, node_count):
    """Labeled robots, legal simultaneous moves; pairwise swaps forbidden."""
    options = [range(max(0, p - 1), min(node_count - 1, p + 1) + 1) for p in positions]
    for candidate in itertools.product(*options):
        if len(set(candidate)) != len(candidate):
            continue
        if any(candidate[i] == positions[j] and candidate[j] == positions[i]
               for i in range(len(positions)) for j in range(i + 1, len(positions))):
            continue
        yield candidate


def route_is_feasible(initial_positions, route, node_count):
    previous = tuple(initial_positions)
    if len(set(previous)) != len(previous) or any(p < 0 or p >= node_count for p in previous):
        return False
    for step in route:
        if tuple(step) not in set(joint_successors(previous, node_count)):
            return False
        previous = tuple(step)
    return True


def route_observations(initial_observations, route):
    return tuple(initial_observations) + tuple(i for positions in route for i in positions)


def enumerate_routes(initial_positions, node_count, horizon):
    if horizon == 0:
        yield ()
        return
    for positions in joint_successors(tuple(initial_positions), node_count):
        for suffix in enumerate_routes(positions, node_count, horizon - 1):
            yield (positions,) + suffix


def exhaustive_plan(gp, initial_positions, observations, horizon):
    best_route = None
    best_objective = float("inf")
    route_count = 0
    for route in enumerate_routes(initial_positions, len(gp.nodes), horizon):
        route_count += 1
        objective = gp.integrated_variance(route_observations(observations, route))
        # Lexicographic enumeration gives a deterministic tie rule.
        if objective < best_objective - 1e-12:
            best_route, best_objective = route, objective
    return {"route": best_route, "terminal_variance": best_objective,
            "enumerated_routes": route_count}


def greedy_plan(gp, initial_positions, observations, horizon):
    positions = tuple(initial_positions)
    accumulated = tuple(observations)
    route = []
    for _ in range(horizon):
        best = min(joint_successors(positions, len(gp.nodes)),
                   key=lambda state: (round(gp.integrated_variance(accumulated + state), 12), state))
        route.append(best)
        accumulated += best
        positions = best
    return {"route": tuple(route), "terminal_variance": gp.integrated_variance(accumulated)}


def prefix_variances(gp, observations, route):
    values = [gp.integrated_variance(observations)]
    accumulated = tuple(observations)
    for positions in route:
        accumulated += tuple(positions)
        values.append(gp.integrated_variance(accumulated))
    return values


def dropout_scenarios(route):
    """Every independent identity mask: no miss or exactly one missing sample."""
    yield "none", None
    for step, positions in enumerate(route):
        for robot in range(len(positions)):
            yield f"step{step + 1}_robot{robot}", (step, robot)


def masked_prefix_variances(gp, observations, route, missing):
    accumulated = tuple(observations)
    values = [gp.integrated_variance(accumulated)]
    for step, positions in enumerate(route):
        accumulated += tuple(node for robot, node in enumerate(positions) if (step, robot) != missing)
        values.append(gp.integrated_variance(accumulated))
    return values


def route_dropout_audit(gp, observations, route):
    scenarios = [{"mask": label, "missing": missing,
                  "prefix_variance": masked_prefix_variances(gp, observations, route, missing)}
                 for label, missing in dropout_scenarios(route)]
    envelope = np.max([scenario["prefix_variance"] for scenario in scenarios], axis=0).tolist()
    return {"worst_terminal_variance": envelope[-1], "prefix_envelope": envelope,
            "scenarios": scenarios}


def exhaustive_robust_plan(gp, initial_positions, observations, horizon):
    """Min over all open-loop routes, max over no/one-miss masks (finite only)."""
    best_route, best_worst = None, float("inf")
    count = 0
    for route in enumerate_routes(initial_positions, len(gp.nodes), horizon):
        count += 1
        flat = tuple(node for positions in route for node in positions)
        # No miss cannot exceed a missed-sample variance (PSD information update).
        # Include it explicitly anyway, rather than depending on that theorem.
        scenario_data = [tuple(observations) + flat]
        scenario_data.extend(tuple(observations) + flat[:i] + flat[i + 1:] for i in range(len(flat)))
        worst = max(gp.integrated_variance(data) for data in scenario_data)
        if worst < best_worst - 1e-12:
            best_route, best_worst = route, worst
    return {"route": best_route, "worst_terminal_variance": best_worst,
            "nominal_terminal_variance": gp.integrated_variance(route_observations(observations, best_route)),
            "enumerated_routes": count, "masks_per_route": 1 + horizon * len(initial_positions),
            "route_mask_pairs": count * (1 + horizon * len(initial_positions))}


def missed_sample_experiment(gp, initial_positions, observations, planned, step=1, robot=0):
    route = planned["route"]
    if step != 1:
        raise ValueError("This bounded fixture deliberately misses a first-step sample")
    actual_first = tuple(p for r, p in enumerate(route[0]) if r != robot)
    actual_observations = tuple(observations) + actual_first
    replanned = exhaustive_plan(gp, route[0], actual_observations, len(route) - 1)
    planned_curve = prefix_variances(gp, observations, route)
    continued_curve = [planned_curve[0]] + prefix_variances(gp, actual_observations, route[1:])
    repaired_curve = [planned_curve[0]] + prefix_variances(gp, actual_observations, replanned["route"])
    return {
        "missed_step": step,
        "missed_robot": robot,
        "missed_node": route[0][robot],
        "physical_positions_after_miss": route[0],
        "actual_observations_after_miss": actual_observations,
        "planned_prefix_variance": planned_curve[1],
        "actual_prefix_variance": repaired_curve[1],
        "prefix_gap": repaired_curve[1] - planned_curve[1],
        "original_terminal_target": planned["terminal_variance"],
        "best_remaining_terminal_variance": replanned["terminal_variance"],
        "terminal_gap": replanned["terminal_variance"] - planned["terminal_variance"],
        "old_target_unattainable_in_this_finite_model": bool(replanned["terminal_variance"] > planned["terminal_variance"] + 1e-10),
        "remaining_enumerated_routes": replanned["enumerated_routes"],
        "replanned_remaining_route": replanned["route"],
        "planned_curve": planned_curve,
        "continue_original_route_after_miss_curve": continued_curve,
        "replanned_curve": repaired_curve,
        "remaining_steps": len(route) - 1,
        "scheduled_total_new_samples": len(route) * len(initial_positions),
        "actual_total_new_samples": len(route) * len(initial_positions) - 1,
        "remaining_samples_after_miss": (len(route) - 1) * len(initial_positions),
    }


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    started = time.perf_counter()
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    gp = ExactGP(config["nodes"], config["signal_variance"], config["length_scale"], config["noise_variance"])
    initial = tuple(config["initial_positions"])
    observations = tuple(config["initial_observations"])
    horizon = config["horizon_steps"]
    optimum = exhaustive_plan(gp, initial, observations, horizon)
    greedy = greedy_plan(gp, initial, observations, horizon)
    stress = missed_sample_experiment(gp, initial, observations, optimum, **config["missed_sample"])
    robust = exhaustive_robust_plan(gp, initial, observations, horizon)
    dropout_audits = {name: route_dropout_audit(gp, observations, route)
                     for name, route in [("nominal_optimum", optimum["route"]),
                                         ("greedy", greedy["route"]), ("robust_optimum", robust["route"])]}
    dropout_rows = [{"method": name, "mask": scenario["mask"], "step": step, "latent_ivar": variance}
                    for name, audit in dropout_audits.items() for scenario in audit["scenarios"]
                    for step, variance in enumerate(scenario["prefix_variance"])]
    write_csv(ROOT / "matched_dropout_scenarios.csv", dropout_rows)
    counts = [0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 10000]
    repeated = []
    prior = config["signal_variance"]
    noise = config["noise_variance"]
    for n in counts:
        latent = 1 / (1 / prior + n / noise)
        sequential = prior
        for _ in range(n):
            sequential -= sequential ** 2 / (sequential + noise)
        repeated.append({"observations": n, "latent_variance": latent,
                         "predictive_variance": latent + noise,
                         "sequential_latent_variance": sequential})
    write_csv(ROOT / "repeated_samples.csv", repeated)
    greedy_curve = prefix_variances(gp, observations, greedy["route"])
    trajectory_rows = []
    replanned_full = (optimum["route"][0],) + tuple(stress["replanned_remaining_route"])
    for t in range(horizon + 1):
        op = initial if t == 0 else optimum["route"][t - 1]
        gr = initial if t == 0 else greedy["route"][t - 1]
        rp = initial if t == 0 else replanned_full[t - 1]
        trajectory_rows.append({"step": t, "optimal_robot0": op[0], "optimal_robot1": op[1],
                                "greedy_robot0": gr[0], "greedy_robot1": gr[1],
                                "replanned_robot0": rp[0], "replanned_robot1": rp[1],
                                "original_optimum_prefix_variance": stress["planned_curve"][t],
                                "greedy_prefix_variance": greedy_curve[t],
                                "miss_then_continue_prefix_variance": stress["continue_original_route_after_miss_curve"][t],
                                "miss_then_replan_prefix_variance": stress["replanned_curve"][t]})
    write_csv(ROOT / "route_prefixes.csv", trajectory_rows)
    matrices = []
    for name, obs in [("prior", ()), ("initial", observations),
                      ("original_optimum_terminal", route_observations(observations, optimum["route"])),
                      ("miss_replanned_terminal", route_observations(stress["actual_observations_after_miss"], stress["replanned_remaining_route"]))]:
        covariance = gp.batch_covariance(obs)
        matrices.extend({"case": name, "row": i, "column": j, "covariance": float(covariance[i, j])}
                        for i in range(len(gp.nodes)) for j in range(len(gp.nodes)))
    write_csv(ROOT / "covariance_arrays.csv", matrices)
    metrics = {
        "scope": config["scope"], "environment": {"python": platform.python_version(), "numpy": np.__version__},
        "initial_integrated_latent_variance": gp.integrated_variance(observations),
        "exhaustive_optimum": optimum, "greedy": greedy,
        "greedy_minus_optimum": greedy["terminal_variance"] - optimum["terminal_variance"],
        "finite_set_robust_optimum": robust,
        "matched_dropout_audits": dropout_audits,
        "nominal_route_worst_minus_robust_route_worst": dropout_audits["nominal_optimum"]["worst_terminal_variance"] - robust["worst_terminal_variance"],
        "missed_sample_stress": stress, "repeated_sample_limit_demo": repeated[-1],
        "fixed_noise_variance": noise, "covariance_cache": gp._cached_covariance.cache_info()._asdict(),
        "elapsed_seconds": time.perf_counter() - started,
        "interpretation": [
            "A feasible route gives an achievable candidate upper bound on the best terminal objective; it is not a lower uncertainty floor.",
            "Exhaustive enumeration identifies the exact minimum only in this finite graph, finite horizon and fixed GP model.",
            "A missed first-step sample leaves the same remaining schedule but one fewer total observation. Revised target acknowledges lost information; it does not prove improved mapping.",
            "Latent variance at a repeatedly observed point can approach zero despite independent measurement noise; predictive variance includes the noise variance.",
            "No y-values or field-error metric are used. There is no claimed reconstruction accuracy or physical safety guarantee."
            ,"The min-max comparison is over fixed open-loop routes and all nine no/one-miss identity masks, using the same scheduled eight samples. A mask removes one sample for every method. It is not a stochastic dropout model or feedback-policy optimality theorem."
        ]
    }
    (ROOT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"optimum": optimum, "greedy": greedy,
                      "robust_optimum": robust,
                      "nominal_route_worst": dropout_audits["nominal_optimum"]["worst_terminal_variance"],
                      "stale_terminal_gap": stress["terminal_gap"],
                      "stale_target_unattainable": stress["old_target_unattainable_in_this_finite_model"],
                      "elapsed_seconds": metrics["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
