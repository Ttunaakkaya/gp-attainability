# GP environmental mapping

A robot team gathers environmental measurements during a time-limited mapping
mission. The research focus is early warning of a missed mission target and
replanning that improves the chance of meeting it.

## Language

**Mission execution**:
The robot team's actual motion, measurement receipt, and estimation over the
original mission clock, including any failed or incomplete outcome.
_Avoid_: Nominal rollout, completed mission only

**Ordinary continuation**:
The remainder of a mission under its ordinary adaptive planner, using the states
and measurements it actually receives and retaining its normal replanning behavior.
_Avoid_: Frozen route, stopped adaptation, recovery replanning

**Mission target**:
A bound on average GP uncertainty fixed before a mission that must be met by the
original mission deadline.
_Avoid_: Plan forecast, moving target

**Model uncertainty**:
The GP's posterior uncertainty about the environmental field under its assumed
model and received measurements.
_Avoid_: Actual map error

**Actual map error**:
The discrepancy between the estimated environmental field and the true field.
_Avoid_: Posterior variance

**Early warning**:
An explainable prediction made before the mission deadline that a specified
continuation is expected to miss the fixed mission target.
_Avoid_: Impossibility certificate, calibrated failure probability

**Target margin**:
The fixed uncertainty target minus the predicted average uncertainty at the
mission deadline for a specified continuation; negative values predict a miss.
_Avoid_: Failure probability

**Recovery replanning**:
Changing routes and sampling assignments to improve the chance of meeting the
mission target while preserving the original deadline, robot team, sensing limits,
and safety constraints.
_Avoid_: Guaranteed recovery

**Planning delay**:
The mission time consumed by forecasting and replanning before a resulting decision
is available for execution; the robots and original mission clock continue meanwhile.
_Avoid_: Paused mission time, offline analysis runtime
