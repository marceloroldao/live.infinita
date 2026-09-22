from __future__ import annotations

from server_cognitive_rc1_service import RuntimeController


def test_server_cognitive_rc1_controller_exposes_status_step_run_and_inspect():
    controller = RuntimeController(episode_id=801)

    initial = controller.status()
    assert initial["cycles"] == 0
    assert initial["service"]["auto_running"] is False

    one = controller.step()
    assert one["cycles"] == 1

    batch = controller.run(3)
    assert batch["cycles_requested"] == 3
    assert len(batch["samples"]) == 3
    assert batch["status"]["cycles"] == 4

    inspect = controller.inspect()
    assert inspect["status"]["cycles"] == 4
    assert "current_resolutions" in inspect


def test_server_cognitive_rc1_controller_checkpoints_and_restores(tmp_path):
    state_path = tmp_path / "rc1.state"
    first = RuntimeController(
        episode_id=802,
        state_path=str(state_path),
    )
    first.run(5)
    before = first.inspect()

    assert state_path.exists()

    restored = RuntimeController(
        episode_id=999,
        state_path=str(state_path),
    )
    after = restored.inspect()

    assert after["status"] == before["status"]
    assert after["current_resolutions"] == before["current_resolutions"]
    assert after["historical_context_observations"] == before[
        "historical_context_observations"
    ]


def test_server_cognitive_rc1_manual_checkpoint_requires_configured_path():
    controller = RuntimeController(episode_id=803)

    try:
        controller.checkpoint()
    except ValueError as exc:
        assert "checkpoint path" in str(exc)
    else:
        raise AssertionError("checkpoint without state path must fail")


def test_server_cognitive_rc1_auto_loop_can_start_and_stop_without_extra_api():
    controller = RuntimeController(episode_id=804)

    started = controller.start_auto(10.0)
    assert started["auto_running"] is True
    assert started["auto_interval"] == 10.0

    stopped = controller.stop_auto()
    assert stopped["auto_running"] is False


def test_server_cognitive_rc1_run_rejects_unbounded_batch():
    controller = RuntimeController(episode_id=805)

    for cycles in (0, 1001):
        try:
            controller.run(cycles)
        except ValueError as exc:
            assert "between 1 and 1000" in str(exc)
        else:
            raise AssertionError("invalid cycle batch must be rejected")
