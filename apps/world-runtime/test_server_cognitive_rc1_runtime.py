from __future__ import annotations

from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime


def _frame_ticks(runtime, frame_ids):
    wanted = set(frame_ids)
    return tuple(
        sorted(
            int(event["tick_id"])
            for event in (runtime.world.get("events") or {}).values()
            if isinstance(event, dict)
            and event.get("type") == "multimodal_sensor_frame_sampled"
            and event.get("frame_id") in wanted
        )
    )


def test_server_cognitive_rc1_runs_without_llm_tiktok_or_renderer():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=701)

    first = runtime.step()
    assert first["profile"] == "server-cognitive-rc1"
    assert first["cycles"] == 1
    assert first["nov"]["mode"] in ("curiosity", "need")
    assert first["nov"]["action"] in ("probe", "walk", "rest")
    assert len(first["reality"]["frame_ids"]) == 3
    assert first["world"]["events"] > 0
    assert first["cognition"]["intervention_memory_episodes"] >= 1


def test_server_cognitive_rc1_sensor_frames_are_distinct_world_ticks():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=702)

    first = runtime.step()
    ticks = _frame_ticks(runtime, first["reality"]["frame_ids"])

    assert len(ticks) == 3
    assert len(set(ticks)) == 3
    assert ticks == tuple(sorted(ticks))


def test_server_cognitive_rc1_reality_slices_reach_structural_pipeline():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=703)

    samples = runtime.run(6)
    status = runtime.status()

    assert len(samples) == 6
    assert status["cycles"] == 6
    assert status["reality"]["ingested_total"] >= 4
    assert status["cognition"]["pairwise_patterns"] > 0
    assert status["cognition"]["pairwise_links"] > 0
    assert status["event_time"]["max_event_time"] is not None
    assert status["event_time"]["watermark"] is not None
    assert len(status["event_time"]["pending_slice_ids"]) <= 2


def test_server_cognitive_rc1_water_evolves_while_nov_learns():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=704)
    before = runtime.status()["environment"]
    samples = runtime.run(6)
    after = runtime.status()["environment"]

    assert len(samples) == 6
    assert runtime.cycles == 6
    assert after != before
    assert runtime.status()["cognition"]["intervention_memory_episodes"] >= 2


def test_server_cognitive_rc1_inspect_exposes_structural_observability():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=705)
    runtime.run(8)

    inspect = runtime.inspect()

    assert inspect["status"]["cognition"]["pairwise_links"] > 0
    assert "higher_order_candidates" in inspect
    assert "current_resolutions" in inspect
    assert "historical_context_observations" in inspect
    assert "admission_history" in inspect


def test_server_cognitive_rc1_checkpoint_restores_exact_next_step(tmp_path):
    checkpoint = tmp_path / "server-cognitive-rc1.state"
    continuous = ServerCognitiveRC1Runtime.create(episode_id=706)
    continuous.run(7)
    continuous.save_checkpoint(checkpoint)

    restored = ServerCognitiveRC1Runtime.load_checkpoint(checkpoint)

    assert restored.status() == continuous.status()
    assert restored.inspect() == continuous.inspect()

    expected_next = continuous.step()
    restored_next = restored.step()

    assert restored_next == expected_next
    assert restored.status() == continuous.status()
    assert restored.inspect() == continuous.inspect()


def test_server_cognitive_rc1_checkpoint_is_atomic_and_rewritable(tmp_path):
    checkpoint = tmp_path / "server-cognitive-rc1.state"
    runtime = ServerCognitiveRC1Runtime.create(episode_id=707)

    runtime.run(2)
    runtime.save_checkpoint(checkpoint)
    first_size = checkpoint.stat().st_size
    assert first_size > 0
    assert not checkpoint.with_name(checkpoint.name + ".tmp").exists()

    runtime.run(2)
    runtime.save_checkpoint(checkpoint)
    assert checkpoint.stat().st_size > 0
    assert not checkpoint.with_name(checkpoint.name + ".tmp").exists()

    restored = ServerCognitiveRC1Runtime.load_checkpoint(checkpoint)
    assert restored.cycles == 4


def test_server_cognitive_rc1_is_deterministic():
    a = ServerCognitiveRC1Runtime.create(episode_id=708)
    b = ServerCognitiveRC1Runtime.create(episode_id=708)

    assert a.run(8) == b.run(8)
    assert a.status() == b.status()
    assert a.inspect() == b.inspect()
