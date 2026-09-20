"""Behavior at the approved internal mission read/advance/finish interface."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from attain_sampling.gp.sogp import SparseOnlineGP
from attain_sampling.sim import mapping
from attain_sampling.sim.mapping import MappingConfig, _MissionExecution


def config(**changes):
    return MappingConfig(
        **{
            "robot_count": 2,
            "duration_s": 3.0,
            "dt": 0.5,
            "sample_period_s": 2.0,
            "grid_shape": (6, 4),
            "dp_grid_shape": (4, 3),
            **changes,
        }
    )


def test_constructor_closes_initial_receipt_and_plan_before_reading():
    mission = _MissionExecution(config(), "dp")

    initial = mission.read()

    assert initial.status == "running"
    assert (initial.tick, initial.time_s) == (0, 0.0)
    assert initial.samples_attempted == initial.samples_received == initial.samples_assimilated == 2
    assert initial.active_plan_id is not None
    assert len(initial.positions) == len(initial.headings) == 2
    assert mission.read() == initial


def test_advance_closes_one_physical_tick_and_the_arriving_sampling_epoch():
    mission = _MissionExecution(config(), "dp")
    initial = mission.read()

    for tick, time_s in [(1, 0.5), (2, 1.0), (3, 1.5)]:
        interior = mission.advance()
        assert (interior.tick, interior.time_s) == (tick, time_s)
        assert interior.samples_attempted == interior.samples_received == 2
        assert interior.active_plan_id == initial.active_plan_id

    arrival = mission.advance()

    assert (arrival.tick, arrival.time_s) == (4, 2.0)
    assert arrival.samples_attempted == arrival.samples_received == arrival.samples_assimilated == 4
    assert arrival.active_plan_id != initial.active_plan_id
    assert arrival.status == "running"
    assert mission.read() == arrival


def test_finish_closes_the_deadline_once_and_returns_independent_evidence():
    mission = _MissionExecution(config(), "dp")
    mission.advance()

    result = mission.finish()

    assert result["status"] == "completed"
    assert [row["time_s"] for row in result["motion"]] == [0, 0.5, 1, 1.5, 2, 2.5, 3]
    assert [row["time_s"] for row in result["samples"]] == [0, 0, 2, 2]
    assert [row["time_s"] for row in result["frames"]] == [0, 2, 3]
    assert [plan["generated_at_s"] for plan in result["plans"]] == [0, 2]
    terminal = mission.read()
    assert (terminal.status, terminal.tick, terminal.time_s) == ("completed", 6, 3.0)
    expected = deepcopy(result)
    result["motion"][0]["positions"][0][0] = -1000
    result["frames"][-1]["mean"][0][0] = -1000
    result["plans"].clear()

    assert mission.advance() == terminal
    assert mission.advance() == terminal
    assert mission.finish() == expected


def test_fractional_ticks_keep_the_original_sample_clock_and_incoming_plan():
    mission = _MissionExecution(config(dt=0.7, sample_period_s=2.1, duration_s=7.0), "dp")
    views = [mission.read()]
    while views[-1].status == "running":
        views.append(mission.advance())
    result = mission.finish()

    assert [view.tick for view in views] == list(range(11))
    assert [view.time_s for view in views] == pytest.approx(
        [0, 0.7, 1.4, 2.1, 2.8, 3.5, 4.2, 4.9, 5.6, 6.3, 7]
    )
    assert [view.samples_attempted for view in views] == [2, 2, 2, 4, 4, 4, 6, 6, 6, 8, 8]
    assert [row["time_s"] for row in result["samples"]] == pytest.approx(
        [0, 0, 2.1, 2.1, 4.2, 4.2, 6.3, 6.3]
    )
    for arrival_index, frame in zip([3, 6, 9], result["frames"][1:-1], strict=True):
        incoming = views[arrival_index - 1].active_plan_id
        outgoing = views[arrival_index].active_plan_id
        assert outgoing != incoming
        assert frame["plan_id"] == outgoing
        assert frame["forecast_plan_id"] == incoming
        assert result["motion"][arrival_index]["plan_id"] == incoming
        arrivals = [s for s in result["samples"] if s["time_s"] == frame["time_s"]]
        assert len(arrivals) == 2
        assert all(sample["plan_id"] == incoming for sample in arrivals)
    assert result["frames"][-1]["forecast_plan_id"] is None
    assert result["frames"][-1]["time_s"] == 7.0


def test_views_are_immutable_and_earlier_observations_survive_advancement():
    mission = _MissionExecution(config(), "sweep")
    initial = mission.read()
    initial_positions = initial.positions

    with pytest.raises(FrozenInstanceError):
        initial.tick = 99
    with pytest.raises(TypeError):
        initial.positions[0][0] = -1000
    with pytest.raises(TypeError):
        initial.headings[0] = -1000
    next_view = mission.advance()

    assert (initial.tick, initial.time_s) == (0, 0.0)
    assert initial.positions == initial_positions
    assert next_view.tick == 1
    assert next_view.positions != initial.positions


@pytest.mark.parametrize("method,receipts", [("sweep", 0), ("greedy", 0), ("adaptive", 2)])
def test_startup_preview_failure_preserves_method_specific_receipt_order(method, receipts):
    mission = _MissionExecution(config(controller="qp", qp_max_iter=1), method)

    failed = mission.read()
    result = mission.finish()

    assert (failed.status, failed.tick, failed.time_s) == ("failed", 0, 0.0)
    assert (
        failed.samples_attempted
        == failed.samples_received
        == failed.samples_assimilated
        == receipts
    )
    assert result["failure"]["phase"] == "preview"
    assert len(result["frames"]) == len(result["motion"]) == 1
    assert len(result["samples"]) == receipts
    assert mission.advance() == failed
    assert mission.finish() == result


@pytest.mark.parametrize("failure_time,tick,receipts", [(0.0, 0, 2), (2.0, 4, 4)])
def test_planning_failure_exposes_the_reached_tick_after_real_receipt(
    monkeypatch, failure_time, tick, receipts
):
    original = mapping.plan_timed_dp

    def fail_at_epoch(*args, **kwargs):
        if kwargs["now_s"] == failure_time:
            raise FloatingPointError("injected covariance failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(mapping, "plan_timed_dp", fail_at_epoch)
    mission = _MissionExecution(config(), "dp")
    view = mission.read()
    while view.status == "running":
        view = mission.advance()
    result = mission.finish()

    assert (view.status, view.tick, view.time_s) == ("failed", tick, failure_time)
    assert view.samples_attempted == view.samples_received == view.samples_assimilated == receipts
    assert result["failure"]["phase"] == "planning"
    assert result["failure"]["last_executed_time_s"] == failure_time
    assert result["frames"][-1]["time_s"] == failure_time
    assert len(result["plans"]) == (0 if tick == 0 else 1)
    assert result["frames"][-1]["plan_id"] == view.active_plan_id
    assert mission.advance() == view
    assert mission.finish() == result


def test_rejected_control_leaves_the_last_accepted_tick_without_extra_samples(monkeypatch):
    original = mapping._advance

    def reject_thirteenth_step(positions, headings, targets, config, tick, **kwargs):
        if kwargs.get("phase") == "execution" and tick == 13:
            config = replace(config, qp_max_iter=1)
        return original(positions, headings, targets, config, tick, **kwargs)

    monkeypatch.setattr(mapping, "_advance", reject_thirteenth_step)
    mission = _MissionExecution(
        config(duration_s=10.0, sample_period_s=5.0, controller="qp"), "adaptive"
    )
    for _ in range(12):
        accepted = mission.advance()
    assert (accepted.status, accepted.tick, accepted.time_s) == ("running", 12, 6.0)

    failed = mission.advance()
    result = mission.finish()

    assert (failed.status, failed.tick, failed.time_s) == ("failed", 12, 6.0)
    assert failed.positions == accepted.positions
    assert failed.headings == accepted.headings
    assert failed.samples_received == failed.samples_assimilated == 4
    assert result["failure"]["tick"] == 13
    assert result["failure"]["phase"] == "execution"
    assert result["controls"][-1]["applied_velocity"] is None
    assert [row["time_s"] for row in result["frames"]] == [0, 5, 6]
    assert [row["time_s"] for row in result["samples"]] == [0, 0, 5, 5]
    assert mission.advance() == failed
    assert mission.finish() == result


def test_rejected_gp_batch_keeps_receipts_separate_from_assimilation(monkeypatch):
    original = SparseOnlineGP.update

    def reject_second_batch(self, points, values):
        if self.observation_count >= 2:
            raise FloatingPointError("injected rejected GP batch")
        return original(self, points, values)

    monkeypatch.setattr(SparseOnlineGP, "update", reject_second_batch)
    mission = _MissionExecution(config(gp_backend="sogp"), "dp")
    for _ in range(4):
        view = mission.advance()
    result = mission.finish()

    assert (view.status, view.tick, view.time_s) == ("failed", 4, 2.0)
    assert view.samples_attempted == view.samples_received == 4
    assert view.samples_assimilated == 2
    assert result["failure"]["phase"] == "gp_update"
    assert [sample["assimilated"] for sample in result["samples"]] == [True, True, False, False]
    assert len(result["plans"]) == 1
    assert mission.advance() == view
    assert mission.finish() == result


def test_interior_p_replacement_is_visible_after_arrival_and_before_next_motion():
    mission = _MissionExecution(
        config(
            duration_s=10.0,
            sample_period_s=5.0,
            controller="qp",
            drift_strength=0.35,
            dp_horizon_steps=2,
            p_deviation_trigger_m=0.05,
            p_intervention_trigger_mps=1000.0,
            p_retain_plan=False,
        ),
        "p",
    )
    views = [mission.read()]
    while views[-1].status == "running":
        views.append(mission.advance())
    result = mission.finish()
    interior = [event for event in result["plan_events"] if event["tick"] % 10 != 0]

    assert interior
    assert any(event["action"] == "replaced" for event in interior)
    for event in interior:
        tick = event["tick"]
        assert result["motion"][tick]["plan_id"] == views[tick - 1].active_plan_id
        assert views[tick].active_plan_id == event["plan_id"]
        assert views[tick].active_plan_id != views[tick - 1].active_plan_id
        assert result["motion"][tick + 1]["plan_id"] == event["plan_id"]
        assert views[tick].samples_attempted == views[tick - 1].samples_attempted


def test_caller_pause_counts_in_running_wall_time_but_terminal_time_is_frozen(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(mapping.time, "perf_counter", lambda: clock[0])
    mission = _MissionExecution(config(), "dp")
    initial = mission.read()
    clock[0] += 20.0

    assert mission.read() == initial
    assert mission.advance().time_s == 0.5
    clock[0] += 15.0
    result = mission.finish()
    assert result["summary"]["runtime_s"] == 35.0
    assert result["summary"]["completion_time_s"] == 3.0
    clock[0] += 500.0
    assert mission.advance().time_s == 3.0
    assert mission.finish() == result


@pytest.mark.parametrize("advanced_ticks", [0, 1, 3, 4, 6])
def test_finishing_at_different_observation_points_preserves_the_whole_run(
    monkeypatch, advanced_ticks
):
    # A fixed external clock removes only measured runtime differences; every
    # returned field, including the physical clock and plan provenance, is equal.
    monkeypatch.setattr(mapping.time, "perf_counter", lambda: 1000.0)
    expected = mapping.run_mapping(config(), "dp")
    mission = _MissionExecution(config(), "dp")
    for _ in range(advanced_ticks):
        mission.advance()

    assert mission.finish() == expected


@pytest.mark.parametrize("method", ["sweep", "greedy", "adaptive", "dp", "p"])
def test_deadline_before_next_measurement_finishes_without_a_fabricated_receipt(method):
    mission = _MissionExecution(config(duration_s=1.0), method)
    assert mission.advance().status == "running"
    terminal = mission.advance()
    result = mission.finish()

    assert (terminal.status, terminal.tick, terminal.time_s) == ("completed", 2, 1.0)
    assert (
        terminal.samples_attempted == terminal.samples_received == terminal.samples_assimilated == 2
    )
    assert [row["time_s"] for row in result["samples"]] == [0, 0]
    assert [row["time_s"] for row in result["frames"]] == [0, 1]
    assert all(plan["generated_at_s"] == 0 for plan in result["plans"])


def test_lost_measurements_increment_attempts_without_receipt_or_assimilation():
    mission = _MissionExecution(config(dropout_prob=1.0), "dp")
    initial = mission.read()
    assert (initial.samples_attempted, initial.samples_received, initial.samples_assimilated) == (
        2,
        0,
        0,
    )
    for _ in range(4):
        arrival = mission.advance()
    assert (arrival.samples_attempted, arrival.samples_received, arrival.samples_assimilated) == (
        4,
        0,
        0,
    )


@pytest.mark.parametrize("phase", ["startup", "execution"])
def test_unrelated_exceptions_propagate_instead_of_becoming_failed_artifacts(monkeypatch, phase):
    if phase == "startup":

        def broken_planner(*args, **kwargs):
            raise RuntimeError("unexpected implementation error")

        monkeypatch.setattr(mapping, "plan_timed_dp", broken_planner)
        with pytest.raises(RuntimeError, match="unexpected implementation error"):
            _MissionExecution(config(), "dp")
    else:
        mission = _MissionExecution(config(), "dp")

        def broken_execution(*args, **kwargs):
            raise RuntimeError("unexpected implementation error")

        monkeypatch.setattr(mapping, "_advance", broken_execution)
        with pytest.raises(RuntimeError, match="unexpected implementation error"):
            mission.advance()
        assert (mission.read().status, mission.read().tick) == ("running", 0)
