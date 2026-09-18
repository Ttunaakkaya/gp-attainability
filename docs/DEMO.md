# Demo walkthrough (M8)

A guide for showing FIELDWORK live in about ten minutes, plus short answers to the
questions a reviewer is likely to ask. Everything shown is recorded simulation output.
The showcases use development seeds and illustrate mechanisms. Claims rest on the
held-out studies ([technical note](technical_note/FIELDWORK_technical_note.pdf)).

## Before the demo

```powershell
.\scripts\bootstrap.ps1                                  # once, on a fresh checkout
.\.venv\Scripts\python.exe scripts\make_showcases.py     # once, about 5 minutes
.\scripts\demo.ps1                                       # http://127.0.0.1:8765
```

The server prints how many showcases it found. The page loads the newest saved
comparison, and **Guided showcases** appear above the mission setup. The recorded video
is built separately with `python scripts/make_video.py` (107 s, 1280 × 720).

## Ten-minute path

1. **The loop in nominal conditions (showcase 1, about 2 min).** Open the card; the
   replay jumps to 30 s.
   - Point at the squares: the timed cells of B3's plan in force, labelled with their
     sampling times.
   - Press play. Every 5 s B3 re-plans from the data that actually arrived and the
     robots' actual poses.
   - Switch the layers. Uncertainty falls where samples land; the error map does not
     fall evenly.
2. **A plan update after loss and drift (showcase 2, about 3 min).** B3 is on the left,
   P on the right: same world, same lost measurements (crosses).
   - The strip under the maps says, in plain words, which event made P check and why it
     kept or replaced its plan.
   - In the plan panel, the chart separates P's conditional forecast (dashed), the hold
     continuation to the mission end (dotted) and the fixed mission target (coral, dashed).
   - Say explicitly that P's lower RMSE on this seed is one seed. The held-out interval
     on the card includes zero.
3. **The turn limit moves where samples land (showcase 3, about 2 min).** On the
   turn-constrained USV, plans are drawn as the arcs the boat can fly.
   - On the P map, hollow circles are where P's controller rollout predicts each sample
     will land; dotted connectors join them to the commanded cells.
   - Dashed rings mark robots that the safety filter holds on their private loiter circle.
   - At the key moment, one robot is predicted to sample 14 m from its cell, and the
     real sample lands 1.4 m from the prediction.
4. **Where the method does not help (showcase 4, about 2 min).** The card states the
   rule that chose this seed.
   - P and B3 end with the same RMSE, B2 is better, and P planned 14 times longer.
   - In **Plan meets reality**, the realised variance stays above the forecast under loss.
5. **The held-out result (about 1 min).** Show Figure 1 of the note: 10 of 10 intervals
   include zero. Then Figure 5: the comparator defect and its correction.

A live run is optional. With **Include periodic DP** and **Include execution-aware P**
on the turn-constrained USV, 2 robots and 20 s, it finishes in under a minute. The
mission-target field is optional and only used by P.

## Controls worth knowing

- **Side by side.** The **B3 | P side by side** toggle in the map toolbar replays both
  planners on the same clock. It is enabled whenever a recording contains both.
- **Robot dynamics.**
  - The **turn-constrained USV (M7)** uses the certified arc filter; the velocity QP is
    holonomic-only.
  - The v0 USV that turns on the spot is kept for old recordings. It has no
    heading-aware planner, so B3 and P are disabled for it.
- **Panels.**
  - Controller evidence: QP solves and residuals (holonomic), or loiter holds, speed
    scales and certified separation (USV).
  - Sparse belief panel: dictionary size and pruning (SOGP runs).
- **Failures.** Failed missions stay visible as INCOMPLETE, with their real prefix;
  they are never ranked.

## Questions to be ready for

- **Why can variance fall while error does not?**
  - The GP variance depends only on where samples were taken, not on the values.
  - A mis-specified kernel makes the variance look good while the map is wrong. In M6,
    a 16 m kernel lowered every method's variance and raised its RMSE, and all 40 tasks
    still met the variance target.
- **What does the MDP approximate?**
  - A bounded Bellman search over coarse cells (or seven motion primitives on the USV),
    four epochs ahead, with frozen single-sample rewards and earlier robots' choices as
    conditioning.
  - Joint terminal variance then selects among a few candidates. It is not a full
    belief-MDP optimum.
- **What does the QP constrain?** Speed (an inscribed polygon), the field boundary,
  pairwise separation through barrier rows, and whole-segment separation. Every command
  is re-checked before execution. It carries no GP performance constraint.
- **Why does a plan look executable and still miss?**
  - The planner checks geometry and budget. The executed motion also sees drift, other
    robots and the safety filter.
  - P's rollout replays the nominal controller without disturbance or loss, so it is
    not a robust guarantee.
- **When does a forecast become invalid?**
  - When a measurement is lost: every forecast assumes each sample arrives, and the
    one-step error is about +0.017 in mean variance under 30% loss.
  - When SOGP pruning changes the dictionary.
  - When the kernel is wrong.
- **How strong is the comparator?**
  - B3 re-plans every epoch from the actual belief and positions, with joint covariance
    selection.
  - A defect in its USV planner was found in the M7 v1 raw records, fixed, and the study
    repeated on new tasks.
  - The one-step adaptive greedy B2 is stronger than both B3 and P in most scenarios.

## Older material

The 30-second video of the 8 September v0 comparison is kept as history
(`outputs/mapping/20260908T132704368559Z-ad68f128-d2c47b/demo.mp4`). The `record`
command still renders a short video from any saved comparison:

```powershell
.\.venv\Scripts\python.exe -m attain_sampling record "PATH_TO_COMPARISON_JSON"
```
