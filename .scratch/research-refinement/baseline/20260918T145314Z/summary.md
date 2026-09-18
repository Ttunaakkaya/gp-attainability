# Preserved baseline — 18 September 2026

The approved agent setup is applied. The existing project's source, tests and
configuration have not been refactored during this phase.

## Snapshot

- `source-tests-config.zip`: 179 files, with per-file SHA-256 values in `manifest.json`.
- The ZIP was read back and verified against the manifest.
- All 179 current file hashes still matched the snapshot after baseline validation.
- Historical experiment outputs remain in their existing locations; the snapshot
  excludes environments, generated outputs, caches and licensed papers.
- The repository has no commits or configured remote. This snapshot is a local
  preservation point, not a Git commit or an independent off-machine backup.

## Validation

Checks used the existing `.venv\Scripts\python.exe`, with versions recorded in the
manifest. No dependency installation or update was performed.

| Check | Result |
| --- | --- |
| Ruff check | Passed |
| Ruff format check | Passed; 84 files already formatted |
| Mypy | Passed; 44 source files |
| Main pytest suite | 1,007 passed in 204.91 seconds |
| Coverage, including configured branch measurement | 94.52%; required threshold 80% |
| Independent exact-GP diagnostic | 11 unittest tests passed |

The normal `scripts/check.ps1` launcher stopped before running checks because its
probe of `.tools\uv\bin\uv.exe` was denied access. The equivalent four quality
commands were then executed directly with the existing virtual environment and
all passed. The launcher issue remains; no application-code failure was observed.

Evidence: `quality-check.log`, `quality-check-status.json`, `validation.log`,
`validation-status.json`, `diagnostic.log` and `diagnostic-status.json`.

Passing the current tests establishes a software baseline. It does not validate the
new recovery claim or settle the source-equation questions recorded in the research
notes.

## Architecture assessment

Two independent read-only surveys identified three candidates:

1. Concentrate mission state and progression inside the existing simulation module.
2. Make forecasting usable independently of plan selection.
3. Give the new warning/recovery study explicit assessment semantics while
   preserving historical M6/M7 interpretation.

The first candidate is recommended because faithful paired continuations and
execution during planning both depend on coherent mission state and event order.
Candidate selection and interface design remain open; no implementation was made.

The visual assessment is an intentionally temporary artifact at
`C:\Users\Lenovo\AppData\Local\Temp\architecture-review-20260918-175747.html`.
Its content was inspected as source; browser preview was blocked by the browser's
local-file URL policy, so rendered layout was not visually verified.
