# Single grid-sensitivity diagnostic, declared before execution

20 September 2026. The original 15-mission batch is complete and preserved in
`results/`. It found no target-crossing opportunities and no benefit from target
priority. Its nominal B3 and P both travel only 6.732362983457671 m in total,
receive at four distinct sites, and repeat their first reached grid cells.
B2 travels 78.41135313155357 m and receives at 22 distinct sites.

For the 5 x 4 planner grid on 20 x 14 m, adjacent cells are separated by 5 m
horizontally and 14/3 = 4.666666666666667 m vertically. Both exceed the maximum
4 m travel in one 2 s sampling interval. The initial cells are reachable from
the off-grid starting positions, but from a grid cell only itself is reachable
at the next epoch. The recorded initial B3/P candidates repeat exactly those
first targets, supporting this diagnosis without adding any experiments.

Run exactly one follow-up batch with `dp_grid_shape=(7,5)`; adjacent spacings
20/6 = 3.3333333333333335 and 14/4 = 3.5 m are within that same 4 m budget.
Every other config, the five arms and three drifts stay unchanged. Reuse the
already frozen numeric target 0.17797860776402111 from `results/calibration.json`.
Do not recalibrate. Save all 15 results separately in `results-grid7x5/`.

This is a post-pilot development diagnosis prompted by observed outcomes, not a
replacement of the initial protocol, a fresh test or held-out evidence. Do not
try another grid, seed, target or candidate cap afterward. The comparison still
does not charge decision time, calibrate warnings, or evaluate adaptive continuation.
