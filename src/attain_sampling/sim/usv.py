"""Turn-constrained USV model for M7: forward-only, bounded curvature, may stop.

Masterplan v2 §12 asks the USV transfer to name the vehicle class it represents. This
module implements one explicit class, ``usv_curvature``:

* state ``(x, y, heading)``; controls are a forward speed ``v`` in ``[0, v_max]`` and a
  path curvature ``kappa`` with ``|kappa| <= 1 / R``, so the yaw rate is ``v * kappa``;
* motion is integrated exactly along circular arcs;
* the vehicle may slow to a stop but can never turn on the spot, so a waypoint behind
  it costs a turning manoeuvre of radius at least ``R``.

``R = v_max / max_turn_rate`` keeps the existing turn-rate setting meaningful: at full
speed the yaw-rate bound is the configured one, and at lower speed it shrinks with the
speed. It is a kinematic surrogate, not a hydrodynamic model: there is no current, no
drift of a stopped vehicle, and the disturbance acts on the commanded curvature.

Guidance follows the shortest forward path to the target point with a free arrival
heading (the Dubins point-target problem, whose optimal paths are turn-straight or
turn-turn). The safety filter keeps these invariants on every executed step and
certifies them along the exact arcs:

* **inside the field**, with a margin for the arc's deviation from its chord;
* **private loiter circles**: every robot has one minimum-radius circle inside the field,
  and the chosen circles are at least ``2R + d_min`` apart, so the whole fleet can always
  keep moving by circling without ever meeting;
* **separated** from every other vehicle: the straight chords the audits replay keep the
  minimum distance exactly, and the arcs between them keep it to within 1 mm.

The loiter invariant matters because stopping is not enough for this vehicle class:
two forward-only vehicles that face each other at the minimum distance can never move
again. With private circles the filter never needs to stop anyone. This is a property
of this kinematic model with no current, not a general safety claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from attain_sampling.gp.protocol import FloatArray

BoolArray = NDArray[np.bool_]
IndexArray = NDArray[np.intp]

__all__ = [
    "ArcStep",
    "PointPath",
    "arc_bounds",
    "arc_points",
    "chord_deviation",
    "filter_step",
    "guidance",
    "integrate_arc",
    "loiter_assignment",
    "loiter_centres",
    "point_path",
    "sample_point_path",
    "turn_radius",
    "viable",
]

TWO_PI = 2.0 * math.pi
_ARC_WRAP_TOLERANCE = 1e-9
ARRIVAL_TOLERANCE_M = 0.05
SAMPLES_PER_STEP = 16
SCALES = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.0)
# The recorded straight chords are held to the minimum distance exactly; the arcs
# between them may bulge by at most one sub-interval deviation (about 2e-4 m here),
# which this tolerance covers without charging it at the current, certified state.
ARC_SEPARATION_TOLERANCE_M = 1e-3


def turn_radius(max_speed: float, max_turn_rate: float) -> float:
    """Minimum turning radius implied by the speed and full-speed yaw-rate bounds."""
    if not (math.isfinite(max_speed) and math.isfinite(max_turn_rate)):
        raise ValueError("speed and turn-rate bounds must be finite")
    if max_speed <= 0 or max_turn_rate <= 0:
        raise ValueError("speed and turn-rate bounds must be positive")
    return max_speed / max_turn_rate


def _wrap_positive(angle: FloatArray) -> FloatArray:
    wrapped = np.mod(angle, TWO_PI)
    return np.where(wrapped > TWO_PI - _ARC_WRAP_TOLERANCE, 0.0, wrapped)


@dataclass(frozen=True, slots=True)
class PointPath:
    """Shortest forward path to a point with free arrival heading, per query.

    ``turn`` is the direction of the first arc (+1 left, -1 right) and ``first_arc``
    its length in metres; ``second_turn``/``second_arc`` describe the second arc of a
    turn-turn path (zero for turn-straight); ``straight`` is the straight length.
    """

    length: FloatArray
    arrival_heading: FloatArray
    turn: FloatArray
    first_arc: FloatArray
    second_turn: FloatArray
    second_arc: FloatArray
    straight: FloatArray


def _centres(positions: FloatArray, headings: FloatArray, radius: float, turn: float) -> FloatArray:
    normal = np.stack((-np.sin(headings), np.cos(headings)), axis=-1)
    return positions + turn * radius * normal


def point_path(
    positions: FloatArray, headings: FloatArray, targets: FloatArray, radius: float
) -> PointPath:
    """Vectorised shortest forward path from ``(p, heading)`` to point ``q``.

    The candidate set is left-straight, right-straight, left-right and right-left,
    which contains the optimum of the free-arrival-heading problem; the minimum over
    the feasible candidates is returned. Inputs broadcast to a common leading shape.
    """
    p = np.asarray(positions, dtype=np.float64)
    q = np.asarray(targets, dtype=np.float64)
    theta = np.asarray(headings, dtype=np.float64)
    shape = np.broadcast_shapes(p.shape[:-1], q.shape[:-1], theta.shape)
    p = np.broadcast_to(p, (*shape, 2))
    q = np.broadcast_to(q, (*shape, 2))
    theta = np.broadcast_to(theta, shape)
    r = float(radius)

    best_length = np.full(shape, np.inf)
    arrival = np.zeros(shape)
    turn = np.zeros(shape)
    first = np.zeros(shape)
    second_turn = np.zeros(shape)
    second = np.zeros(shape)
    straight = np.zeros(shape)

    def keep(
        length: FloatArray,
        arrive: FloatArray,
        d1: float,
        a1: FloatArray,
        d2: float,
        a2: FloatArray | float,
        s: FloatArray | float,
    ) -> None:
        better = length < best_length - 1e-12
        np.copyto(best_length, length, where=better)
        np.copyto(arrival, arrive, where=better)
        np.copyto(turn, d1, where=better)
        np.copyto(first, a1, where=better)
        np.copyto(second_turn, d2, where=better)
        np.copyto(second, a2, where=better)
        np.copyto(straight, s, where=better)

    for d in (1.0, -1.0):
        centre = _centres(p, theta, r, d)
        start_angle = theta - d * math.pi / 2
        w = q - centre
        distance = np.hypot(w[..., 0], w[..., 1])
        # Turn-straight: the straight tangent leaves the circle towards q.
        feasible = distance >= r - 1e-12
        clipped = np.maximum(distance, r)
        s = np.sqrt(np.maximum(clipped * clipped - r * r, 0.0))
        gamma = np.arctan2(s, r)
        alpha = np.arctan2(w[..., 1], w[..., 0])
        tangent_angle = alpha - d * gamma
        arc = _wrap_positive(d * (tangent_angle - start_angle))
        length = np.where(feasible, r * arc + s, np.inf)
        keep(length, tangent_angle + d * math.pi / 2, d, r * arc, 0.0, 0.0, s)

        # Turn-turn: a second circle of opposite direction, tangent to the first,
        # passes through q. Its centre is 2R from the first centre and R from q.
        e = distance
        possible = (e >= r - 1e-12) & (e <= 3 * r + 1e-12)
        e_safe = np.where(possible & (e > 1e-12), e, 1.0)
        # Law of cosines in triangle (first centre, q, second centre).
        cos_offset = np.clip((e_safe**2 + 4 * r * r - r * r) / (4 * r * e_safe), -1.0, 1.0)
        offset = np.arccos(cos_offset)
        for sign in (1.0, -1.0):
            angle = alpha + sign * offset
            centre2 = centre + 2 * r * np.stack((np.cos(angle), np.sin(angle)), axis=-1)
            switch_angle = angle  # angle of the switching point seen from the first centre
            arc1 = _wrap_positive(d * (switch_angle - start_angle))
            to_switch = switch_angle + math.pi  # switching point seen from the second centre
            to_q = q - centre2
            q_angle = np.arctan2(to_q[..., 1], to_q[..., 0])
            arc2 = _wrap_positive(-d * (q_angle - to_switch))
            length = np.where(possible, r * (arc1 + arc2), np.inf)
            keep(length, q_angle - d * math.pi / 2, d, r * arc1, -d, r * arc2, 0.0)

    same = np.hypot(*(q - p).reshape(-1, 2).T).reshape(shape) <= 1e-12
    best_length = np.where(same, 0.0, best_length)
    arrival = np.where(same, theta, arrival)
    for array in (first, second, straight):
        np.copyto(array, 0.0, where=same)
    return PointPath(
        length=best_length,
        arrival_heading=np.mod(arrival + math.pi, TWO_PI) - math.pi,
        turn=turn,
        first_arc=first,
        second_turn=second_turn,
        second_arc=second,
        straight=straight,
    )


def integrate_arc(
    positions: FloatArray, headings: FloatArray, lengths: FloatArray, curvatures: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Exact end state after travelling ``lengths`` along arcs of ``curvatures``.

    The chord of an arc with turning angle ``phi`` has length ``L sinc(phi / 2)`` and
    points along the mean heading. That form has no cancellation for small turns, so a
    chord is never longer than its arc beyond rounding.
    """
    p = np.asarray(positions, dtype=np.float64)
    theta = np.asarray(headings, dtype=np.float64)
    length = np.asarray(lengths, dtype=np.float64)
    kappa = np.asarray(curvatures, dtype=np.float64)
    half = 0.5 * kappa * length
    chord = length * np.sinc(half / math.pi)
    direction = theta + half
    end = p + np.stack((chord * np.cos(direction), chord * np.sin(direction)), axis=-1)
    return end, np.mod(theta + 2.0 * half + math.pi, TWO_PI) - math.pi


