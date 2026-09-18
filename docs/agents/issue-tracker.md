# Issue tracker: Local Markdown

Issues and specs for this repo live as Markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- The spec is `.scratch/<feature-slug>/spec.md`.
- Implementation issues are one file per ticket at
  `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Triage state is a `Status:` line near the top of each issue file; use the role
  strings in `docs/agents/triage-labels.md`.
- Record execution separately as `Execution: not-started`, `in-progress`, or
  `complete`. Completed tickets retain their triage role and are not picked again.
  A blocking ticket is satisfied when its execution is complete; link completion
  evidence under its Comments heading.
- Append comments and conversation history under a `## Comments` heading.
- Existing plans and reports remain in place. Link to relevant source material
  from tickets rather than copying or migrating the existing backlog during setup.

## Publishing and fetching

When a skill says "publish to the issue tracker", create the spec or individual
ticket file at the appropriate path above, creating its directories as needed.

When a skill says "fetch the relevant ticket", read the referenced file. Ticket
numbers are scoped to a feature directory; resolve the feature before using a
bare number that could refer to multiple files.

## Wayfinding operations

Used by `/wayfinder`. The map is a file with one child file per ticket.

- Map: `.scratch/<effort>/map.md`, with Notes, Decisions-so-far, and Fog sections.
- Child ticket: `.scratch/<effort>/issues/<NN>-<slug>.md`, numbered from `01`, with
  the question in the body. `Type:` is `research`, `prototype`, `grilling`, or `task`.
- Wayfinding tickets use their own lifecycle: `Status: open`, `Status: claimed`,
  or `Status: resolved`, separate from the triage roles above.
- Blocking: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when
  every ticket it lists is `resolved`.
- Frontier: scan the effort's issues for open, unblocked tickets; lowest number wins.
- Claim: set `Status: claimed` and save before starting work.
- Resolve: append the answer under `## Answer`, set `Status: resolved`, and append
  a summary and ticket link to the map's Decisions-so-far section.
