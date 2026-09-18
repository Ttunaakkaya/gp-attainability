# M7 — USV transfer: a turn-constrained vehicle

17 September 2026. Masterplan v2 §12 and §16 ask for the same contribution question on
a second vehicle model, with the vehicle class named explicitly and its limits stated.
This document describes the model, controller and planner. The frozen comparison is in
[M7 results](../reports/m7_results_2026-09-17.md).

## Vehicle class: `usv_curvature`

| | |
|---|---|
| State | position and heading |
| Controls | forward speed `v` in `[0, 2]` m/s, path curvature `|κ| ≤ 1/R` |
| Turning radius | `R = v_max / max_turn_rate = 2 / 0.45 = 4.44` m |
| Motion | exact circular arcs over each 0.5 s step |
| May stop | yes |
| May turn on the spot | **no** — this is what separates it from the original `usv` model |
| Disturbance | yaw-rate tracking error of `drift_strength` rad/s at full speed, applied to the commanded curvature within the vehicle's authority |
| Not modelled | hydrodynamics, currents, drift of a stopped vehicle, actuator dynamics |

The original `usv` model (turn-in-place allowed, straight segments) is unchanged and
still has no planner support. The M1 QP stays holonomic-only.

## Guidance

Each step follows the shortest forward path to the commanded cell with a free arrival
heading (`sim/usv.py`, `point_path`). The candidate paths are turn-straight and
turn-turn, which contain the optimum of that problem; tests compare the result with a
brute-force search over a larger family and find it never longer. Speed asks for arrival
at the sampling deadline, never earlier, as the holonomic controller does.

## Certified filter and its invariants

Every executed step keeps three invariants, checked on entry and certified on exit:

1. **Inside the field.** Sampled arc points stay inside the field with a margin for the
   sub-interval arc deviation.
2. **Private loiter circles.** Every robot has one minimum-radius circle inside the
   field, and the chosen circles are at least `2R + d_min` apart
   (`loiter_assignment`).
3. **Separation.** The straight chords that the M1 audit replays keep `d_min` exactly;
   the arcs between them keep it to within 1 mm (sub-interval deviation ≤ 2e-4 m).

The second invariant was not in the first design. With stopping as the only fallback,
a development loop left the fleet stopped in 57 % of robot-steps. Two forward-only
vehicles facing each other at `d_min` can never move again, so stopping is not a
sufficient fallback for this vehicle class. With private loiter circles, "everyone
circles on their own circle" is always a safe joint command. The filter therefore never
stops a robot: it moves a robot onto its loiter circle, or tries the opposite full turn,
straight ahead, then lower speeds. In the same development loop no robot stopped, and
the fleet covered 93–95 % of the maximum path.

Initial positions sit a turning radius from the left edge in two staggered columns, so
the invariant holds from the first step. The configuration refuses a start without
private circles.

## Planner: motion-primitive Bellman tree

Masterplan §7 asks the USV planner to carry heading information or motion primitives.
B3 and P on this vehicle use `planning/primitive_dp.py`:

- **Primitives:** each epoch applies one of seven — a full-budget or half-budget arc
  turning fully left, going straight or turning fully right, or a stop.
- **Tree:** over the four-epoch horizon the reachable states form a tree of about 2,800
  exact vehicle states. A node is admissible if its whole arc stays inside the field
  (exact bounding box of the arc) and it ends with a turning circle inside. A robot
  with an inside circle can therefore always continue along it.
- **Shared with M2:** frozen single-sample rewards, normalised travel, reservations of
  earlier robots' chords, four robot orders, Bellman or greedy routes, and joint
  terminal-variance selection. A primitive route is flyable by construction.

### Held-out record: the containment defect (D056–D058)

The v1 planner checked containment on 17 sampled arc points with a margin of half a
sub-interval (0.16–0.31 m). That was stricter than the controller's invariant, whose
circles may come within 1e-9 m of an edge. Drift pushes robots into exactly such states.
There the planner kept only the stop primitive. A stopped robot never changes state,
so B3 left it stopped for the rest of the mission. In the v1 held-out batch, under
drift, 94 of 160 B3 robots stopped for good for at least 30 s, in 37 of 40 tasks.

The check is now exact, and a regression test covers it. M7 v2 repeats the frozen
comparison with this correction on new tasks. v1 is reported as run; see
[M7 results](../reports/m7_results_2026-09-17.md).

### Development record: the heading-bin DP that was replaced

The first USV planner kept M2's cell grid and added 16 or 32 heading bins. On the
development seeds it was a weak baseline (170–310 m of fleet travel against ~700 m for
B2) and was replaced before any held-out run:

- Rounded headings made path lengths jump by a full turn whenever a target slipped
  inside the turning circle. Exact re-checks then rejected every candidate for
  8 consecutive epochs, and the fleet held.
- Admitting moves on the worst heading within the bin removed the rejections, but left
  fewer than one move per state on average.

With primitives, B3 on development seed 7 (nominal) reached a mean variance of 0.0329
and 534 m of travel. Only development seeds 7, 19 and 31 were used for these choices.

### Straight-line variant

`dp_motion_primitives: false` keeps the holonomic M2 planner (straight-line
reachability) on cells inset by `R + 0.5` m. Its geometry is wrong for this vehicle.
M7 runs it as a separate block, because that is where a controller rollout should
matter most.

## P on this vehicle

P is unchanged. Its rollout replays candidates through this guidance and filter, and its
hold continuation is a stop, which the loiter invariant keeps admissible. The event
triggers use the frozen M4 thresholds. The reference path for the deviation trigger is
the shortest forward path, not a straight line. Nothing was re-tuned for the USV,
although drift makes the 1.5 m deviation trigger fire often: 78–110 decisions per
development mission against 18 periodic ones.

## Limits

- A kinematic surrogate: arcs of bounded curvature, no current or hydrodynamics. It is
  not the Hatanaka group's USV benchmark, and ROS 2 was not needed for this question.
- The filter's guarantees hold for this model and its disturbance, not for a real boat.
- The primitive set is a surrogate: routes that curve less than fully are not searched.
- Timing is wall-clock on a shared machine.