def arc_points(
    positions: FloatArray,
    headings: FloatArray,
    lengths: FloatArray,
    curvatures: FloatArray,
    samples: int = SAMPLES_PER_STEP,
) -> FloatArray:
    """Points at ``samples + 1`` uniform fractions of each arc: shape (samples+1, n, 2)."""
    fractions = np.linspace(0.0, 1.0, samples + 1)[:, None]
    lengths_by_fraction = fractions * np.asarray(lengths, dtype=np.float64)[None, :]
    points, _ = integrate_arc(
        np.asarray(positions, dtype=np.float64)[None],
        np.asarray(headings, dtype=np.float64)[None],
        lengths_by_fraction,
        np.asarray(curvatures, dtype=np.float64)[None],
    )
    return points


def arc_bounds(
    positions: FloatArray,
    headings: FloatArray,
    lengths: FloatArray,
    curvatures: FloatArray,
) -> tuple[FloatArray, FloatArray]:
    """Exact axis-aligned bounds ``(low, high)`` of each arc, shape (n, 2) each.

    A straight segment is bounded by its end points. A turning arc is bounded by its
    end points and by every circle extreme (east, north, west, south) that the swept
    angle passes through.
    """
    p = np.asarray(positions, dtype=np.float64)
    theta = np.asarray(headings, dtype=np.float64)
    length = np.asarray(lengths, dtype=np.float64)
    kappa = np.asarray(curvatures, dtype=np.float64)
    end, _ = integrate_arc(p, theta, length, kappa)
    low = np.minimum(p, end)
    high = np.maximum(p, end)
    turning = kappa != 0
    if not np.any(turning):
        return low, high
    direction = np.sign(kappa[turning])
    radius = 1.0 / np.abs(kappa[turning])
    heading = theta[turning]
    normal = np.stack((-np.sin(heading), np.cos(heading)), axis=-1)
    centre = p[turning] + (direction * radius)[:, None] * normal
    # Angle of the start point seen from the centre, and the angle swept along the arc.
    start_angle = heading - direction * (math.pi / 2)
    sweep = np.abs(kappa[turning] * length[turning])
    sub_low = low[turning]
    sub_high = high[turning]
    for extreme, axis, sign in ((0.0, 0, 1.0), (0.5, 1, 1.0), (1.0, 0, -1.0), (1.5, 1, -1.0)):
        ahead = np.mod(direction * (extreme * math.pi - start_angle), TWO_PI)
        reached = (ahead <= sweep) | (ahead >= TWO_PI - _ARC_WRAP_TOLERANCE)
        value = centre[:, axis] + sign * radius
        if sign > 0:
            sub_high[:, axis] = np.where(
                reached, np.maximum(sub_high[:, axis], value), sub_high[:, axis]
            )
        else:
            sub_low[:, axis] = np.where(
                reached, np.minimum(sub_low[:, axis], value), sub_low[:, axis]
            )
    low[turning] = sub_low
    high[turning] = sub_high
    return low, high


