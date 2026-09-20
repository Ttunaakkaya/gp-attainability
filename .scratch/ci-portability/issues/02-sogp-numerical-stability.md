# Stabilize unresolved SOGP dictionary novelty

Status: ready-for-agent
Execution: in-progress
Parent: [CI portability spec](../spec.md)

- [x] Reproduce negative novelty using an unmodified public dense-stream update.
- [x] Diagnose the error using an independent factorization of the same kernel.
- [x] Correct the supported numerical mechanism without weakening variance guards.
- [x] Validate covariance/PSD/accuracy, transactionality and runtime impact.
- [ ] Compare frozen mission references and pass complete quality checks and CI.

## Comments

Ubuntu rejects a dense stream at raw novelty -2.24578507e-08. A real local stream
also reproduces this issue with seed 4 and zero labels before pruning. Diagnosis
and the bounded correction are ongoing; no scientific preservation claim is made
until the reference comparison and full checks finish.

Local implementation and checks passed; see [completion evidence](../completion.md).
Final two-platform CI remains the closure gate.
