"""M7 curvature USV: shortest forward paths, arcs, loiter circles and the certified filter."""

from __future__ import annotations

import math

import numpy as np
import pytest

from attain_sampling.sim import usv

RADIUS = 2.0 / 0.45
DOMAIN = (60.0, 40.0)


def _turn_straight(ends, heads, target):
    best = np.full(len(ends), np.inf)
    for turn in (1.0, -1.0):
        centre = ends + turn * RADIUS * np.stack((-np.sin(heads), np.cos(heads)), axis=-1)
        offset = target - centre
        distance = np.hypot(offset[:, 0], offset[:, 1])
        straight = np.sqrt(np.maximum(distance**2 - RADIUS**2, 0.0))
        tangent = np.arctan2(offset[:, 1], offset[:, 0]) - turn * np.arctan2(straight, RADIUS)
        arc = np.mod(turn * (tangent - (heads - turn * math.pi / 2)), 2 * math.pi)
        arc = np.where(arc > 2 * math.pi - 1e-9, 0.0, arc)
        best = np.minimum(best, np.where(distance >= RADIUS, RADIUS * arc + straight, np.inf))
    return best


def _brute_force(position, heading, target, samples=8000):
    """Shortest turn-turn-straight path by searching the first arc on a fine grid."""
    arcs = np.linspace(0, 2 * math.pi, samples, endpoint=False)
    best = math.inf
    for turn in (1.0, -1.0):
        ends, heads = usv.integrate_arc(
            np.repeat(position[None], samples, axis=0),
            np.full(samples, heading),
            RADIUS * arcs,
            np.full(samples, turn / RADIUS),
        )
        best = min(best, float(np.min(RADIUS * arcs + _turn_straight(ends, heads, target))))
    return best


def test_turn_radius_follows_the_speed_and_yaw_rate_bounds():
    assert usv.turn_radius(2.0, 0.45) == pytest.approx(RADIUS)
    for speed, rate in ((0.0, 1.0), (1.0, -1.0), (math.inf, 1.0)):
        with pytest.raises(ValueError):
            usv.turn_radius(speed, rate)


@pytest.mark.parametrize("seed", range(6))
def test_point_path_is_never_longer_than_a_brute_force_search(seed):
    rng = np.random.default_rng(seed)
    for _ in range(12):
        position = rng.uniform(0, 30, 2)
        heading = float(rng.uniform(-math.pi, math.pi))
        target = position + rng.normal(0, rng.choice([1.0, 5.0, 15.0]), 2)
        path = usv.point_path(position, np.asarray(heading), target, RADIUS)
        brute = _brute_force(position, heading, target)
        # The brute force searches a superset on a grid: it can only be longer.
        assert float(path.length) <= brute + 1e-9
        assert float(path.length) >= brute - 0.01


def test_point_path_geometry_ends_at_the_target_with_its_arrival_heading():
    rng = np.random.default_rng(11)
    for _ in range(40):
        position = rng.uniform(0, 30, 2)
        heading = float(rng.uniform(-math.pi, math.pi))
        target = position + rng.normal(0, 8.0, 2)
        path = usv.point_path(position, np.asarray(heading), target, RADIUS)
        points = usv.sample_point_path(
            position, heading, target, RADIUS, np.asarray([1 - 1e-7, 1.0])
        )
        np.testing.assert_allclose(points[-1], target, atol=1e-9)
        direction = math.atan2(*(points[1] - points[0])[::-1])
        error = (direction - float(path.arrival_heading) + math.pi) % (2 * math.pi) - math.pi
        assert abs(error) < 1e-4


def test_simple_point_paths():
    origin = np.zeros(2)
    ahead = usv.point_path(origin, np.asarray(0.0), np.asarray([10.0, 0.0]), RADIUS)
    assert float(ahead.length) == pytest.approx(10.0)
    assert float(ahead.first_arc) == 0.0 and float(ahead.straight) == pytest.approx(10.0)
    same = usv.point_path(origin, np.asarray(0.3), origin, RADIUS)
    assert float(same.length) == 0.0 and float(same.arrival_heading) == pytest.approx(0.3)
    behind = usv.point_path(origin, np.asarray(0.0), np.asarray([-20.0, 0.0]), RADIUS)
    # Behind the vehicle the path must turn: longer than the straight distance.
    assert float(behind.length) > 20.0 + RADIUS
    batch = usv.point_path(
        np.zeros((3, 2)), np.zeros(3), np.asarray([[10.0, 0], [0, 10.0], [-10.0, 0]]), RADIUS
    )
    assert batch.length.shape == (3,)
    assert batch.length[0] == pytest.approx(10.0)


