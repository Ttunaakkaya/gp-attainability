# Scripts

Environment entry points:

- `bootstrap.ps1`: installs/selects Python 3.11, restores the locked environment, and
  runs the environment doctor. It prefers `.tools/uv/bin/uv.exe`, then `uv` from `PATH`.
- `check.ps1`: runs the same lint, format, type, and coverage gates as CI.
- `demo.ps1`: starts the working local FIELDWORK dashboard on port 8765.

Stage-specific evidence:

- `validate_m1.py`: QP pilot, geometric/control evidence and source/artifact audits.
- `validate_m2.py`: exact-GP timed-plan prefix and candidate audits.
- `validate_m3.py`: same-data 32/64/128 replay, ordering/future-pruning diagnostics,
  then a measured long pilot. `--matrix --seeds 7 19` explicitly adds the development matrix.
- `check_m3_delivery.py`: compares matching exact runs with the preserved M2 index,
  verifies wheel/package byte equality and checks active local document links.
- `validate_m4.py`: bounded M4 development cases with an independent recomputation of
  every recorded P decision and budget.
- `validate_m5.py`: ECC 2025 source profile; eight qualitative criteria written to
  `criteria_declared.json` before four configurations x five paired seeds run, with an
  independent `J` recompute and a noise-pairing check.
- `figures_m5.py`: draws every pair of an M5 batch from its recorded runs.
- `run_m6.py`: the frozen M6 held-out comparison (`configs/independent/m6_protocol.yaml`).
  It refuses a changed protocol, writes the job list before the first job, keeps every
  comparison as gzip JSON and audits each run. `--dev-seeds 7,19 --allow-unfrozen` is
  a smoke test on development seeds only.
- `report_m6.py`: recomputes every M6 metric and warning from the raw files, checks them
  against the worker records, then writes `analysis.json` and the figures.
- The runner takes `--milestone m7` or `--milestone m7v2`, and the report reads the
  milestone from the batch. These select the frozen M7 USV protocols
  (`configs/independent/m7_protocol.yaml` and `m7_protocol_v2.yaml`; see D056–D058
  for why v2 exists).

M8 package (no new study; see REPRODUCIBILITY.md for the order):

- `make_showcases.py`: four recorded showcase comparisons on development seeds, with
  card text computed from each recording and a SHA-256 manifest the demo server checks.
- `figures_m8.py`: the six held-out figures, the recomputed stranded-robot counts and
  a hash manifest in `reports/figures/m8/`.
- `build_note.py`: fills `docs/technical_note/note_template.html` from the analyses and
  prints the PDF with a local Chrome or Edge.
- `make_video.py`: the 107 s presentation video from the showcases and figures.

Working experiment entry points are package CLI commands: `simulate`, `benchmark`,
`record`, `export` and, for the ECC source profile, `ecc-profile`. See the root README
for runnable examples. The old planned
`run_sweep.py`/`make_figures.py`/`make_report.py` files do not exist and are not required
for the current demo. Future work follows masterplan v2.0, not this historical scaffold.

Refinement preservation checks:

- `mission_reference.py check --reference <frozen-directory> --output <new-directory>`:
  compares whole missions with the hash-verified historical evidence. The existing
  harness and its runtime-only normalization are frozen.
- `check_mission_execution.py --output <new-directory>`: exercises the approved
  complete-tick interface against all 14 preserved cases. It retains comparison
  with the original baseline and separately identifies the one SOGP case affected
  by the documented numerical repair. The combined comparison is exact; the script
  never replaces frozen references. Use the original capture environment.
