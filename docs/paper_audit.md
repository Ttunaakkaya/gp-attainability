# Anchor paper audit

## Status

**The ECC 2025 full-text audit was completed on 15 September 2026, and the `ecc2025` source
profile was implemented on 16 September.** The profile supports a qualitative comparison,
not a numerical reproduction ([M5 results](../reports/m5_results_2026-09-15.md)). Under the
[active masterplan v2.0](../GP_Attainability_Masterplan_TR.md), this is the `ecc2025`
profile's source gate (M5), not a prerequisite for independent development. Source-attributed
SOGP, independently defined MDP/Bellman-DP, QP/constraint control and execution/budget
management may proceed now. See [continuation notes](CONTINUE_HERE.md).

The public-source facts below retain their 2026-09-01 audit scope; installing the new
plan is not a new literature audit or completion of its implementation milestones.

## Publicly verified facts

| Fact | Evidence class | Current code/config consequence |
|---|---|---|
| Three robots | `AUTHOR_PAGE` | Stored only as a verified public placeholder |
| 120 m x 120 m workspace | `AUTHOR_PAGE` | Stored only as a verified public placeholder |
| Sampling every 10 s | `AUTHOR_PAGE` | Public-source placeholder; current independent demo samples every 5 s |
| 900 evaluation points (30 x 30) | `AUTHOR_PAGE` | Paper/report grids remain separately named |
| Central sparse online GP | `AUTHOR_PAGE` | Belief backend is not called fully distributed |
| Per-robot QP on a Voronoi share | `AUTHOR_PAGE` | Distributed controller must have a centralized oracle check |
| Collision-avoidance barrier | `AUTHOR_PAGE` | Safety and performance constraint blocks stay separate |
| Constraint-only controller deadlocks | `AUTHOR_PAGE` | E0 qualitative reproduction target under v2 naming |
| Coarse MDP uses uncertainty and distance | `AUTHOR_PAGE` | Planner contract returns a timed sample plan, not only waypoints |
| Hierarchy reaches remote uncertain regions | `AUTHOR_PAGE` | E1 qualitative reproduction target under v2 naming |
| Both methods eventually lose the requested rate | `AUTHOR_PAGE` | Failure mechanism must be audited rather than assumed |

## Unresolved questions for paper-specific code and claims

These nine questions are mirrored by the machine-checked ledger
`attain_sampling.sources.ecc2025` (topics T01-T09). The ledger, this list and
[equation_map.md](equation_map.md) are asserted consistent by tests, and every
ECC-specific claim is refused at the gate while its topic is open. See the
[M5 protocol](M5_SOURCE_ALIGNMENT.md) and the
[recorded gap](../reports/m5_results_2026-09-15.md).

1. **T01** — Does the objective use latent posterior variance, observation-predictive variance, or a
   different sparse-GP variance quantity?
2. **T02** — Is the field integral a normalized sum, unnormalized sum, maximum, or another form?
3. **T03** — Which Csató-Opper equations and basis admission/pruning score are used?
4. **T04** — Is dictionary pruning label-dependent, and in what order are simultaneous robot samples
   processed?
5. **T05** — What is the exact desired-decay inequality, sign convention, slack convention, and slack
   penalty?
6. **T06** — Which safety CBF and robot dynamics are used, and are workspace/input constraints present?
7. **T07** — How is the global objective partitioned and what information is centralized?
8. **T08** — What are the MDP states, actions, transition, reward, horizon, discount, cell construction,
   assignment, and replanning trigger?
9. **T09** — What are all numerical parameters, initial conditions, field definition, seeds, and figure
   snapshot times?

## Mandatory branch record

```text
PAPER_OBJECTIVE_VARIANCE = ambiguous
Evidence = full paper unavailable as of 2026-09-01
Allowed independent implementation = Exact GP, source-attributed SOGP, own MDP/DP and QP
Allowed independent extension = timed plans, controller rollout, execution/budget management
Forbidden claim = guessed equations/parameters presented as ECC reproduction or ECC results
```

The sentence on the author page that sensor noise prevents the variance from reaching zero
is a reported interpretation, not enough evidence to classify the variance mathematically.