def test_integrate_arc_matches_the_circle_and_the_straight_limit():
    end, heading = usv.integrate_arc(
        np.zeros((1, 2)), np.zeros(1), np.asarray([math.pi * RADIUS]), np.asarray([1 / RADIUS])
    )
    np.testing.assert_allclose(end[0], [0.0, 2 * RADIUS], atol=1e-12)
    assert abs(abs(float(heading[0])) - math.pi) < 1e-12
    end, heading = usv.integrate_arc(
        np.zeros((1, 2)), np.asarray([0.5]), np.asarray([3.0]), np.asarray([1e-12])
    )
    np.testing.assert_allclose(end[0], 3.0 * np.asarray([math.cos(0.5), math.sin(0.5)]))
    points = usv.arc_points(
        np.zeros((2, 2)), np.zeros(2), np.asarray([4.0, 0.0]), np.asarray([0.2, 0.0])
    )
    assert points.shape == (usv.SAMPLES_PER_STEP + 1, 2, 2)
    np.testing.assert_allclose(points[:, 1], 0.0)


def test_chord_deviation_bounds_the_arc_and_rejects_large_turns():
    length, curvature = 2.0, 1 / RADIUS
    bound = float(usv.chord_deviation(np.asarray([length]), np.asarray([curvature]))[0])
    start = np.zeros((1, 2))
    points = usv.arc_points(start, np.zeros(1), np.asarray([length]), np.asarray([curvature]))[:, 0]
    fractions = np.linspace(0, 1, len(points))[:, None]
    chord = points[0] + fractions * (points[-1] - points[0])
    assert float(np.max(np.linalg.norm(points - chord, axis=1))) <= bound
    with pytest.raises(ValueError):
        usv.chord_deviation(np.asarray([100.0]), np.asarray([1.0]))


@pytest.mark.parametrize("seed", [0, 1])
def test_arc_bounds_are_exact_for_straight_and_turning_arcs(seed):
    rng = np.random.default_rng(seed)
    count = 3000
    positions = rng.uniform(-10, 10, (count, 2))
    headings = rng.uniform(-math.pi, math.pi, count)
    lengths = rng.uniform(0, 40, count)
    curvatures = rng.choice([0.0, 1.0, -1.0], count) / RADIUS * rng.uniform(0.3, 1.0, count)
    low, high = usv.arc_bounds(positions, headings, lengths, curvatures)
    dense = usv.arc_points(positions, headings, lengths, curvatures, samples=4000)
    assert np.all(low <= dense.min(axis=0) + 1e-12)
    assert np.all(high >= dense.max(axis=0) - 1e-12)
    # Tight up to the sampling resolution of the dense reference.
    assert np.max(dense.min(axis=0) - low) < 1e-5
    assert np.max(high - dense.max(axis=0)) < 1e-5
    # A quarter circle turning left from the origin heading east.
    low, high = usv.arc_bounds(
        np.zeros((1, 2)), np.zeros(1), np.asarray([RADIUS * math.pi / 2]), np.asarray([1 / RADIUS])
    )
    np.testing.assert_allclose(low, [[0.0, 0.0]], atol=1e-12)
    np.testing.assert_allclose(high, [[RADIUS, RADIUS]])


def test_viable_needs_a_turning_circle_inside_the_field():
    left, right = usv.viable(
        np.asarray([[RADIUS + 1, 20.0], [0.5, 20.0]]), np.asarray([0.0, 0.0]), RADIUS, DOMAIN
    )
    assert bool(left[0]) and bool(right[0])
    assert not bool(left[1]) and not bool(right[1])


def _starts(count):
    return np.column_stack(
        (
            RADIUS + 1 + (np.arange(count) % 2) * (2 * RADIUS + 2.0),
            (np.arange(count) + 0.35) * DOMAIN[1] / count,
        )
    )


def test_loiter_assignment_finds_private_circles_or_reports_none():
    starts = _starts(4)
    choice = usv.loiter_assignment(
        starts, np.zeros(4), radius=RADIUS, domain=DOMAIN, min_separation=2.0
    )
    assert choice is not None
    centres = usv.loiter_centres(starts, np.zeros(4), RADIUS)[np.arange(4), choice]
    gaps = np.linalg.norm(centres[:, None] - centres[None], axis=2)[np.triu_indices(4, 1)]
    assert np.all(gaps >= 2 * RADIUS + 2.0 - 1e-9)
    crowded = np.asarray([[20.0, 20.0], [23.0, 20.0]])
    assert (
        usv.loiter_assignment(
            crowded, np.zeros(2), radius=RADIUS, domain=DOMAIN, min_separation=2.0
        )
        is None
    )
    preferred = usv.loiter_assignment(
        np.asarray([[30.0, 20.0]]),
        np.zeros(1),
        radius=RADIUS,
        domain=DOMAIN,
        min_separation=2.0,
        preference=np.asarray([-1.0]),
    )
    assert preferred is not None and int(preferred[0]) == 1


