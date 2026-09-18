# Known differences

The [active masterplan v2.0](../GP_Attainability_Masterplan_TR.md) supersedes earlier
scope and completion rules. The v0 application is preserved as a working baseline;
it does not complete the new hierarchy, SOGP, QP and execution/budget deliverables.

## Existing independent v0 application, 2026-09-08

The active application uses a fixed exact RBF GP, heuristic finite-grid information
planning, a centralized segment-displacement constraint filter, synthetic field and
holonomic/kinematic-USV dynamics. All are independent chosen implementations, not
paper-aligned SOGP/QP/CBF or hierarchical distributed control. Active clocks are 0.5 s
motion and 5 s sampling. See README for the implemented contract and limitations.

54 policy development runs, an offline dashboard, artifact exports and recorded video
are recorded development evidence. They are not held-out validation of the new method
or completion of v2. Independent development can proceed without the ECC full text;
paper reproduction and formal guarantees remain separate, unsupported claims.

## Historical scaffold stage (superseded application status)

- The anchor full text, author code, and raw data are not locally available.
- `configs/reproduction/ecc2025.yaml` is deliberately locked and contains no inferred
  paper values.
- Historical development clocks used the publicly reported 10 s sample period and a
  chosen 0.2 s control period; neither is an exact reproduction claim.
- At that stage, no SOGP, controller, planner, field, or ECC figure had been implemented.
- The initial package supplied contracts, provenance, deterministic RNG, config parsing,
  scheduler, and artefact identifiers only.
- No headline results, performance claim, certificate, or safety claim existed then.

## Literature-driven design differences

- Exact/frozen-dictionary covariance was the earlier certificate-surrogate candidate
  because fixed-budget Csató-Opper pruning is label-dependent. Certificate development
  is deferred. Active SOGP forecasts must declare their approximation and report error;
  they are not automatically bounds.
- Integrated variance reduction is not assigned Krause et al.'s mutual-information
  submodularity guarantee.
- External TensorFlow/GPflow SGP-Tools is not a core dependency; any comparison uses a
  separate optional, revision-locked environment.
- A route penalty is never treated as hard feasibility, and a TSP polyline is never treated
  as an executable robot plan without dynamics/safety simulation.
- A finite evaluation-grid variance statement is not promoted to a continuous-domain or
  true-field-error guarantee.
