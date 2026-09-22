from __future__ import annotations

import time

from server_cognitive_rc1_service import RuntimeController


def test_server_cognitive_rc1_controller_exposes_status_step_and_run():
    controller = RuntimeController(episode_id=801)

    initial = controller.status()
    assert initial["cycles"] == 0

    one = controller.step()
    assert one["cycles"] == 1

    batch = controller.run(3)
    assert batch["cycles_requested"] == 3
    assert len(batch["samples"]) == 3
    assert batch["status"]["cycles"] == 4



def test_server_cognitive_rc1_controller_exposes_observability_views():
    controller = RuntimeController(episode_id=802)
    controller.run(4)

    cognition = controller.cognition()
    world = controller.world_status()
    metrics = controller.metrics()

    assert cognition["cognition"]["causal"]["memory_episodes"] >= 1
    assert "structural" in cognition["cognition"]
    assert world["world"]["tick"] > 0
    assert metrics["cycles"] == 4
    assert metrics["reality_slices_offered"] == 4
    assert metrics["reality_slices_ingested"] >= 2
    assert metrics["late_rejection_count"] == 0
    controller.close()


def test_server_cognitive_rc1_controller_background_loop_starts_and_stops():
    controller = RuntimeController(episode_id=803)
    initial_cycles = controller.status()["cycles"]

    started = controller.start(interval_seconds=0.01)
    assert started["service"]["running"] is True

    deadline = time.monotonic() + 2.0
    while controller.status()["cycles"] <= initial_cycles:
        if time.monotonic() >= deadline:
            raise AssertionError("background loop did not advance")
        time.sleep(0.01)

    stopped = controller.stop()
    stopped_cycles = stopped["cycles"]
    assert stopped["service"]["running"] is False

    time.sleep(0.03)
    assert controller.status()["cycles"] == stopped_cycles


def test_server_cognitive_rc1_controller_rejects_invalid_background_interval():
    controller = RuntimeController(episode_id=804)

    try:
        controller.start(interval_seconds=0.001)
    except ValueError as exc:
        assert "between 0.01 and 60" in str(exc)
    else:
        raise AssertionError("invalid interval should be rejected")
    controller.close()
