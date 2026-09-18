# Mission execution: design recommendation

18 September 2026. Design assessment completed using `codebase-design`, including
three independent interface designs. The user selected the next design step after
the architecture assessment. This records the recommended engineering direction;
the interfaces below are proposals, not implemented capabilities.

## Recommendation in plain language

Give the existing simulator one internal owner for a mission's changing state and
event order. Keep `run_mapping(config, method)` as the ordinary way to run an
experiment. First demonstrate that this structural change preserves today's
results. Then make the same execution path advance one physical tick at a time.

This supports later controlled recovery experiments: run an ordinary continuation
and a recovery continuation from the same complete state. Copying robot positions
alone would not preserve the GP belief, active plan, clock, or remaining budget.
Copying, recovery choices and planning delay are separately tested later increments.

The research decisions in [the approved brief](research-brief.md) remain settled.
This design does not select a recovery algorithm or establish a positive result.

## What the code requires

The evidence is in `src/attain_sampling/sim/mapping.py`:

| Location | Current behavior and consequence |
| --- | --- |
| `967`, `997` | `run_mapping` converts `ControlFailure` into a partial artifact using a separately maintained `progress` dictionary. Failure handling must read the same owned state as normal execution. |
| `1133`, `1172`, `1250` | State is spread across local variables, a closure, mutable lists and a progress mirror. Position alone cannot represent a continuation. |
| `1196` | Sweep/greedy perform nominal preplanning before the initial real measurement. Moving that measurement earlier would change failure evidence. |
| `1257`, `1323` | Real samples arrive in robot order; received and assimilated are different facts when an update fails. |
| `1324`, `1380`, `1440` | At a sampling time, posterior prediction and outgoing planning precede the frame. The frame may name a different plan from the incoming measurement and forecast. |
| `1480`, `1519` | Accepted motion is recorded before an interior P event-triggered replan. An epoch-only advancement interface would conceal these decisions. |
| `1566` | Plan activation and provenance are repeated in the interior-event path. They belong to the same execution owner. |
| `1608` | Only the physical sensing clock authorizes a sample; a partial final interval must not invent one. |

Historical contracts D020/D021 (clock/provenance) and D023–D026 (forecast,
continuation, retention and bounded search) remain intact. Historical design
documents describe their milestone versions; current code and M7 describe the
added curvature-USV support. No relevant existing ADR needs to be overturned.

## Three interface designs considered

### A. Functional continuation values

An interface such as `begin(config, method)` and `resume(continuation, stop)` can
hide substantial execution behavior behind two calls. Opaque continuation values
keep callers away from raw state.

The tradeoff is ownership. A reusable value implies copying a complete GP and
execution history correctly; an explicitly consumed value adds token-validity
rules to every caller. Neither cost helps today's whole-mission caller. Read-only
or frozen containers alone do not make their NumPy arrays or GP state immutable.

### B. Event and command scheduler

An interface such as `advance(until=...)`, `observe()` and `submit_plan(...)` could
support late decisions and explicit activation. Its depth would come from owning
event ordering, not from dispatching arbitrary callbacks.

That interface also commits us now to stale-plan validity, equal-time ordering,
in-flight jobs and planner observations. Those are research-protocol questions
that the first structural refactor need not answer. A generic event bus or a
one-event-at-a-time public interface would push ordering complexity onto callers.

### C. Owned mission execution — recommended

An internal mutable execution object owns progression and evidence. The existing
whole-mission interface remains unchanged. A later diagnostic caller advances the
same implementation through complete physical ticks.

This offers the best locality for the present code: state, failure handling and
plan activation change together in one place. It provides leverage to the normal
runner and, after the next increment, to incremental diagnostics. The deletion
test is meaningful once both paths use it: removing the module would scatter
state and ordering rules back across those callers and failed-outcome handling.

An object that merely wraps the old function while retaining a separate progress
mirror would not achieve the proposed depth.

## Staged interface

The first implementation slice stays inside `sim/mapping.py` to avoid an unrelated
file-move/import refactor. Its interface is intentionally small:

```python
def run_mapping(config: MappingConfig, method: str) -> dict[str, Any]:
    return _MissionExecution(config, method).run()
```

This is an illustrative shape, not permission to replace the body with a shallow
forwarder. `_MissionExecution` must own the changing state used by normal and
failed outcomes. Its private operations retain the existing numerical helpers.
Calling code must not need to invoke sampling, planning, or record-writing in order.

After historical parity is established, evolve that internal interface to:

```python
mission = _MissionExecution(config, method)
view = mission.read()
while view.status == "running":
    view = mission.advance()
result = mission.finish()
```

Here construction closes startup at tick zero; `advance()` executes one physical
transition and all existing work due at that tick. `finish()` advances to a
terminal outcome and finalizes once. `run_mapping` delegates to `finish()` at this
stage. These are consecutive designs, not two permanent execution implementations.

The diagnostic view contains status, last reached tick/time, positions, headings,
active-plan identity and sample counts as immutable values. Reading it performs
no GP prediction and exposes no writable internal arrays. It is not a checkpoint
or a planner's input contract.

### Ordering and lifecycle contract

1. Preserve nominal preplanning before initial receipt for sweep/greedy. A preview
   failure can leave no real samples; adaptive preview failure can occur after
   initial assimilation. Preserve that distinction.
2. At an interior tick: execute accepted motion, record it, then process any
   existing P trigger. The next motion uses the resulting active plan.
3. At a sampling tick: record arriving motion, receive and assimilate using the
   incoming plan, predict, choose the outgoing plan where appropriate, then write
   the frame. Preserve incoming `forecast_plan_id` and outgoing `plan_id` meanings.
