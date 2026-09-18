# Domain docs

All paths below are relative to the repository root.

## Existing project references

For the current refinement effort, read `.scratch/research-refinement/interview.md`
for confirmed user choices and `.scratch/research-refinement/research-brief.md` for
the brief and its approval status. Use approved scope decisions for new research.

Read `AKTIF_ONCELIK_PROJE.md`, `GP_Attainability_Masterplan_TR.md`, and
`docs/CONTINUE_HERE.md` for the original milestone scope, implementation history,
and continuation notes. Earlier research deferrals apply to that original plan;
the current user has explicitly reopened research refinement.

For work in a particular area, read the relevant milestone design document under
`docs/` (`M1_CONTROL.md` through `M7_USV.md`). Consult `docs/equation_map.md`,
`docs/assumption_ledger.md`, and `docs/source_manifest.md` when changing equations,
assumptions, or source-based claims.

Read relevant entries in `docs/decision_log.md` for historical decisions. Preserve
the log and reference its entries when a new ADR builds on or supersedes one.
Resolve scope conflicts using the user's current decisions and the approval status
of the new research brief, rather than treating historical plans as new instructions.

## Domain-document layout

This is a single-context repository:

- `CONTEXT.md`: repository-wide domain vocabulary and model.
- `docs/adr/`: architecture decision records.

Before exploring an area, read `CONTEXT.md` and any ADRs relevant to that area when
they exist. If these files or directories are absent, proceed silently. The
`domain-modeling` skill creates them lazily when terms or decisions are resolved.

## Vocabulary and decision conflicts

Use the terms defined in `CONTEXT.md` in issue titles, hypotheses, refactor proposals,
and tests. If a concept is missing, check the existing project vocabulary before
proposing a glossary addition through `domain-modeling`.

When a proposal conflicts with an ADR, identify the record and explain why it should
be reconsidered. Make conflicts with recorded project decisions explicit as well.
