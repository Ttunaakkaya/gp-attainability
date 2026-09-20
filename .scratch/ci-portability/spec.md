# Cross-platform validation of the existing baseline

Status: ready-for-agent
Date: 20 September 2026
Base commit: c256bac

The initial GitHub CI run passed on Windows but failed two Ubuntu tests: the DP
sample-to-target coordinate assertion and the prolonged dense SOGP stream. Resolve
both through reproducible public behavior before extending mission execution.

Preserve exact clock/provenance identities and geometric checks. Coordinate
comparisons after interpolation may admit only explicit numerical roundoff, with
zero relative tolerance. Keep the SOGP nonnegative-variance guard, bounded basis,
PSD/posterior checks and transactional update behavior. No changed kernel, noise,
novelty/pruning rule, or blanket variance clipping is authorized by this repair.

Use the existing run_mapping and GP update/predict/covariance seams. Capture the
failing local reproductions, explain the numerical correction, retain prior
reference artifacts, run targeted regressions, and finish with full quality checks
and two-platform CI. Record any change to historical scientific evidence precisely.
