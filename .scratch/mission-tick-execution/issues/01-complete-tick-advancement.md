# Advance missions through complete physical ticks

Status: ready-for-agent
Execution: complete
Parent: [Complete-tick execution spec](../spec.md)
Approval: the user approved the read/advance/finish testing interface.

- [x] Constructor closes startup with its existing ordering and failure behavior.
- [x] Each advance returns only after one physical tick and all due work.
- [x] Reads provide immutable views with actual reached time and sample counts.
- [x] Finish uses the same progression and finalizes completed/failed evidence once.
- [x] Terminal advances and copied artifact reads preserve owned evidence.
- [x] Literal clock/provenance, partial/failure, and frozen-reference tests pass.
- [x] Static, full-suite, diagnostic checks and independent reviews pass.

## Comments

Existing CI portability repairs are validated first. Copying mission state,
recovery interventions, and charged planning delay remain separate research work.

20 September 2026: the user approved the testing interface. Red/green development
is recorded in [the development log](../red-green.md). Final validation passed
1,057 tests at 94.61% coverage, all static checks and 11 independent GP diagnostics.
The 14 expected reference cases match exactly, with the separate SOGP numerical
repair explicitly retained. Both independent review axes report zero findings.
See [completion evidence](../completion.md) for reports and integrity hashes.
