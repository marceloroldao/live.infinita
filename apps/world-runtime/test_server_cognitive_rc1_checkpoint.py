from __future__ import annotations

import json
from pathlib import Path

from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime
from server_cognitive_rc1_service import RuntimeController


def test_server_cognitive_rc1_checkpoint_roundtrip_preserves_runtime_state(tmp_path):
    path = tmp_path / "checkpoint.json"
    original = ServerCognitiveRC1Runtime.create(episode_id=901)
    original.run(8)

    original.save_checkpoint(str(path))
    restored = ServerCognitiveRC1Runtime.load_checkpoint(str(path))

    assert path.is_file()
    assert restored.cycles == original.cycles
    assert restored.simulation_time == original.simulation_time
    assert restored.world == original.world
    assert restored.needs == original.needs
    assert restored.gym.memory.snapshot() == original.gym.memory.snapshot()
    assert restored.gym.regimes == original.gym.regimes
    assert restored.context_memory.snapshot() == original.context_memory.snapshot()
    assert restored.admission_memory.snapshot() == original.admission_memory.snapshot()
    assert restored.provenance_by_slice == original.provenance_by_slice
    assert restored.reorder.watermark == original.reorder.watermark
    assert restored.reorder.max_event_time == original.reorder.max_event_time
    assert restored.reorder.pending_slice_ids() == original.reorder.pending_slice_ids()


def test_server_cognitive_rc1_restart_continuation_matches_uninterrupted_next_cycle(tmp_path):
    path = tmp_path / "checkpoint.json"
    uninterrupted = ServerCognitiveRC1Runtime.create(episode_id=902)
    uninterrupted.run(10)
    uninterrupted.save_checkpoint(str(path))

    restarted = ServerCognitiveRC1Runtime.load_checkpoint(str(path))

    next_uninterrupted = uninterrupted.step()
    next_restarted = restarted.step()

    assert next_restarted == next_uninterrupted
    assert restarted.world == uninterrupted.world
    assert restarted.needs == uninterrupted.needs
    assert restarted.gym.memory.snapshot() == uninterrupted.gym.memory.snapshot()
    assert restarted.gym.regimes == uninterrupted.gym.regimes
    assert restarted.context_memory.snapshot() == uninterrupted.context_memory.snapshot()
    assert restarted.admission_memory.snapshot() == uninterrupted.admission_memory.snapshot()


def test_server_cognitive_rc1_controller_autosaves_and_resumes(tmp_path):
    path = tmp_path / "checkpoint.json"
    first = RuntimeController(
        episode_id=903,
        checkpoint_path=str(path),
        autosave_every=2,
        resume=True,
    )
    first.run(5)
    stopped = first.stop()

    assert path.is_file()
    assert stopped["cycles"] == 5
    assert stopped["service"]["last_checkpoint_cycle"] == 5

    second = RuntimeController(
        episode_id=999,
        checkpoint_path=str(path),
        autosave_every=2,
        resume=True,
    )
    resumed = second.status()

    assert resumed["cycles"] == 5
    assert resumed["service"]["loaded_from_checkpoint"] is True
    assert resumed["service"]["last_checkpoint_cycle"] == 5

    after = second.step()
    assert after["cycles"] == 6
    second.close()


def test_server_cognitive_rc1_manual_checkpoint_reports_saved_state(tmp_path):
    path = tmp_path / "checkpoint.json"
    controller = RuntimeController(
        episode_id=904,
        checkpoint_path=str(path),
        autosave_every=100,
    )
    controller.run(3)

    result = controller.checkpoint()

    assert result["saved"] is True
    assert Path(result["path"]) == path
    assert result["cycles"] == 3
    assert result["service"]["last_checkpoint_cycle"] == 3
    controller.close()


def test_server_cognitive_rc1_no_resume_starts_fresh_even_when_checkpoint_exists(tmp_path):
    path = tmp_path / "checkpoint.json"
    first = RuntimeController(
        episode_id=905,
        checkpoint_path=str(path),
        autosave_every=1,
    )
    first.run(3)
    first.close()

    fresh = RuntimeController(
        episode_id=906,
        checkpoint_path=str(path),
        autosave_every=1,
        resume=False,
    )
    status = fresh.status()

    assert status["cycles"] == 0
    assert status["service"]["loaded_from_checkpoint"] is False
    fresh.close()


def test_server_cognitive_rc1_checkpoint_version_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    runtime = ServerCognitiveRC1Runtime.create(episode_id=907)
    runtime.run(2)
    runtime.save_checkpoint(str(path))

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["version"] = 999
    path.write_text(json.dumps(raw), encoding="utf-8")

    try:
        ServerCognitiveRC1Runtime.load_checkpoint(str(path))
    except ValueError as exc:
        assert "unsupported checkpoint version" in str(exc)
    else:
        raise AssertionError("unsupported checkpoint version must be rejected")