4. At the deadline: preserve the final frame and existing failure semantics, with
   no new outgoing plan or extra off-clock measurement.
5. Preserve unsupported-configuration/method errors. Only failures currently
   handled as `ControlFailure` become failed artifacts; do not catch arbitrary
   exceptions or silently change GP backend failure semantics.
6. A failed control preserves the last accepted physical state and rejected
   attempt. A handled GP update failure retains actual receipts, their assimilation
   status and the existing backend state. Do not replay rejected data to rebuild it.
7. A fully processed tick is a safe observation point, not yet a place to fork
   before the additional recovery decision. That later capability requires an
   explicitly defined predecision phase and ownership contract.
8. Terminal advancement and finalization must not duplicate records. Returned
   views and repeated artifact reads must not let a caller mutate owned evidence.

### State and dependency ownership

Keep positions/headings, physical tick and interval cursor, received-data GP,
active plan/budget, remaining reference/goals, forecast links, evidence lists,
accumulated metrics and timers together. Configuration, grid and seed keys are
fixed inputs. Truth belongs to simulation and offline evaluation; planners still
receive only the existing allowed information.

All current scientific dependencies are **in-process**. Reuse the existing GP
backends, planners, shared motion execution, covariance interface and injected
nominal stepper. Actual alternatives already justify those seams. Add no new
adapter framework, transport interface, or dependency container for hypothetical
ROS integration. File persistence remains with the existing runner.

No complete state copying belongs in the tick loop. GP copying is a separate
future contract: ExactGP owns observation arrays and caches; SOGP owns an
order-dependent dictionary, posterior arrays, counters and update metadata. Both
need branch-isolation checks. Replaying received records is insufficient after a
rejected update; copying a final JSON artifact is not copying an executable state.

### Timing contract

For the preservation slice, planning is synchronous and its wall duration still
does not advance simulated time. Preserve the current timing scopes and avoid
double-counting nested rollout time. In the later incremental interface, elapsed
`runtime_s` would include caller pauses unless its semantics are deliberately
changed; per-operation timings remain separate. Pausing the caller is not a
planning-delay experiment.

The approved main validation still requires charged planning delay. A subsequent
protocol will specify decision availability, activation, stale-result checks,
equal-time ordering and behavior while a result is pending. A fully processed-tick
interface alone does not implement that protocol.

## Smallest useful implementation sequence

1. **Capture behavior before editing.** Use the preserved source snapshot and
   short development configurations to save deterministic artifact references.
   Cover all five methods across supported motion models, both GP backends, and
   relevant controller choices with a compact representative set. Include the
   already-tested failure branches below; do not launch a full research study.
2. **Concentrate ownership.** Introduce the private execution owner, migrate the
   state used by sensing, progression and failed outcomes, and remove the progress
   mirror. Keep the existing loop ordering, algorithms and returned schema.
   Consolidate duplicate activation bookkeeping only after parity is demonstrated.
3. **Add incremental execution.** Advance the same implementation through complete
   physical ticks and prove its result matches uninterrupted execution and the
   captured baseline. Add view-isolation and terminal-idempotence checks.
4. **Return to the research mechanism.** Resolve relevant source-consistency and
   estimator-cost questions, establish a distinct recovery action in a small
   controlled case, then specify predecision copying, ordinary continuation,
   warning assessment and charged planning delay against that experiment.

The immediate implementation spec should cover steps 1–2. Step 3 is the next
bounded increment. Steps involving recovery and delays must not become speculative
framework work inside that refactor. Stop expanding architecture once the next
controlled research experiment has the execution support it needs.

## Evidence required for the refactor

Preserve the existing behavioral tests and independent mathematical checks. The
skill's general suggestion to replace redundant shallow tests does not justify
deleting these behavior/provenance oracles.

| Behavior | Existing check |
| --- | --- |
| Scientific records deterministic except measured timings | `tests/unit/test_mapping.py:94` |
| Posterior reconstructed from actual received observations | `tests/unit/test_mapping.py:47` |
| Incoming/outgoing plan and forecast provenance | `tests/unit/test_mapping_dp.py:68` |
| Partial deadline and fractional sample clock | `tests/unit/test_mapping_dp.py:109`, `147` |
| Nominal preview failure prefix | `tests/unit/test_mapping_qp.py:78` |
| Rejected execution preserves actual reached state | `tests/unit/test_mapping_qp.py:96` |
| Planning failure after real receipt at an epoch | `tests/unit/test_mapping_dp.py:190` |
| Received but unassimilated data after GP failure | `tests/unit/test_mapping_sogp.py:140` |
| P event decisions inside an interval | `tests/unit/test_mapping_p.py:71` |
| Curvature-USV execution and planner behavior | `tests/unit/test_mapping_usv_curvature.py:73` |

Compare against pre-change references, not just two paths through new code. Remove
only an explicit list of measured performance fields when comparing artifacts;
physical time, deadlines, budget, IDs, event order and scientific values remain.
Keep unexpected differences visible. Run relevant tests during each slice and the
repository quality checks after the completed change.

The previous baseline passed 1,007 tests with 94.52% coverage plus 11 independent
GP diagnostic tests. No tests were rerun for this documentation-only design step.
That software baseline does not settle the pending source audit or prove recovery.

## Next workflow step

Turn the first bounded increment into the local implementation spec and dependency-
ordered tickets, then implement with behavioral tests and review. No new research
interview is needed for the state-ownership refactor. Ask the user only if research
work reveals a consequential choice not covered by the approved brief.
