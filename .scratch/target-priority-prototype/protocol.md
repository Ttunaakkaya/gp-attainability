# Target-priority pilot: predeclared development protocol

Declared 20 September 2026 before calibration or comparison. Throwaway prototype;
no held-out evaluation, warning calibration, robustness guarantee or charged delay.

Question: should a feasible, already-scored candidate reaching the fixed target
override hysteresis when the retained candidate misses it? Does this narrow change
produce a visible benefit over ordinary adaptive B2 in a small motion-error pilot?

ExactGP, holonomic, filter controller; two robots, domain 20 x 14 m, deadline 20 s,
dt 0.5 s, samples every 2 s, uniform evaluation grid 12 x 8, DP grid 5 x 4,
horizon 2 epochs, length scale 3 m, maximum speed 2 m/s, seed 7, no dropout.
All other MappingConfig defaults stay fixed, including minimum separation 2 m,
noise standard deviation 0.15 and switch margin 0.01. The target is 1.05 times
the nominal adaptive-B2 final mean latent variance from one calibration run. Write
that numeric target before comparison, then use it unchanged in all 15 missions.

Run every combination of drifts 0, 0.35, 1.0 m/s and arms adaptive B2, DP B3,
historical P, target-priority P, and historical P with switch margin zero. Compare
final mean/max latent variance, actual RMSE, target successes, failures, planning
and total wall time, candidate counts, target-crossing decisions, and first changed
route and received sample relative to historical P. Common physical resources and
indexed future motion-error stream remain unchanged. Planning wall time is measured
but does not consume simulated mission time. B2 does not pay for P's search.

No tuning, repeated seed selection, target changes, or rejection of unfavorable
cases. Small effect or no effect is an answer. The nominal candidate + hold forecast
is not ordinary adaptive continuation. HTML numbers are illustrative, independent
of simulator evidence. Production decision is owned by the parent task; prototype
source and raw evidence remain on the separate throwaway branch.

Historical policy saved before edits as `legacy_policy.py`, SHA-256
`492d7d00d4c1b57eb11e0bb129ceda5d047aa8b5b26ef24fbd1b21884c8d195f`.