def chord_deviation(lengths: FloatArray, curvatures: FloatArray) -> FloatArray:
    """Bound on the distance between an arc and its chord at equal fractions.

    Sagitta ``L*phi/8`` plus the along-track mismatch ``L*phi^2/24`` stays below
    ``L*phi/4`` for turning angles ``phi <= 3`` rad.
    """
    length = np.asarray(lengths, dtype=np.float64)
    phi = np.abs(np.asarray(curvatures, dtype=np.float64) * length)
    if np.any(phi > 3.0):
        raise ValueError("a single control step may not turn more than 3 rad")
    return length * phi / 4.0


def viable(
    positions: FloatArray,
    headings: FloatArray,
    radius: float,
    domain: tuple[float, float],
    tolerance: float = 1e-9,
) -> tuple[BoolArray, BoolArray]:
    """Whether the left and right minimum-radius circles lie inside the field."""
    width, height = domain
    results = []
    for d in (1.0, -1.0):
        centre = _centres(np.asarray(positions), np.asarray(headings), radius, d)
        inside = (
            (centre[..., 0] >= radius - tolerance)
            & (centre[..., 0] <= width - radius + tolerance)
            & (centre[..., 1] >= radius - tolerance)
            & (centre[..., 1] <= height - radius + tolerance)
        )
        results.append(inside)
    return results[0], results[1]


