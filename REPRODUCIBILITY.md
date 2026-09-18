# Reproducibility contract

Scope and completion criteria follow [masterplan v2.0](GP_Attainability_Masterplan_TR.md).
The implemented contract below describes v0, M1 holonomic QP, M2 timed DP, M3 SOGP,
M4 execution-aware plan management, the frozen M6 held-out comparison, the M7
turn-constrained USV transfer (v1 and its v2 confirmation) and the M8 presentable
package (showcases, figures, technical note, video).
M5 source alignment: the ECC 2025 full text was audited on 15 September 2026 and the
separate `ecc2025` source profile was implemented on 16 September. The paper publishes no
seeds, ground-truth parameters or exact initial positions, so the profile is compared with
the paper **qualitatively**, never as a numerical reproduction. Run
`doctor --source-report` for the difference report.

## Active independent application

CPython 3.11, dependencies resolved by `uv.lock`, CPU only. Simulation CLI commands
default BLAS/OpenMP thread environment variables to one unless already set by the user.
Historical YAML schemas in `configs/` are not active simulator settings. Active
configuration is validated by `MappingConfig` in `sim/mapping.py` with presets in
`demo/runner.py`.

Repeat `python -m attain_sampling simulate --scenario combined --seed 7` with the
same code/dependencies to recover the same scientific values. Timestamps, output IDs
and timings differ. Measurement noise/dropouts and disturbances are indexed by
seed/robot/tick, independent of planner call order. Policies share truth and exogenous
events but observe different values at different actual locations.

Each paired comparison produces:

```text
outputs/mapping/<timestamp-config_hash-unique_suffix>/
|-- comparison.json         # all frames, motion, measurements and summaries
|-- config.yaml             # resolved MappingConfig, not a paper configuration
|-- metadata.json           # versions, platform, command, seeds, source hashes, claims
|-- source_snapshot.zip     # package sources plus local pyproject/uv.lock
|-- summary.json
|-- artifact_manifest.json  # SHA-256 of base artifacts (not itself or DONE)
|-- sweep/, greedy/, adaptive/
|   |-- robots.parquet      # motion tick: plans, actual states, constraints
|   |-- samples.parquet     # planned/actual positions, receipt, values
|   |-- controls.json       # full preview/execution control events and solver settings
|   |-- controls.parquet    # columnar control-event export
|   |-- plans.json          # M2/M4 timed plans; empty for original policies
|   |-- plan_events.json    # M4 decision log; empty unless the method is P
|   |-- gp_updates.json     # M3 ordered online update/removal events (SOGP)
|   |-- gp_failures.json    # rejected updates; received != assimilated in a failed batch
|   |-- gp_telemetry.json   # final and per-frame numeric dictionary state
|   |-- planned_samples.parquet # plan ID, physical sample time, robot and geometric site
|   |-- status.json         # completed/failed and failure details
|   |-- timeseries.parquet  # scalar metrics at GP evaluation frames
|   `-- seed_manifest.json
|-- DONE
|-- figures/                # optional derived export after DONE
`-- demo.mp4                # optional recorded-data video after DONE
```

Directories are unique and never replaced. DONE follows base serialization, hashing
and configuration read-back validation, not video export. The whole directory is not
an atomic filesystem transaction. Interrupted directories without DONE are retained
and ignored by `latest_comparison`. Derived exports are not included in the original
base manifest and refuse overwrite. `DONE` does not mean mission success: inspect
comparison/run `status` and `failure_count`. Failed runs retain actual partial
trajectories, sensor-epoch prefixes, rejection details and last reached time;
their metrics are not full-horizon scores. `summary.json` and benchmark records
also carry `status`, `failure`, `requested_duration_s` and `metric_scope`.

Git revision is null without a commit; source hashes and snapshot trace uncommitted
code without invented provenance. Installed wheels still snapshot their package even
when a Git checkout is unavailable.

