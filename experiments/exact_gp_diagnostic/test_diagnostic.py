"""Meaningful numerical/model checks; run: python -m unittest -v."""
import itertools
import json
from pathlib import Path
import unittest

import numpy as np

from diagnostic import (ExactGP, enumerate_routes, exhaustive_plan, greedy_plan,
                        joint_successors, missed_sample_experiment,
                        route_is_feasible, route_observations, exhaustive_robust_plan,
                        route_dropout_audit, dropout_scenarios)


class GPTests(unittest.TestCase):
    def setUp(self):
        self.gp = ExactGP(range(7))

    def test_batch_cholesky_matches_sequential_repeated_and_joint(self):
        for observations in [(), (3,), (3, 3), (1, 5), (3, 1, 5, 1, 5, 3), (0, 6, 2, 4, 2, 2)]:
            with self.subTest(observations=observations):
                np.testing.assert_allclose(self.gp.batch_covariance(observations),
                                           self.gp.sequential_covariance(observations), atol=2e-14, rtol=2e-13)

    def test_independent_simultaneous_updates_are_order_invariant(self):
        reference = self.gp.sequential_covariance((3, 1, 5, 1))
        for observations in set(itertools.permutations((3, 1, 5, 1))):
            np.testing.assert_allclose(reference, self.gp.sequential_covariance(observations), atol=2e-14)

    def test_repeated_noisy_scalar_analytic_formula(self):
        gp = ExactGP([0], signal_variance=1.7, noise_variance=0.3)
        for count in [0, 1, 2, 5, 20, 100]:
            analytic = 1 / (1 / 1.7 + count / 0.3)
            self.assertAlmostEqual(gp.batch_covariance((0,) * count)[0, 0], analytic, places=13)
            self.assertAlmostEqual(gp.sequential_covariance((0,) * count)[0, 0], analytic, places=13)
        self.assertLess(1 / (1 / 1.7 + 100000 / 0.3), 3e-6)

    def test_posterior_positive_semidefinite_and_information_nonincreasing(self):
        before = self.gp.batch_covariance((3,))
        after = self.gp.batch_covariance((3, 1, 5, 1, 5))
        self.assertGreaterEqual(float(np.linalg.eigvalsh(after).min()), -1e-12)
        self.assertGreaterEqual(float(np.linalg.eigvalsh(before - after).min()), -1e-12)