def guidance(
    positions: FloatArray,
    headings: FloatArray,
    targets: FloatArray,
    *,
    radius: float,
    max_speed: float,
    dt: float,
    tracking_time_s: float | None,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Speed and curvature that follow the shortest forward path to each target.

    Returns ``(speeds, curvatures, path_lengths)``. Speed asks for arrival at the
    tracking deadline, never earlier; a vehicle within the arrival tolerance stops.
    The curvature reproduces the path's turning over this step (a straight segment
    that starts inside the step is approximated by the average turn).
    """
    path = point_path(positions, headings, targets, radius)
    horizon = dt if tracking_time_s is None else max(float(tracking_time_s), dt)
    speed = np.minimum(max_speed, path.length / horizon)
    speed = np.where(path.length <= ARRIVAL_TOLERANCE_M, 0.0, speed)
    step = speed * dt
    turned = path.turn * np.minimum(step, path.first_arc)
    # A turn-turn path whose first arc ends inside this step starts its second arc.
    remaining = np.maximum(step - path.first_arc, 0.0)
    turned += path.second_turn * np.minimum(remaining, path.second_arc)
    curvature = np.where(step > 0, turned / np.maximum(step, 1e-12) / radius, 0.0)
    curvature = np.clip(curvature, -1.0 / radius, 1.0 / radius)
    return speed, curvature, path.length


def sample_point_path(
    position: FloatArray, heading: float, target: FloatArray, radius: float, fractions: FloatArray
) -> FloatArray:
    """Points along one robot's shortest forward path at the given length fractions."""
    path = point_path(position[None], np.asarray([heading]), target[None], radius)
    total = float(path.length[0])
    points = []
    for fraction in np.asarray(fractions, dtype=np.float64):
        travelled = total * float(fraction)
        state_p, state_h = np.asarray(position, dtype=np.float64)[None], np.asarray([heading])
        segments = (
            (float(path.first_arc[0]), float(path.turn[0]) / radius),
            (float(path.second_arc[0]), float(path.second_turn[0]) / radius),
            (float(path.straight[0]), 0.0),
        )
        for segment_length, kappa in segments:
            portion = min(max(travelled, 0.0), segment_length)
            if portion > 0:
                state_p, state_h = integrate_arc(
                    state_p, state_h, np.asarray([portion]), np.asarray([kappa])
                )
            travelled -= segment_length
        points.append(state_p[0])
    return np.asarray(points)


@dataclass(frozen=True, slots=True)
class ArcStep:
    """One filtered control interval for the whole fleet."""

    positions: FloatArray
    headings: FloatArray
    speeds: FloatArray
    curvatures: FloatArray
    scales: FloatArray
    modified: BoolArray
    loitering: BoolArray
    intervention: bool
    certified_separation: float | None
    chord_separation: float | None


def _sub_deviation(lengths: FloatArray, curvatures: FloatArray) -> FloatArray:
    """Arc-to-chord deviation bound for one sampling sub-interval."""
    sub = np.asarray(lengths, dtype=np.float64) / SAMPLES_PER_STEP
    return chord_deviation(sub, curvatures)


