"""M7 v2 confirmation protocol: pinned, new tasks, and v1 unchanged apart from D057."""

from __future__ import annotations

import pytest
import yaml

from attain_sampling.eval import m7, m7_v2
from attain_sampling.eval.m6 import ProtocolError, enumerate_jobs, protocol_digest


def test_the_frozen_v2_protocol_loads_and_is_pinned():
    text = m7_v2.PROTOCOL_PATH.read_text(encoding="utf-8")
    assert protocol_digest(text) == m7_v2.FROZEN_PROTOCOL_SHA256
    protocol = m7_v2.load_protocol()
    assert protocol["protocol_id"] == "m7-usv-heldout-v2"
    assert protocol["target"]["value"] == protocol["settings"]["target_mean_variance"] == 0.0774


def test_v2_tasks_are_new_and_the_rest_of_v1_is_unchanged():
    v1 = m7.load_protocol()
    v2 = m7_v2.load_protocol()
    seeds = {job.seed for job in enumerate_jobs(v2)}
    assert seeds == set(range(9201, 9241))
    assert not seeds & ({job.seed for job in enumerate_jobs(v1)} | set(range(9001, 9041)))
    assert [(j.block, j.variant, j.scenario) for j in enumerate_jobs(v2)] == [
        (j.block, j.variant, j.scenario) for j in enumerate_jobs(v1)
    ]
    for key in ("vehicle", "methods", "blocks", "analysis", "execution"):
        assert v2[key] == v1[key]
    changed = {k for k in v1["settings"] if v1["settings"][k] != v2["settings"][k]}
    assert changed == {"target_mean_variance"}


def test_a_changed_v2_protocol_is_refused(tmp_path):
    data = yaml.safe_load(m7_v2.PROTOCOL_PATH.read_text(encoding="utf-8"))
    data["tasks"]["seed_start"] = 9101
    path = tmp_path / "v2.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ProtocolError, match="differs from the frozen protocol"):
        m7_v2.load_protocol(path)
    with pytest.raises(ProtocolError, match="overlap"):
        m7_v2.load_protocol(path, require_frozen=False)
