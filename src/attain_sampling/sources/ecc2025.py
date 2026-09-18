"""The ECC 2025 source-alignment ledger and its gate (masterplan v2 M5).

M5 implements the anchor paper's equations, parameters and baselines in a separate
``ecc2025`` profile and reports the differences. The full text was obtained and audited
on 15 September 2026, so every topic below now carries a page/equation citation read
directly from the paper. This module remains the machine-checked ledger so that

- each audit question records exactly where its answer was read;
- a claim cannot be produced while any topic it depends on is still open;
- what the *source itself* leaves unspecified is recorded separately, as a bound on
  what a reproduction may claim, never filled in by inference.

Anchor: Suenaga, Hanif, Uto and Hatanaka, *Hierarchical Multi-Robot Data Sampling for
Environmental State Estimation through Online Gaussian Process*, ECC 2025, pp. 304-311,
doi:10.23919/ECC65951.2025.11187026.

A topic moves to ``verified`` only from a page/equation citation read directly in the
paper, recorded in `docs/equation_map.md` and in a `docs/decision_log.md` entry. A
remembered equation, an adjacent paper, or the public author summary never unlocks one.
The public values below are the author page's stated setup; they are a provenance
record, not paper equations, and they never unlocked anything.

``unstated`` entries are gaps in the paper, not gaps in the audit. They force recorded
project choices and they bound the claims listed in :data:`CLAIM_LIMITS`: without the
random seeds and the ground-truth mixture parameters, figures can be compared
qualitatively but never numerically reproduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "ECC2025_AUDIT",
    "ECC2025_PARAMETERS",
    "ECC2025_PUBLIC_VALUES",
    "IMPLEMENTATION",
    "SOURCE_INCONSISTENCIES",
    "AuditTopic",
    "PublicValue",
    "SourceInconsistency",
    "SourceParameter",
    "SourceGateError",
    "audit_status",
    "blocked_claims",
    "blocked_topics",
    "difference_report",
    "parameters",
    "require_unlocked",
    "unstated_items",
]

Provenance = Literal["AUTHOR_PAGE", "FULL_TEXT", "PROJECT_CHOICE"]
TopicStatus = Literal["blocked", "verified"]

CITATION = "Suenaga, Hanif, Uto and Hatanaka, ECC 2025, pp. 304-311"
DOI = "10.23919/ECC65951.2025.11187026"
ANCHOR_FILENAME = "suenaga_et_al_ecc2025.pdf"
AUDITED_ON = "2026-09-15"
# Claims the source itself bounds, however well they are implemented.
CLAIM_LIMITS: dict[str, str] = {
    "ecc_figure_reproduction": (
        "qualitative only: the paper publishes no random seed and no ground-truth "
        "Gaussian-mixture parameters, so its curves cannot be matched numerically"
    ),
    "ecc_controller_reproduction": (
        "alpha_ca, the input set U and the low-level control period are project "
        "choices; the controller is reproduced up to those settings"
    ),
    "ecc_planner_reproduction": (
        "the horizon and termination rule of the Bellman recursion are project choices"
    ),
    "ecc_sogp_equivalence": (
        "the order of simultaneous multi-robot samples in one epoch is a project "
        "choice and can change label-dependent pruning"
    ),
}


# Where each audited piece lives. Tests assert these modules import.
IMPLEMENTATION: dict[str, str] = {
    "sogp": "attain_sampling.gp.sogp",
    "decay_rate_row": "attain_sampling.control.rate_constraint",
    "per_robot_qp": "attain_sampling.control.ecc_qp",
    "cell_planner": "attain_sampling.planning.cell_mdp",
    "closed_loop_profile": "attain_sampling.sim.ecc2025",
    "figures": "attain_sampling.sim.ecc2025_figures",
    "validation": "scripts/validate_m5.py",
}


class SourceGateError(RuntimeError):
    """Raised when an ECC-specific claim is attempted while its topic is blocked."""


@dataclass(frozen=True, slots=True)
class AuditTopic:
    """One unresolved source question, with what it blocks and how to close it."""

    topic_id: str
    question: str
    equation_objects: tuple[str, ...]
    blocks: tuple[str, ...]
    acceptance_test: str
    status: TopicStatus = "blocked"
    evidence: str | None = None
    unstated: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "verified" and not self.evidence:
            raise ValueError(f"{self.topic_id} cannot be verified without a page/equation citation")
        if self.status == "blocked" and self.evidence:
            raise ValueError(f"{self.topic_id} is blocked, so it must carry no citation")
        if self.status == "blocked" and self.unstated:
            raise ValueError(f"{self.topic_id} cannot record source gaps before it is audited")

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "question": self.question,
            "equation_objects": list(self.equation_objects),
            "blocks": list(self.blocks),
            "acceptance_test": self.acceptance_test,
            "status": self.status,
            "evidence": self.evidence,
            "unstated": list(self.unstated),
        }


@dataclass(frozen=True, slots=True)
class PublicValue:
    """A setup value stated on the author page, not read from the paper."""

    name: str
    value: Any
    provenance: Provenance
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "provenance": self.provenance,
            "note": self.note,
        }


# The nine questions of docs/paper_audit.md, in the same order. `equation_objects`
# name the rows of docs/equation_map.md each question must close; a consistency test
# keeps the three records from drifting apart.
ECC2025_AUDIT: tuple[AuditTopic, ...] = (
    AuditTopic(
        topic_id="T01",
        question=(
            "Does the objective use latent posterior variance, observation-predictive "
            "variance, or a different sparse-GP variance quantity?"
        ),
        equation_objects=("Global objective", "SOGP variance"),
        blocks=("ecc_objective_semantics", "ecc_figure_reproduction"),
        acceptance_test="Recompute the paper's reported objective on its stated setup",
        status="verified",
        evidence=(
            "p. 306, eq. (4): sigma^2(x) = k(x,x) + k_{x,l}^T C_l k_{x,l}, latent; no sigma_eps^2 "
            "term is added, and J is built from that same sigma^2"
        ),
    ),
    AuditTopic(
        topic_id="T02",
        question=(
            "Is the field integral a normalized sum, unnormalized sum, maximum, or another form?"
        ),
        equation_objects=("Global objective",),
        blocks=("ecc_objective_semantics",),
        acceptance_test="Direct grid sum matches the paper's definition and units",
        status="verified",
        evidence=(
            "p. 306: J = sum over x in F_d of sigma^2(x), an unnormalized sum over m evenly "
            "distributed points; |F_d| = 900 (p. 308)"
        ),
    ),
    AuditTopic(
        topic_id="T03",
        question="Which Csató-Opper equations and basis admission/pruning score are used?",
        equation_objects=("SOGP mean", "SOGP variance", "Basis admission"),
        blocks=("ecc_sogp_equivalence",),
        acceptance_test="Exact replay of the paper's update on a fixed observation stream",
        status="verified",
        evidence=(
            "p. 305: eq. (1) online updates; novelty beta_{tau+1} = k(x,x) - k^T Q_tau k; admit "
            "iff beta >= omega, else project (omega = 0.1, Table I p. 310)"
        ),
    ),
    AuditTopic(
        topic_id="T04",
        question=(
            "Is dictionary pruning label-dependent, and in what order are simultaneous "
            "robot samples processed?"
        ),
        equation_objects=("Basis pruning",),
        blocks=("ecc_sogp_equivalence", "ecc_forecast_semantics"),
        acceptance_test="Prune replay plus a changed-label scenario",
        status="verified",
        evidence=(
            "p. 305: removal score eta_i = |[a_{tau+1}]_i| / [Q_{tau+1}]_ii at capacity n_d,max = "
            "360; a depends on observations, so pruning is label-dependent"
        ),
        unstated=("order of simultaneous multi-robot samples within one epoch",),
    ),
    AuditTopic(
        topic_id="T05",
        question=(
            "What is the exact desired-decay inequality, sign convention, slack "
            "convention, and slack penalty?"
        ),
        equation_objects=("Desired rate", "Task slack", "QP objective"),
        blocks=("ecc_performance_constraint", "ecc_slack_comparison"),
        acceptance_test="Analytic constraint row reproduced with its stated units",
        status="verified",
        evidence=(
            "pp. 306-308: eq. (5) J[l] <= J[0] - l*gamma; eq. (6) continuous form; eq. (7) per- "
            "robot; eq. (8) hdot_J + alpha_J(h_J) >= w_i; eqs. (12)-(13) the xi rows"
        ),
        unstated=("class-K form for alpha_J beyond linearity",),
    ),
    AuditTopic(
        topic_id="T06",
        question=(
            "Which safety CBF and robot dynamics are used, and are workspace/input "
            "constraints present?"
        ),
        equation_objects=("Collision CBF", "Input/boundary", "Robot dynamics"),
        blocks=("ecc_controller_reproduction",),
        acceptance_test="Head-on and sampled-data constraint fixtures",
        status="verified",
        evidence=(
            "p. 305 eq. (2) single integrator; p. 307 eq. (9) with h_ca,ij = ||p_i-p_j||^2 - "
            "d_ca^2, d_ca = 3.0 m (Table I p. 310)"
        ),
        unstated=(
            "form and gain of alpha_ca",
            "input set U, speed bound and workspace-containment constraint",
        ),
    ),
    AuditTopic(
        topic_id="T07",
        question="How is the global objective partitioned and what information is centralized?",
        equation_objects=("Local decomposition",),
        blocks=("ecc_distributed_claim",),
        acceptance_test="Local-to-global sum against a centralized oracle",
        status="verified",
        evidence=(
            "p. 306: Voronoi V_i(p) and J~_l(t) = sum_i I_il(t); p. 307: I~_il uses Z~_ti[l] = "
            "Z[l] + p_i(t) only; p. 306: the SOGP update (4) is run centrally"
        ),
    ),
    AuditTopic(
        topic_id="T08",
        question=(
            "What are the MDP states, actions, transition, reward, horizon, discount, "
            "cell construction, assignment, and replanning trigger?"
        ),
        equation_objects=(
            "MDP state/action",
            "MDP reward",
            "Planning/replanning",
        ),
        blocks=("ecc_planner_reproduction",),
        acceptance_test="Tiny exhaustive DP fixture matching the paper's recursion",
        status="verified",
        evidence=(
            "p. 308: (B_i, A_i, T_i, R_i), 10 m cells (p. 310), deterministic T_i = 1; p. 309: "
            "R_i = sigma^2_c,b' / ||x_c,b' - x_c,b||, eq. (16) with rho = 0.9"
        ),
        unstated=("horizon and termination rule of the Bellman recursion (16)",),
    ),
    AuditTopic(
        topic_id="T09",
        question=(
            "What are all numerical parameters, initial conditions, field definition, "
            "seeds, and figure snapshot times?"
        ),
        equation_objects=(
            "Field/observation",
            "Kernel/prior",
            "Sampling/control clocks",
        ),
        blocks=("ecc_figure_reproduction", "ecc_parameter_lock"),
        acceptance_test="Figure snapshot times and curves reproduced within a declared tolerance",
        status="verified",
        evidence=(
            "p. 310 Table I (L, sigma_eps, omega, rho, eps_opt, t_s, alpha_J, d_ca, gamma, "
            "eps_tol, n_d,max, kappa); p. 308 field [-60,60]^2, n = 3, |F_d| = 900, snapshots t = "
            "0/320/640/1000 s; p. 310 10 m cells, robots start outside F"
        ),
        unstated=(
            "random seeds",
            "ground-truth Gaussian-mixture parameters and their sampling sets",
            "exact initial robot positions",
            "control period of the low-level loop",
        ),
    ),
)

# Stated on the author project page, not read from the paper. Held as provenance only:
# they do not unlock a topic and the independent development profile does not use them.
ECC2025_PUBLIC_VALUES: tuple[PublicValue, ...] = (
    PublicValue("robot_count", 3, "AUTHOR_PAGE", "public placeholder; independent demo uses 2-4"),
    PublicValue(
        "workspace_m", (120.0, 120.0), "AUTHOR_PAGE", "public placeholder; independent uses 60x40"
    ),
    PublicValue(
        "sampling_period_s", 10.0, "AUTHOR_PAGE", "public placeholder; independent uses 5 s"
    ),
    PublicValue(
        "evaluation_grid", (30, 30), "AUTHOR_PAGE", "public placeholder; independent uses 24x16"
    ),
)


@dataclass(frozen=True, slots=True)
class SourceParameter:
    """A value read from the paper, with the page it was read on."""

    symbol: str
    value: Any
    units: str | None
    page: int
    meaning: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "value": self.value,
            "units": self.units,
            "page": self.page,
            "meaning": self.meaning,
        }


# Table I, p. 310, plus the setup stated in Sections IV-B and VI. Every entry was read
# from the full text; nothing here is inferred, and the settings the paper omits are in
# each topic's `unstated` list rather than filled in with a plausible number.
ECC2025_PARAMETERS: tuple[SourceParameter, ...] = (
    SourceParameter("L", 4.0, None, 307, "RBF length scale in Theorem 1"),
    SourceParameter("sigma_eps", 0.4, None, 306, "sensor-noise standard deviation in (3)"),
    SourceParameter("omega", 0.1, None, 305, "SOGP novelty admission threshold"),
    SourceParameter("rho", 0.9, None, 309, "discount rate of the Bellman recursion (16)"),
    SourceParameter("epsilon_opt", 0.1, None, 307, "input weight in the QP (10)"),
    SourceParameter("t_s", 10.0, "s", 306, "sampling period"),
    SourceParameter("alpha_J", 1e-4, None, 307, "linear gain of the class-K function on J"),
    SourceParameter("d_ca", 3.0, "m", 307, "minimum inter-robot distance"),
    SourceParameter("gamma", 60.0, None, 306, "performance level in the decay constraint (5)"),
    SourceParameter("epsilon_tol", 3.0, "m", 310, "waypoint arrival tolerance in Algorithm 1"),
    SourceParameter("n_d_max", 360, None, 305, "SOGP basis-vector capacity"),
    SourceParameter("kappa", 15.0, None, 309, "nominal feedback gain"),
    SourceParameter("n", 3, None, 308, "number of robots in the simulation"),
    SourceParameter("field_m", (-60.0, 60.0, -60.0, 60.0), "m", 308, "square mission field F"),
    SourceParameter("evaluation_points", 900, None, 308, "|F_d|, evenly distributed"),
    SourceParameter("cell_m", 10.0, "m", 310, "square planner cell side"),
    SourceParameter(
        "snapshot_times_s", (0.0, 320.0, 640.0, 1000.0), "s", 308, "Fig. 2 snapshot times"
    ),
)


@dataclass(frozen=True, slots=True)
class SourceInconsistency:
    """A place where the paper's text, algorithm or figures disagree with each other.

    Found while implementing the profile, not while auditing a single topic. Each entry
    names where it was read and how the profile handles it; none is resolved by guessing.
    """

    finding_id: str
    where: str
    finding: str
    handling: str
    decision: str

    def __post_init__(self) -> None:
        if "p. " not in self.where:
            raise ValueError(f"{self.finding_id} must cite the page it was read on")
        if not self.decision.startswith("D"):
            raise ValueError(f"{self.finding_id} must name its decision-log entry")

    def as_dict(self) -> dict[str, str]:
        return {
            "finding_id": self.finding_id,
            "where": self.where,
            "finding": self.finding,
            "handling": self.handling,
            "decision": self.decision,
        }


# Mirrors "Reading notes" in docs/equation_map.md; figure values are read approximately.
SOURCE_INCONSISTENCIES: tuple[SourceInconsistency, ...] = (
    SourceInconsistency(
        "R01",
        "p. 307, eq. (12) versus the derivation of (14)-(15)",
        "printed (12) omits the [z*]_{N+1} factor on the basis term and the V_i restriction",
        "the derivation form is implemented and checked by finite differences",
        "D037",
    ),
    SourceInconsistency(
        "R02",
        "p. 309 text and Fig. 5 versus Algorithm 1, p. 310",
        "the text replans after every sample; Algorithm 1 replans only on an empty route",
        "the text is followed; an exhausted route is replanned as in Algorithm 1",
        "D041",
    ),
    SourceInconsistency(
        "R03",
        "p. 305, novelty test",
        "the beta < omega discard is described only for a sample arriving at capacity",
        "novelty is tested at every step, as in the cited SOGP [22]",
        "D041",
    ),
    SourceInconsistency(
        "R04",
        "p. 308 versus Figs. 3 and 6, pp. 307 and 311",
        "900 points with k(x,x) = 1 give J[0] = 900; the figures start near 3600",
        "k(x,x) = 1 is primary; k(x,x) = 4 is run as a recorded figure-scale sensitivity",
        "D042",
    ),
    SourceInconsistency(
        "R05",
        "Table I, p. 310, versus Figs. 3 and 6",
        "the figures follow gamma = 60 for about 150 s (about 57 per epoch); an isolated "
        "sample allows about 8 (k = 1) or 36 (k = 4) per epoch for three robots",
        "reported; gamma is kept at the printed value",
        "D042",
    ),
    SourceInconsistency(
        "R06",
        "p. 310 and Figs. 2 and 4a, t = 0",
        "one robot starts at the square 16-17 m from F_d, where (10) moves it at about "
        "1e-6 to 1e-5 m/s, yet Fig. 2 shows every robot inside F by t = 320 s",
        "the square start is primary; an edge start is run as a recorded sensitivity",
        "D043",
    ),
)


def parameters() -> dict[str, Any]:
    """Return the audited paper values keyed by symbol."""
    return {item.symbol: item.value for item in ECC2025_PARAMETERS}


def blocked_topics() -> tuple[AuditTopic, ...]:
    """Return every topic still waiting on the full text, in ledger order."""
    return tuple(topic for topic in ECC2025_AUDIT if topic.status == "blocked")


def blocked_claims() -> tuple[str, ...]:
    """Return the sorted set of claims that stay locked while topics are blocked."""
    claims: set[str] = set()
    for topic in blocked_topics():
        claims.update(topic.blocks)
    return tuple(sorted(claims))


def unstated_items() -> tuple[tuple[str, str], ...]:
    """Return `(topic_id, item)` pairs the paper itself does not specify.

    These are gaps in the source, not gaps in the audit. They force recorded project
    choices and they bound the claims in :data:`CLAIM_LIMITS`.
    """
    return tuple((topic.topic_id, item) for topic in ECC2025_AUDIT for item in topic.unstated)


def audit_status() -> dict[str, Any]:
    """Machine-readable M5 state for `doctor` and the difference report."""
    blocked = blocked_topics()
    return {
        "citation": CITATION,
        "doi": DOI,
        "anchor_filename": ANCHOR_FILENAME,
        "audited_on": AUDITED_ON,
        "topics_total": len(ECC2025_AUDIT),
        "topics_verified": len(ECC2025_AUDIT) - len(blocked),
        "topics_blocked": len(blocked),
        "blocked_topic_ids": [topic.topic_id for topic in blocked],
        "blocked_claims": list(blocked_claims()),
        "reproduction_available": not blocked,
        "unstated_in_source": [
            {"topic_id": topic_id, "item": item} for topic_id, item in unstated_items()
        ],
        "limited_claims": dict(CLAIM_LIMITS),
        "scope": (
            "every audit question carries a page/equation citation; items the paper "
            "leaves unspecified are recorded as project choices and bound what a "
            "reproduction may claim"
        ),
    }


def require_unlocked(claim: str) -> None:
    """Refuse an ECC-specific claim while any topic that blocks it is unresolved.

    Every future ``ecc2025`` code path calls this before producing an artifact. The
    error names the exact topics to close, so a blocked claim can never be downgraded
    into a guess, and it is never a statement about the paper's correctness.
    """
    if not isinstance(claim, str) or not claim.strip():
        raise ValueError("claim must be a non-empty string")
    offending = [topic for topic in blocked_topics() if claim in topic.blocks]
    if not offending:
        if claim in {item for topic in ECC2025_AUDIT for item in topic.blocks}:
            return
        raise ValueError(f"unknown ECC claim: {claim!r}")
    ids = ", ".join(topic.topic_id for topic in offending)
    raise SourceGateError(
        f"ECC claim {claim!r} is locked: {ids} still require the full text "
        f"({ANCHOR_FILENAME}, doi:{DOI}). Record the page/equation citation in "
        "docs/equation_map.md and a decision-log entry before unlocking."
    )


def difference_report() -> dict[str, Any]:
    """The M5 difference report: what the source fixes, and what it leaves open.

    It records where every answer was read and which settings the paper does not
    publish. It is not itself a reproduction result.
    """
    return {
        "anchor": {
            "citation": CITATION,
            "doi": DOI,
            "full_text": "audited",
            "audited_on": AUDITED_ON,
        },
        "status": "ecc2025_profile_implemented_qualitative_comparison",
        "independent_profile": "complete through M4 and reported separately from the paper",
        "implementation": dict(IMPLEMENTATION),
        "source_inconsistencies": [item.as_dict() for item in SOURCE_INCONSISTENCIES],
        "public_values": [value.as_dict() for value in ECC2025_PUBLIC_VALUES],
        "open_topics": [topic.as_dict() for topic in blocked_topics()],
        "audited_topics": [
            topic.as_dict() for topic in ECC2025_AUDIT if topic.status == "verified"
        ],
        "unstated_in_source": [
            {"topic_id": topic_id, "item": item} for topic_id, item in unstated_items()
        ],
        "limited_claims": dict(CLAIM_LIMITS),
        "claim_limits": [
            "the implemented profile is compared qualitatively against pre-declared criteria; "
            "it is not a numerical reproduction",
            "settings the paper does not publish are project choices, never inferred",
            "without seeds and ground-truth parameters, figures are comparable only qualitatively",
            "public author-page values are provenance only and unlock nothing",
            "the independent results are not presented as the paper's results",
        ],
    }