def _segment_distance(start: FloatArray, end: FloatArray) -> FloatArray:
    """Exact closest distance to the origin along straight segments, elementwise."""
    delta = end - start
    squared = np.sum(delta * delta, axis=-1)
    fraction = np.divide(
        -np.sum(start * delta, axis=-1), squared, out=np.zeros_like(squared), where=squared > 0
    )
    closest = start + np.clip(fraction, 0.0, 1.0)[..., None] * delta
    return np.asarray(np.linalg.norm(closest, axis=-1))


def loiter_centres(positions: FloatArray, headings: FloatArray, radius: float) -> FloatArray:
    """Left and right minimum-radius circle centres: shape (robots, 2, 2)."""
    return np.stack(
        (
            _centres(positions, headings, radius, 1.0),
            _centres(positions, headings, radius, -1.0),
        ),
        axis=1,
    )


def loiter_assignment(
    positions: FloatArray,
    headings: FloatArray,
    *,
    radius: float,
    domain: tuple[float, float],
    min_separation: float,
    preference: FloatArray | None = None,
) -> NDArray[np.int64] | None:
    """Pick a private loiter circle for every robot, or report that none exists.

    Each robot needs one of its two minimum-radius circles inside the field, and any
    two chosen circles must have centres at least ``2R + d_min`` apart. Circling on
    such circles keeps every pair at least ``d_min`` apart forever, so a fleet in this
    state always has a safe way to keep moving. Returns 0 (left) or 1 (right) per
    robot, preferring the side of ``preference`` (a signed curvature) when possible.
    """
    centres = loiter_centres(positions, headings, radius)
    width, height = domain
    inside = (
        (centres[..., 0] >= radius - 1e-9)
        & (centres[..., 0] <= width - radius + 1e-9)
        & (centres[..., 1] >= radius - 1e-9)
        & (centres[..., 1] <= height - radius + 1e-9)
    )
    count = len(centres)
    combos = (np.arange(2**count)[:, None] >> np.arange(count)[None, :]) & 1
    ok = np.all(inside[np.arange(count)[None, :], combos], axis=1)
    if count > 1:
        first, second = np.triu_indices(count, k=1)
        gap = np.linalg.norm(
            centres[first][:, :, None, :] - centres[second][:, None, :, :], axis=-1
        )
        chosen = gap[np.arange(len(first))[None, :], combos[:, first], combos[:, second]]
        ok &= np.all(chosen >= 2 * radius + min_separation - 1e-9, axis=1)
    if not np.any(ok):
        return None
    wanted = (
        np.zeros(count, dtype=np.int64)
        if preference is None
        else (np.asarray(preference) < 0).astype(np.int64)
    )
    score = np.where(ok, np.sum(combos == wanted[None, :], axis=1), -1)
    return np.asarray(combos[int(np.argmax(score))], dtype=np.int64)


