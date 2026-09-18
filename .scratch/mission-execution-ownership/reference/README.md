# Frozen mission behavior references

The accepted reference is `frozen-20260918/`, captured before production changes.
Its manifest SHA256 is
`176304312a59b1895be6cd86db4731b7005572756b86459ed94066960a683da8`.
The source and archived source copies were checked against the preserved
`../../research-refinement/baseline/20260918T145314Z/manifest.json`.
The manifest contains all source hashes, full configurations, seed, failure
triggers, Python/platform and numerical dependency versions, harness hash, and raw
and normalized artifact hashes. This is development preservation evidence, not a
new research result.

Run from the repository root with the existing environment:

```powershell
.venv/Scripts/python.exe scripts/mission_reference.py check --reference .scratch/mission-execution-ownership/reference/frozen-20260918 --output .scratch/mission-execution-ownership/reference/after-ownership
```

Choose a **new** output directory for each check. Capture and check never overwrite
an output directory. `capture --output <new-directory>` additionally requires the
production source to match the pre-refactor archive. Do not recapture to accept a
post-refactor difference. Check deliberately accepts changed production source,
records its hashes, and requires the frozen harness, environment, and normalization
rules. It retains fresh raw/normalized outputs and reports a case and first
differing JSON path, with no scientific numeric tolerance.

The 14 cases cover all five methods, all three motion models, both GP backends,
SOGP dictionary pruning, filter and QP controls, fractional clocks, an off-sample
deadline, total receipt loss, actual interior P triggers, and different incoming
forecast/outgoing-plan identities. Managed curvature motion actually executes.
Six failed cases preserve preview before/after initial receipt, rejected execution,
initial/later planning failure and received-but-unassimilated GP batch failure.
Each manifest row records observed coverage, and capture asserts these requirements.

`repeat-frozen-20260918/report.json` passed all 14 cases exactly. Capture and repeat
each ran in about 2.3 seconds of summed per-case wall time. Raw JSON remains intact;
normalization replaces only the explicitly listed measured runtime paths in
`scripts/mission_reference.py`. It retains their presence and null state, checks
finite nonnegative numeric values, and never strips arbitrary `_s` fields.
Physical clocks, deadlines, budgets, IDs, counts, iterations, solver results,
scientific values and failure details remain compared.

`sensitivity-controls.json` records mutation checks against copies of real frozen
raw evidence: scientific values, physical time, plan linkage, receipt provenance,
and failure status were detected. Listed summary and nested rollout timing changes
alone were accepted. No frozen artifact was modified for these checks.

Validation passed: the initial 12 harness unit tests plus 14 existing
timing/accounting cases (26 passed, 93 deselected in 2.16 seconds). Four further
schema/exclusion controls bring the standalone harness suite to 16 tests, all
passed in 0.31 seconds. Ruff lint/format checks on the two new Python files passed.
The exact initial focused command is recorded in the sensitivity report.
The test loop first observed failures for a missing comparator, an unhandled
runtime path, and changed-harness acceptance before implementing each behavior.

The earlier `capture-20260918-a` and `repeat-20260918-a` artifacts retain the discovery
of the source-confirmed nested `plans.*.candidates.*.rollout.wall_s` timing field.
The intermediate `capture-20260918-final`/`repeat-20260918-final` predates the final
harness identity enforcement. They are retained audit history; use only
`frozen-20260918` for production comparisons.
