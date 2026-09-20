"""M8 demo additions: guided showcases, the turn-constrained USV and a fixed target."""

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from attain_sampling.attainability import policy
from attain_sampling.demo.server import DemoServer

ROOT = Path(__file__).resolve().parents[2]


def _serve(output_root: Path, showcase_root: Path | None = None) -> Iterator[DemoServer]:
    with DemoServer(0, output_root, showcase_root) as server:
        worker = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join(timeout=2.0)


def _request(server: DemoServer, path: str, body: str | None = None) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=60)
    try:
        method = "GET" if body is None else "POST"
        headers = {} if body is None else {"Content-Type": "application/json"}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


@pytest.fixture
def showcase_root(tmp_path: Path) -> Path:
    root = tmp_path / "showcases"
    (root / "demo" / "run").mkdir(parents=True)
    recording = json.dumps({"runs": [], "note": "stand-in recording"}).encode()
    (root / "demo" / "run" / "comparison.json").write_bytes(recording)
    (tmp_path / "outside.json").write_bytes(recording)
    manifest = {
        "showcases": [
            {
                "id": "demo",
                "title": "A card",
                "question": "What happens?",
                "look_for": ["this"],
                "evidence": "held-out report",
                "focus": "p",
                "compare": True,
                "key_time_s": 10.0,
                "key_moment": "At 10 s something happened.",
                "facts": [["Final map RMSE", "B3 0.1"]],
                "config": {"seed": 7},
                "comparison": "demo/run/comparison.json",
                "sha256": hashlib.sha256(recording).hexdigest(),
            },
            {
                "id": "escape",
                "title": "Outside the root",
                "comparison": "../outside.json",
                "sha256": hashlib.sha256(recording).hexdigest(),
            },
            {"id": "../bad", "title": "Invalid id", "comparison": "demo/run/comparison.json"},
        ]
    }
    (root / "showcases.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


@pytest.fixture
def server(tmp_path: Path, showcase_root: Path) -> Iterator[DemoServer]:
    yield from _serve(tmp_path / "runs", showcase_root)


def test_showcase_cards_are_served_without_paths_or_hashes(server: DemoServer) -> None:
    status, body = _request(server, "/api/showcases")
    assert status == 200
    cards = json.loads(body)["showcases"]
    assert [card["id"] for card in cards] == ["demo", "escape"]
    assert cards[0]["key_moment"] == "At 10 s something happened."
    assert all("comparison" not in card and "sha256" not in card for card in cards)
    status, body = _request(server, "/api/status")
    assert json.loads(body)["showcases_available"] is True


def test_a_showcase_recording_is_served_only_when_its_hash_matches(
    server: DemoServer, showcase_root: Path
) -> None:
    status, body = _request(server, "/api/showcase/demo")
    assert status == 200 and json.loads(body)["note"] == "stand-in recording"
    for path in ("/api/showcase/escape", "/api/showcase/unknown", "/api/showcase/..%2Fbad"):
        assert _request(server, path)[0] == 404
    (showcase_root / "demo" / "run" / "comparison.json").write_bytes(b'{"runs": [1]}')
    assert _request(server, "/api/showcase/demo")[0] == 404


def test_missing_or_broken_manifests_mean_no_showcases(tmp_path: Path) -> None:
    for content in (None, "not json", '{"showcases": "x"}'):
        root = tmp_path / f"case-{content is None}-{len(content or '')}"
        root.mkdir()
        if content is not None:
            (root / "showcases.json").write_text(content, encoding="utf-8")
        for server in _serve(tmp_path / "runs", root):
            assert json.loads(_request(server, "/api/showcases")[1]) == {"showcases": []}
            assert _request(server, "/api/showcase/demo")[0] == 404


def test_status_lists_the_turn_constrained_usv_for_the_planners(server: DemoServer) -> None:
    status = json.loads(_request(server, "/api/status")[1])
    assert "usv_curvature" in status["models"]
    assert status["method_models"]["p"] == ["holonomic", "usv_curvature"]
    assert status["controller_models"]["qp"] == ["holonomic"]


@pytest.mark.parametrize("value", ['"0.1"', "0", "-1", "true"])
def test_an_invalid_mission_target_is_rejected(server: DemoServer, value: str) -> None:
    status, body = _request(server, "/api/run", f'{{"target_mean_variance": {value}}}')
    assert status == 400 and "target_mean_variance" in json.loads(body)["error"]
    assert not server.output_root.exists()


def test_a_usv_run_with_a_target_records_both(server: DemoServer) -> None:
    request = {
        "scenario": "nominal",
        "robots": 2,
        "duration_s": 10,
        "model": "usv_curvature",
        "methods": ["dp", "p"],
        "target_mean_variance": 0.3,
    }
    status, body = _request(server, "/api/run", json.dumps(request))
    assert status == 200
    comparison = json.loads(body)
    assert comparison["config"]["model"] == "usv_curvature"
    assert comparison["config"]["target_mean_variance"] == 0.3
    managed = next(run for run in comparison["runs"] if run["method"] == "p")
    assert managed["plans"][0]["target_risk"]["target_mean_variance"] == 0.3


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_recorded_decision_code_has_plain_language() -> None:
    source = Path(policy.__file__).read_text(encoding="utf-8")
    reasons = set(re.findall(r'reason = "([a-z_]+)"', source))
    assert len(reasons) == 7
    dashboard = (ROOT / "src" / "attain_sampling" / "demo" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    for code in (*policy.TRIGGERS, *reasons):
        assert f"  {code}: " in dashboard, code
    showcases = _load_script("make_showcases")
    assert set(showcases.TRIGGERS) == set(policy.TRIGGERS)
    assert set(showcases.REASONS) == reasons
    plan = {
        "generated_at_s": 12.5,
        "decision": {
            "action": "retained",
            "trigger": "missed_measurement",
            "reason": "retained_plan_within_switch_margin_of_the_best_candidate",
        },
    }
    assert showcases.decision_sentence(plan) == (
        "At 12.5 s, a lost measurement led P to check; it kept its plan because no candidate "
        "beats the plan in force by more than the switch margin."
    )
