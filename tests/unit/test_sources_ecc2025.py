"""M5 ledger: audited citations, recorded source gaps, and no drift from the docs."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest
import yaml

from attain_sampling.sources.ecc2025 import (
    CLAIM_LIMITS,
    ECC2025_AUDIT,
    ECC2025_PARAMETERS,
    ECC2025_PUBLIC_VALUES,
    IMPLEMENTATION,
    SOURCE_INCONSISTENCIES,
    AuditTopic,
    SourceInconsistency,
    audit_status,
    blocked_claims,
    blocked_topics,
    difference_report,
    parameters,
    require_unlocked,
    unstated_items,
)

ROOT = Path(__file__).resolve().parents[2]
EQUATION_MAP = (ROOT / "docs" / "equation_map.md").read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def all_claims() -> set[str]:
    return {claim for topic in ECC2025_AUDIT for claim in topic.blocks}


def test_every_topic_is_audited_against_a_page_citation():
    assert len(ECC2025_AUDIT) == 9
    assert blocked_topics() == ()
    assert blocked_claims() == ()
    for topic in ECC2025_AUDIT:
        assert topic.status == "verified", topic.topic_id
        assert topic.evidence and "p. 30" in topic.evidence, topic.topic_id
    status = audit_status()
    assert status["topics_verified"] == 9
    assert status["topics_blocked"] == 0
    assert status["reproduction_available"] is True
    assert status["audited_on"] == "2026-09-15"


def test_topic_ids_are_unique_and_ordered():
    ids = [topic.topic_id for topic in ECC2025_AUDIT]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("claim", sorted(all_claims()))
def test_an_audited_claim_passes_the_gate(claim):
    require_unlocked(claim)


def test_an_unknown_claim_is_a_programming_error_not_a_silent_pass():
    with pytest.raises(ValueError):
        require_unlocked("ecc_something_invented")
    with pytest.raises(ValueError):
        require_unlocked("")


def test_a_topic_cannot_be_verified_without_a_citation():
    with pytest.raises(ValueError):
        AuditTopic(
            topic_id="T99",
            question="q",
            equation_objects=("x",),
            blocks=("y",),
            acceptance_test="t",
            status="verified",
        )


@pytest.mark.parametrize(
    "extra",
    [{"evidence": "p. 306, eq. (4)"}, {"unstated": ("something",)}],
)
def test_a_blocked_topic_cannot_carry_audit_results(extra):
    with pytest.raises(ValueError):
        AuditTopic(
            topic_id="T99",
            question="q",
            equation_objects=("x",),
            blocks=("y",),
            acceptance_test="t",
            status="blocked",
            **extra,
        )


def test_each_ledger_question_matches_the_paper_audit_document():
    text = normalized((ROOT / "docs" / "paper_audit.md").read_text(encoding="utf-8"))
    for topic in ECC2025_AUDIT:
        assert normalized(topic.question) in text, topic.topic_id


def test_the_ledger_covers_every_equation_map_row_exactly():
    table = EQUATION_MAP.split("| Paper eq./page |", 1)[1].split("\n## ", 1)[0]
    objects = {
        line.split("|")[2].strip()
        for line in table.splitlines()
        if line.startswith("| ") and len(line.split("|")) > 7 and "p. 3" in line.split("|")[1]
    }
    assert len(objects) == 18, sorted(objects)
    claimed = {name for topic in ECC2025_AUDIT for name in topic.equation_objects}
    assert claimed == objects


def test_every_recorded_source_gap_also_appears_in_the_equation_map():
    """What the paper omits must be listed in the document, not only in code."""
    section = normalized(EQUATION_MAP.split("## Not stated in the source", 1)[1])
    needles = {
        "order of simultaneous multi-robot samples within one epoch": "simultaneous",
        "class-K form for alpha_J beyond linearity": "Class-K form",
        "form and gain of alpha_ca": "form and gain",
        "input set U, speed bound and workspace-containment constraint": "Input set",
        "horizon and termination rule of the Bellman recursion (16)": "Horizon/termination",
        "random seeds": "Random seeds",
        "ground-truth Gaussian-mixture parameters and their sampling sets": "mixture parameters",
        "exact initial robot positions": "initial robot positions",
        "control period of the low-level loop": "Control period",
    }
    recorded = {item for _, item in unstated_items()}
    assert recorded == set(needles), recorded.symmetric_difference(set(needles))
    for item, needle in needles.items():
        assert needle in section, item


def test_claim_limits_reference_real_claims_and_survive_the_audit():
    assert set(CLAIM_LIMITS) <= all_claims()
    # A claim the source itself bounds must say so even though its topic is audited.
    assert "seed" in CLAIM_LIMITS["ecc_figure_reproduction"]
    assert audit_status()["limited_claims"] == dict(CLAIM_LIMITS)


def test_audited_parameters_match_the_equation_map_table():
    values = parameters()
    assert len(ECC2025_PARAMETERS) == len(values) == 17
    for item in ECC2025_PARAMETERS:
        assert 304 <= item.page <= 311, item.symbol
    assert values["L"] == 4.0
    assert values["sigma_eps"] == 0.4
    assert values["omega"] == 0.1
    assert values["rho"] == 0.9
    assert values["epsilon_opt"] == 0.1
    assert values["t_s"] == 10.0
    assert values["alpha_J"] == 1e-4
    assert values["d_ca"] == 3.0
    assert values["gamma"] == 60.0
    assert values["epsilon_tol"] == 3.0
    assert values["n_d_max"] == 360
    assert values["kappa"] == 15.0
    assert values["n"] == 3
    assert values["evaluation_points"] == 900
    # The field is the paper's square, not the independent 60 x 40 m development domain.
    assert values["field_m"] == (-60.0, 60.0, -60.0, 60.0)


def test_the_paper_field_is_not_confused_with_the_independent_development_domain():
    from attain_sampling.sim.mapping import MappingConfig

    assert MappingConfig().domain == (60.0, 40.0)
    assert parameters()["cell_m"] == 10.0


def test_public_author_page_values_stay_labelled_as_provenance_only():
    assert all(value.provenance == "AUTHOR_PAGE" for value in ECC2025_PUBLIC_VALUES)
    # The audited workspace agrees with the author page's 120 m extent.
    left, right, bottom, top = parameters()["field_m"]
    assert (right - left, top - bottom) == dict(
        (value.name, value.value) for value in ECC2025_PUBLIC_VALUES
    )["workspace_m"]


def test_the_locked_reproduction_config_still_agrees_with_the_ledger():
    config = yaml.safe_load(
        (ROOT / "configs" / "reproduction" / "ecc2025.yaml").read_text(encoding="utf-8")
    )
    assert config["source"]["doi"] == audit_status()["doi"]
    recorded = {value.name: value for value in ECC2025_PUBLIC_VALUES}
    assert set(config["verified_public_values"]) == set(recorded)
    for name, entry in config["verified_public_values"].items():
        actual = tuple(entry["value"]) if isinstance(entry["value"], list) else entry["value"]
        assert actual == recorded[name].value


def test_difference_report_states_an_implemented_qualitative_profile():
    report = difference_report()
    json.dumps(report, allow_nan=False)
    assert report["status"] == "ecc2025_profile_implemented_qualitative_comparison"
    assert report["anchor"]["full_text"] == "audited"
    assert report["open_topics"] == []
    assert len(report["audited_topics"]) == 9
    assert len(report["unstated_in_source"]) == 9
    assert any("not a numerical reproduction" in limit for limit in report["claim_limits"])
    assert report["implementation"] == IMPLEMENTATION
    assert len(report["source_inconsistencies"]) == len(SOURCE_INCONSISTENCIES)
    assert any("never inferred" in limit for limit in report["claim_limits"])


def test_no_shipped_module_produces_an_ecc_labelled_artifact_yet():
    """The audit does not entitle any run to call itself an ECC reproduction."""
    banned = re.compile(r"ecc[_ ]?(reproduction|reproduced)\s*[:=]\s*True", re.IGNORECASE)
    for path in (ROOT / "src").rglob("*.py"):
        assert not banned.search(path.read_text(encoding="utf-8")), path


def test_every_implementation_entry_exists():
    for component, target in IMPLEMENTATION.items():
        if target.endswith(".py"):
            assert (ROOT / target).is_file(), component
        else:
            importlib.import_module(target)


def test_source_inconsistencies_cite_pages_and_logged_decisions():
    decisions = (ROOT / "docs" / "decision_log.md").read_text(encoding="utf-8")
    ids = [item.finding_id for item in SOURCE_INCONSISTENCIES]
    assert ids == [f"R0{index}" for index in range(1, len(ids) + 1)]
    for item in SOURCE_INCONSISTENCIES:
        assert "p. " in item.where
        assert f"| {item.decision} |" in decisions, item.finding_id


def test_the_equation_map_carries_the_reading_notes():
    assert "## Reading notes found while running the source profile" in EQUATION_MAP
    assert "## Reading note: equation (12) versus its own derivation" in EQUATION_MAP
    for phrase in ("Replanning.", "Novelty test.", "Scale of `J`.", "Attainable decay."):
        assert phrase in EQUATION_MAP
    assert "Start and entry." in EQUATION_MAP


@pytest.mark.parametrize(
    ("where", "decision", "message"),
    [("Fig. 3", "D042", "page"), ("p. 307", "042", "decision-log")],
)
def test_an_inconsistency_needs_a_page_and_a_decision(where, decision, message):
    with pytest.raises(ValueError, match=message):
        SourceInconsistency("R99", where, "finding", "handling", decision)