`benchmark` prints a representative pilot before the rest of its batch. Projection
excludes artifact I/O and is a linear estimate, not a guarantee. JSON records every
requested method/scenario/seed. Runtime includes nominal baseline preplanning.
`planning_s` includes covariance calculations inside planning; `gp_s` counts actual
assimilation and map prediction (including explicitly identified reconstruction
after failure). `control_s` records executed control wall time and quantiles;
`control_preview_s` overlaps `planning_s`. QP events include effective solver
settings and residuals; `motion.control_event_index` links applied controls.
Timing depends on hardware, load and library stack. See [M1 limits](docs/M1_CONTROL.md).
M2 adds received-belief provenance and plan links across samples/motion/frames;
the selected plan's geometric forecast is not a QP rollout. Short-horizon values
are not mission-terminal values. See [M2 contract and timing](docs/M2_PLANNING.md).
Add `,p` for the proposed M4 policy and its recorded budget, decision and target-risk
blocks; `--p-no-rollout`, `--p-no-retain` and `--p-periodic-only` select the three
ablations. Use `--methods sweep,greedy,adaptive,dp --controller qp` to opt in; default methods
are unchanged. Selected methods are included in comparison metadata.

M3 real update order is ascending `(sample_tick, robot_id)` over received samples.
All policies in a comparison use the same `gp_backend`; exact remains default.
Pruning is label-dependent: SOGP forecasts condition its frozen current approximate
posterior, not future admission/removal. B0/B1 keep their exact-prior nominal route
surrogate. Numeric `state_nbytes` excludes audit logs and workspace. Failed batches
retain receipts with `assimilated=false` and the last committed belief.
See [M3 contract](docs/M3_SOGP.md). `scripts/validate_m3.py` saves raw same-data inputs,
predictions, order/future-pruning diagnostics and independent dense DP-prefix audits.
`--matrix --seeds 7 19` is development, not held-out evidence.

Validate with `scripts/check.ps1` plus the separate diagnostic unittest suite. The
default three seeds are development cases, not held-out evidence.

## M6 held-out comparison

The protocol is frozen in `configs/independent/m6_protocol.yaml` (see
[M6 protocol](docs/M6_PROTOCOL.md)). Its LF SHA-256 is pinned in
`attain_sampling.eval.m6`, and the runner refuses any other version:

```text
python scripts/run_m6.py
python scripts/report_m6.py outputs/m6-<date>/heldout/batch-<id>
outputs/m6-<date>/heldout/batch-<id>/
|-- protocol.yaml, declared.json    # written before the first job
|-- source_snapshot.zip, source_sha256.json
|-- runs/<block>-<variant>-<scenario>-s<seed>.json.gz   # full comparison records
|-- records.json                    # per-run metrics, warnings and audits
|-- batch.json, manifest.json       # job errors, schedule check, SHA-256 of every file
|-- analysis.json, figures/, report_manifest.json      # from report_m6.py
```

Held-out seeds are 9001–9040. Smoke tests use `--dev-seeds` with development seeds only,
and their batches are written under `development/`. `report_m6.py` recomputes every
metric from the raw files and stops if any differs from the worker record. Wall-clock
times come from 16 parallel workers on one machine; compare them within a task, not
across machines.

## M7 turn-constrained USV comparison

The M7 vehicle is `--model usv_curvature` (see [M7 design](docs/M7_USV.md)). It
flies forward only, with a minimum turning radius, and runs under a certified arc
filter. B3 and P plan with motion primitives on this vehicle. The frozen protocols are
`configs/independent/m7_protocol.yaml` (`m7-usv-heldout-v1`, held-out seeds
9101–9140) and `m7_protocol_v2.yaml` (`m7-usv-heldout-v2`), and they run through the
same scripts:

```text
python -m attain_sampling simulate --model usv_curvature --methods sweep,greedy,adaptive,dp,p
python scripts/run_m6.py --milestone m7v2
python scripts/report_m6.py outputs/m7v2-<date>/heldout/batch-<id>
```