class RouteTests(unittest.TestCase):
    def test_feasibility_rejects_collisions_swaps_and_fast_moves(self):
        self.assertFalse(route_is_feasible((1, 2), ((2, 1),), 7))
        self.assertFalse(route_is_feasible((1, 3), ((2, 2),), 7))
        self.assertFalse(route_is_feasible((1, 5), ((3, 5),), 7))
        self.assertTrue(route_is_feasible((1, 5), ((1, 5), (2, 4), (2, 3)), 7))

    def test_successors_match_independent_cartesian_filter(self):
        for current in [(1, 2), (0, 6), (2, 5)]:
            expected = set()
            for a, b in itertools.product(range(7), repeat=2):
                if abs(a-current[0]) <= 1 and abs(b-current[1]) <= 1 and a != b:
                    if (a, b) != (current[1], current[0]):
                        expected.add((a, b))
            self.assertEqual(set(joint_successors(current, 7)), expected)

    def test_enumeration_is_complete_on_independent_tiny_fixture(self):
        initial, node_count, horizon = (0, 3), 4, 2
        expected = set()
        for flat in itertools.product(range(node_count), repeat=4):
            route = (flat[:2], flat[2:])
            if route_is_feasible(initial, route, node_count):
                expected.add(route)
        enumerated = list(enumerate_routes(initial, node_count, horizon))
        self.assertEqual(set(enumerated), expected)
        self.assertEqual(len(enumerated), len(expected))

    def test_exhaustive_optimum_is_minimum_and_not_above_greedy(self):
        gp = ExactGP(range(5))
        initial, obs, horizon = (0, 4), (2,), 3
        optimum = exhaustive_plan(gp, initial, obs, horizon)
        greedy = greedy_plan(gp, initial, obs, horizon)
        self.assertTrue(route_is_feasible(initial, optimum["route"], 5))
        self.assertTrue(route_is_feasible(initial, greedy["route"], 5))
        self.assertLessEqual(optimum["terminal_variance"], greedy["terminal_variance"] + 1e-12)
        for route in enumerate_routes(initial, 5, horizon):
            self.assertGreaterEqual(gp.integrated_variance(route_observations(obs, route)),
                                    optimum["terminal_variance"] - 1e-12)

    def test_missed_sample_reference_staleness_and_remaining_budget(self):
        config = json.loads((Path(__file__).parent / "config.json").read_text())
        gp = ExactGP(config["nodes"], config["signal_variance"], config["length_scale"], config["noise_variance"])
        optimum = exhaustive_plan(gp, config["initial_positions"], config["initial_observations"], config["horizon_steps"])
        stress = missed_sample_experiment(gp, config["initial_positions"], config["initial_observations"], optimum)
        self.assertGreater(stress["prefix_gap"], 1e-10)
        self.assertGreater(stress["terminal_gap"], 1e-10)
        self.assertTrue(stress["old_target_unattainable_in_this_finite_model"])
        self.assertEqual(stress["scheduled_total_new_samples"], 8)
        self.assertEqual(stress["actual_total_new_samples"], 7)
        self.assertEqual(stress["remaining_samples_after_miss"], 6)
        self.assertTrue(route_is_feasible(stress["physical_positions_after_miss"], stress["replanned_remaining_route"], 7))
        self.assertLessEqual(stress["best_remaining_terminal_variance"],
                             stress["continue_original_route_after_miss_curve"][-1] + 1e-12)

    def test_finite_mask_minmax_dominates_nominal_worst_case(self):
        gp, initial, observations, horizon = ExactGP(range(5)), (0, 4), (2,), 3
        nominal = exhaustive_plan(gp, initial, observations, horizon)
        robust = exhaustive_robust_plan(gp, initial, observations, horizon)
        nominal_audit = route_dropout_audit(gp, observations, nominal["route"])
        self.assertLessEqual(robust["worst_terminal_variance"], nominal_audit["worst_terminal_variance"] + 1e-12)
        self.assertTrue(route_is_feasible(initial, robust["route"], 5))
        # Check every alternative route against the returned exact minimax value.
        for route in enumerate_routes(initial, 5, horizon):
            audit = route_dropout_audit(gp, observations, route)
            self.assertGreaterEqual(audit["worst_terminal_variance"], robust["worst_terminal_variance"] - 1e-12)

    def test_mask_set_complete_and_prefix_envelope_covers_each_mask(self):
        gp, observations, route = ExactGP(range(5)), (2,), ((0, 4), (1, 3), (0, 4))
        masks = list(dropout_scenarios(route))
        self.assertEqual(len(masks), 7)
        self.assertEqual({missing for _, missing in masks}, {None} | set(itertools.product(range(3), range(2))))
        audit = route_dropout_audit(gp, observations, route)
        envelope = np.asarray(audit["prefix_envelope"])
        for scenario in audit["scenarios"]:
            self.assertTrue(np.all(np.asarray(scenario["prefix_variance"]) <= envelope + 1e-12))
            # Independent sequential conditioning checks every masked prefix.
            data = list(observations)
            for step, positions in enumerate(route):
                data.extend(node for robot, node in enumerate(positions) if (step, robot) != scenario["missing"])
                expected = float(np.trace(gp.sequential_covariance(data)) / 5)
                self.assertAlmostEqual(expected, scenario["prefix_variance"][step + 1], places=13)


if __name__ == "__main__":
    unittest.main()
