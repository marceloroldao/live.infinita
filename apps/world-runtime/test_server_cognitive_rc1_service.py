from __future__ import annotations

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