def test_guidance_stops_at_the_target_and_asks_for_timed_arrival():
    speed, curvature, length = usv.guidance(
        np.asarray([[10.0, 10.0], [10.0, 10.0]]),
        np.zeros(2),
        np.asarray([[10.02, 10.0], [20.0, 10.0]]),
        radius=RADIUS,
        max_speed=2.0,
        dt=0.5,
        tracking_time_s=10.0,
    )
    assert speed[0] == 0.0 and speed[1] == pytest.approx(1.0)
    assert curvature[1] == 0.0 and length[1] == pytest.approx(10.0)
    behind, turning, _ = usv.guidance(
        np.asarray([[30.0, 20.0]]),
        np.zeros(1),
        np.asarray([[20.0, 20.0]]),
        radius=RADIUS,
        max_speed=2.0,
        dt=0.5,
        tracking_time_s=None,
    )
    assert behind[0] == pytest.approx(2.0)
    assert abs(turning[0]) == pytest.approx(1 / RADIUS)


@pytest.mark.parametrize("seed", range(3))
def test_filter_keeps_every_invariant_in_closed_loop(seed):
    rng = np.random.default_rng(seed)
    positions, headings = _starts(4), np.zeros(4)
    lower = np.asarray([RADIUS + 0.5] * 2)
    upper = np.asarray(DOMAIN) - lower
    moved = 0.0
    for step in range(240):
        if step % 20 == 0:
            targets = rng.uniform(lower, upper, (4, 2))
        speeds, curvatures, _ = usv.guidance(
            positions,
            headings,
            targets,
            radius=RADIUS,
            max_speed=2.0,
            dt=0.5,
            tracking_time_s=(20 - step % 20) * 0.5,
        )
        curvatures = np.clip(curvatures + rng.normal(0, 0.09, 4), -1 / RADIUS, 1 / RADIUS)
        result = usv.filter_step(
            positions,
            headings,
            speeds,
            curvatures,
            radius=RADIUS,
            domain=DOMAIN,
            min_separation=2.0,
            dt=0.5,
        )
        assert np.all(result.positions >= 0) and np.all(result.positions <= np.asarray(DOMAIN))
        assert result.chord_separation is not None and result.chord_separation >= 2.0 - 1e-9
        assert result.certified_separation is not None
        assert result.certified_separation >= 2.0 - usv.ARC_SEPARATION_TOLERANCE_M
        assert (
            usv.loiter_assignment(
                result.positions, result.headings, radius=RADIUS, domain=DOMAIN, min_separation=2.0
            )
            is not None
        )
        assert np.all(result.speeds <= 2.0 + 1e-12)
        assert np.all(np.abs(result.curvatures) <= 1 / RADIUS + 1e-12)
        moved += float(np.sum(np.linalg.norm(result.positions - positions, axis=1)))
        positions, headings = result.positions, result.headings
    # The fleet keeps moving: a filter that stops robots would pass the checks above.
    assert moved > 0.5 * 240 * 4 * 1.0


def test_filter_leaves_a_clear_command_alone_and_loiters_near_the_wall():
    positions = np.asarray([[30.0, 20.0]])
    result = usv.filter_step(
        positions,
        np.zeros(1),
        np.asarray([2.0]),
        np.asarray([0.0]),
        radius=RADIUS,
        domain=DOMAIN,
        min_separation=2.0,
        dt=0.5,
    )
    assert not result.intervention and result.certified_separation is None
    np.testing.assert_allclose(result.positions[0], [31.0, 20.0])
    near_wall = usv.filter_step(
        np.asarray([[60.0 - RADIUS - 0.2, 20.0]]),
        np.zeros(1),
        np.asarray([2.0]),
        np.asarray([0.0]),
        radius=RADIUS,
        domain=DOMAIN,
        min_separation=2.0,
        dt=0.5,
    )
    assert near_wall.intervention and bool(near_wall.loitering[0])
    assert abs(float(near_wall.curvatures[0])) == pytest.approx(1 / RADIUS)


def test_filter_refuses_states_outside_its_invariant():
    kwargs = {"radius": RADIUS, "domain": DOMAIN, "min_separation": 2.0, "dt": 0.5}
    with pytest.raises(ValueError, match="outside the field"):
        usv.filter_step(np.asarray([[-1.0, 5.0]]), np.zeros(1), np.ones(1), np.zeros(1), **kwargs)
    with pytest.raises(ValueError, match="minimum separation"):
        usv.filter_step(
            np.asarray([[20.0, 20.0], [21.0, 20.0]]), np.zeros(2), np.ones(2), np.zeros(2), **kwargs
        )
    with pytest.raises(ValueError, match="loiter circle"):
        usv.filter_step(np.asarray([[1.0, 1.0]]), np.zeros(1), np.ones(1), np.zeros(1), **kwargs)