`--milestone m7v2` runs the v2 confirmation protocol
(`configs/independent/m7_protocol_v2.yaml`, seeds 9201–9240), which is the current code.
The v1 held-out batch (`--milestone m7`, seeds 9101–9140) was produced before the
planner's containment check was corrected (D056–D058). Its `source_snapshot.zip`
holds that code, and `report_m6.py` still recomputes its metrics from the raw
records. Rerunning v1 with today's code would not reproduce it.

The report reads the milestone from `declared.json`. Development smoke batches
(`--dev-seeds 7,19 --allow-unfrozen`) are written under `outputs/<milestone>-<date>/development/`.

## M8 presentable package

The M8 artifacts run no new study. They are built from the frozen batches and from
four showcase recordings, in this order:

```text
python scripts/make_showcases.py   # outputs/showcases/: 4 recordings + showcases.json (SHA-256 pinned)
python scripts/figures_m8.py       # reports/figures/m8/: 6 figures, stopped_robots.json, MANIFEST.json
python scripts/build_note.py       # docs/technical_note/: HTML filled from analysis.json, PDF via local Chrome/Edge
python scripts/make_video.py       # outputs/m8/FIELDWORK_m8_demo.mp4 (+ .json with its SHA-256)
```

**Showcases.** Showcases use development seeds only (D059). The demo server serves a
showcase only if its file still matches the manifest hash. Re-running the script
reproduces the same scientific content: the paired simulation is deterministic, and
only the timings differ.

**Held-out batches.** `figures_m8.py` and `build_note.py` read the M6, M7 v1 and M7 v2
batches from `outputs/`, which is not versioned. On a fresh checkout, re-create them
with `run_m6.py` (about 50 minutes per study on 20 workers) before building.

**Clean-copy check (18 September 2026).**
- The files a commit would contain (everything not ignored) were copied to a separate
  folder.
- An environment was created there from `uv.lock` alone: `uv sync --locked --offline`,
  with the existing package cache.
- All 1,007 tests passed, and a short `simulate` run completed.
- The check found one outdated test expectation, which was fixed.

## ECC 2025 source profile (M5)

The source profile is separate from the independent simulator and uses the audited Table I
values from `attain_sampling.sources.ecc2025`. One paired run:

```text
python -m attain_sampling ecc-profile --seed 7 --start paper --scale theorem
outputs/ecc2025/<timestamp>-<scale>-<start>-s<seed>/
|-- e0.json.gz      # constraint-only controller (10): epochs, samples, trajectory, snapshots
|-- e1.json.gz      # hierarchical controller (17) with the cell planner (16)
|-- summary.json    # both summaries, project choices and claim limits
`-- figures/        # executed paths, J and MSE, variance snapshots
```

`--start edge` and `--scale figure` select the recorded sensitivities (decisions D042 and
D043). The validation batch fixes its criteria in `criteria_declared.json` before the
first run. It writes every run, recomputes `J` independently from the recorded samples,
and checks that both controllers receive identical noise innovations:

```text
python scripts/validate_m5.py
python scripts/figures_m5.py outputs/m5-<date>/validation/batch-<id>
```

A rejected QP solve ends that run as `failed`. The failure is recorded, and the pair
counts as meeting no criterion. The same seed, code and dependencies give the same
values; timings differ. Figures come from recorded runs only.

## Active development and evidence criteria

Follow v2 M0–M8, not the archived v1 G0–G6 sequence: preserve the baseline; add QP,
timed MDP/DP and SOGP; complete execution/budget management; evaluate strong baselines
and ablations; validate USV and package the results. Independent implementation can
proceed without ECC full text. Source/equation audit gates only the corresponding ECC
reproduction claims. Future paper values need a source and PAPER, AUTHOR_PAGE,
INFERRED or CHOSEN provenance; guessed equations are never a reproduction.

The old unfrozen seed reservation and conflicting method/comparison drafts were
archived. No new final seed set is frozen by this cleanup. Freeze the new protocol
before held-out runs, using the plan's task-level comparisons and failure accounting.
New proof/certificate work is deferred, not an application completion requirement.