def filter_step(
    positions: FloatArray,
    headings: FloatArray,
    speeds: FloatArray,
    curvatures: FloatArray,
    *,
    radius: float,
    domain: tuple[float, float],
    min_separation: float,
    dt: float,
) -> ArcStep:
    """Certify one control interval for the fleet, changing only what must change.

    Invariant, checked on entry and kept on exit: every robot is inside the field and
    the fleet has a private loiter circle for every robot (:func:`loiter_assignment`).
    A robot moving along its assigned circle keeps the invariant at any speed and can
    never meet another robot on its own circle, so "everyone loiters" is always a safe
    joint command and no robot ever has to stop.

    Search: each robot starts with its requested curvature at full speed. A robot
    whose own arc would leave the field or end without an inside circle is put on its
    loiter circle. A pair whose arcs fail the separation certificate moves its free
    robots to their next option (loiter circle, opposite full turn, straight) and then
    to lower speeds. If the joint end state has no loiter assignment, free robots are
    put on their loiter circles one at a time, most crowded first.
    """
    p = np.asarray(positions, dtype=np.float64)
    theta = np.asarray(headings, dtype=np.float64)
    v = np.asarray(speeds, dtype=np.float64)
    kappa = np.clip(np.asarray(curvatures, dtype=np.float64), -1.0 / radius, 1.0 / radius)
    bounds = np.asarray(domain, dtype=np.float64)
    count = len(p)
    if np.any(p < -1e-9) or np.any(p > bounds + 1e-9):
        raise ValueError("current state lies outside the field")
    if count > 1:
        first, second = np.triu_indices(count, k=1)
        current_gap = np.linalg.norm(p[first] - p[second], axis=1)
        if float(current_gap.min()) < min_separation - 1e-9:
            raise ValueError("current state violates the minimum separation")
        crowding = np.full(count, np.inf)
        np.minimum.at(crowding, first, current_gap)
        np.minimum.at(crowding, second, current_gap)
        order = [int(robot) for robot in np.argsort(crowding, kind="stable")]
    else:
        order = [0]
    assignment = loiter_assignment(
        p, theta, radius=radius, domain=domain, min_separation=min_separation, preference=kappa
    )
    if assignment is None:
        raise ValueError("current state has no private loiter circle for every robot")
    circle = np.where(assignment == 0, 1.0, -1.0) / radius

    options = [[float(kappa[i]), float(circle[i]), float(-circle[i]), 0.0] for i in range(count)]
    levels = [0] * count
    choices = [0] * count
    loiter = np.zeros(count, dtype=bool)
    moving = v > 0

    def curvature_of(robot: int) -> float:
        return float(circle[robot]) if loiter[robot] else options[robot][choices[robot]]

    def advance(robot: int) -> None:
        choices[robot] += 1
        if choices[robot] >= len(options[robot]):
            choices[robot] = 0
            levels[robot] += 1
            if levels[robot] >= len(SCALES) - 1:
                # Slowest positive speed reached: loiter instead of stopping.
                levels[robot] = len(SCALES) - 2
                loiter[robot] = True

    budget = count * len(SCALES) * (len(options[0]) + 2) + 2 * count + 2
    for _ in range(budget):
        lengths = np.asarray([float(v[i]) * SCALES[levels[i]] * dt for i in range(count)])
        chosen = np.asarray([curvature_of(i) for i in range(count)])
        points = arc_points(p, theta, lengths, chosen)
        end, end_heading = integrate_arc(p, theta, lengths, chosen)
        margin = _sub_deviation(lengths, chosen)
        later = points[1:]
        inside = np.all(
            (later >= margin[None, :, None] - 1e-12)
            & (later <= bounds - margin[None, :, None] + 1e-12),
            axis=(0, 2),
        )
        left, right = viable(end, end_heading, radius, domain)
        own_bad = moving & ~loiter & ~(inside & (left | right))
        if np.any(own_bad):
            loiter[own_bad] = True
            continue
        certified_min: float | None = None
        chord_min: float | None = None
        if count > 1:
            relative = points[:, first] - points[:, second]
            certified = _segment_distance(relative[:-1], relative[1:]).min(axis=0) - (
                margin[first] + margin[second]
            )
            chord = _segment_distance(relative[0], relative[-1])
            failing = (certified < min_separation - ARC_SEPARATION_TOLERANCE_M) | (
                chord < min_separation - 1e-9
            )
            if np.any(failing):
                involved = {
                    int(robot)
                    for pair in np.flatnonzero(failing)
                    for robot in (first[pair], second[pair])
                    if moving[int(robot)] and not loiter[int(robot)]
                }
                if not involved:
                    raise RuntimeError("robots on private loiter circles cannot conflict")
                for robot in involved:
                    advance(robot)
                continue
            certified_min = float(certified.min())
            chord_min = float(chord.min())
        if (
            loiter_assignment(
                end, end_heading, radius=radius, domain=domain, min_separation=min_separation
            )
            is None
        ):
            free = [robot for robot in order if moving[robot] and not loiter[robot]]
            if not free:
                raise RuntimeError("a fleet on its loiter circles keeps its assignment")
            loiter[free[0]] = True
            continue
        scales = np.asarray([SCALES[level] for level in levels])
        modified = moving & (
            (scales < 1.0) | ~np.isclose(chosen, kappa, rtol=0.0, atol=1e-15) | loiter
        )
        return ArcStep(
            positions=end,
            headings=end_heading,
            speeds=lengths / dt,
            curvatures=chosen,
            scales=scales,
            modified=modified,
            loitering=loiter & moving,
            intervention=bool(np.any(modified)),
            certified_separation=certified_min,
            chord_separation=chord_min,
        )
    raise RuntimeError("the loiter search did not terminate")
