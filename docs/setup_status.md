# Setup status

Last updated: 2026-09-08.

Active scope: [masterplan v2.0](../GP_Attainability_Masterplan_TR.md) and
[current priority](../AKTIF_ONCELIK_PROJE.md). The existing FIELDWORK v0 is the baseline,
not completion of the new plan. Independent QP, timed MDP/DP, SOGP and execution/budget
management are the next implementation layers; strong comparison and USV evaluation
follow. Source-specific ECC reproduction is a separate profile.

## Working v0 application (preserved evidence)

- Exact-GP 2–4 robot mapping loop, three paired policies, four disturbance scenarios.
- Holonomic and bounded-turn kinematic USV execution, segment separation checks.
- Offline local dashboard, replay, maps, metrics, saved JSON/Parquet and video export.
- Previous validation recorded 187 passing tests, approximately 91.9% branch coverage,
  and passing Ruff/strict mypy checks; this is not a new test result from installing v2.
- 54 policy runs recorded and audited; see the development results report.
- Wheel/sdist build and locked offline environment sync verified on 2026-09-08.
- Missing paper full text does not block the independent application.

Run `scripts/demo.ps1` from the project root; see [demo instructions](DEMO.md),
[continuation notes](CONTINUE_HERE.md) and [cleanup verification](cleanup_report.md).

## Existing setup and previous validation

- Git repository initialized on `main`.
- Python 3.11 and `uv` contracts declared.
- Runtime, development, and optional oracle dependencies declared in `pyproject.toml`.
- Strict infrastructure YAML loader and deterministic integer-tick scheduler scaffolded.
- Paired-randomness manifest and call-order-independent measurement innovations scaffolded.
- Artifact hash/run-ID contracts and CLI research-gate guards scaffolded.
- CI, pre-commit, formatting, typing, coverage, source provenance, and private-paper ignore
  policies declared.
- Development/reproduction-placeholder/method/sweep/experiment configuration namespaces
  created.
- Local bootstrap was verified with CPython 3.11.16 and uv 0.12.8; `uv sync --locked` passed.
- Wheel/source-distribution build and packaged CLI smoke test passed in the v0 validation.
- Initial scaffold validation had 94 tests; superseded by the recorded v0 suite above.

## Source-specific restrictions and deferred claims

- Anchor SOGP equations and parameters.
- Paper QP, CBF, distributed decomposition, and hierarchical planner.
- Baseline reproduction and headline figures.
- Formal certificate claims require proof and verified preconditions; new proof work
  is deferred and is not a v2 completion requirement.

These restrictions do not lock independently defined SOGP, MDP/Bellman-DP, QP constraints,
controller rollout or execution/budget-aware plan management. Those components remain
to be implemented and tested; the present segment-displacement filter is not a QP/CBF.

The Git remote is intentionally unset because no destination/owner was supplied. Add it
only after choosing the canonical host; `CITATION.cff` therefore contains no placeholder
repository URL.

The initial commit is also intentionally pending: this machine has no Git `user.name` or
`user.email`. Configure the real author identity before committing so provenance is not
fabricated.

## ECC source-audit input (v2 M5 only)

Provided on 15 September 2026 (S01 in [source_manifest.md](source_manifest.md)). A fresh
checkout needs its own legally obtained copy at
`references/private/suenaga_et_al_ecc2025.pdf`; then run:

```bash
uv run attain-sampling doctor --strict-paper
```

The audit recorded its SHA-256, page count, source, access date, redistribution status,
every implementation equation and every parameter before paper-specific code started.
