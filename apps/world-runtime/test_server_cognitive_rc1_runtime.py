from __future__ import annotations

from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime


def test_server_cognitive_rc1_runs_without_llm_tiktok_or_renderer():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=701)

    first = runtime.step()
    assert first["profile"] == "server-cognitive-rc1"
    assert first["cycles"] == 1
    assert first["nov"]["mode"] in ("curiosity", "need")
    assert first["nov"]["action"] in ("probe", "walk", "rest")
    assert first["sensors"]["frame_ids"]
    assert first["world"]["events"] > 0
    assert first["cognition"]["memory_episodes"] >= 1


def test_server_cognitive_rc1_water_evolves_while_nov_learns():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=702)
    before = runtime.status()["environment"]
    samples = runtime.run(6)
    after = runtime.status()["environment"]

    assert len(samples) == 6
    assert runtime.cycles == 6
    assert after != before
    assert runtime.status()["cognition"]["memory_episodes"] >= 2


def test_server_cognitive_rc1_is_deterministic():
    a = ServerCognitiveRC1Runtime.create(episode_id=703)
    b = ServerCognitiveRC1Runtime.create(episode_id=703)

    assert a.run(8) == b.run(8)
    assert a.status() == b.status()



def test_server_cognitive_rc1_structural_pipeline_is_live():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=704)
    runtime.run(6)
    status = runtime.status()

    assert status["event_time"]["slices_offered"] == 6
    assert status["event_time"]["slices_ingested"] >= 4
    assert status["event_time"]["watermark"] is not None
    assert status["event_time"]["max_event_time"] is not None
    assert (
        status["event_time"]["max_event_time"]
        >= status["event_time"]["watermark"]
    )
    assert status["event_time"]["late_rejection_count"] == 0
    assert status["cognition"]["structural"]["pairwise_links"] > 0
    assert status["cognition"]["structural"]["higher_order_links"] >= 0
    assert status["persistence"] == {
        "mode": "memory-only",
        "restart_safe": False,
    }


def test_server_cognitive_rc1_frames_advance_world_time_between_samples():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=705)
    before_tick = runtime.status()["world"]["tick"]
    status = runtime.step()

    assert len(status["sensors"]["frame_ids"]) == 3
    assert status["world"]["tick"] > before_tick + 3
    assert status["simulation_time"] == 1.0
    assert status["event_time"]["slices_offered"] == 1


def test_server_cognitive_rc1_status_separates_causal_and_structural_cognition():
    runtime = ServerCognitiveRC1Runtime.create(episode_id=706)
    runtime.run(5)
    cognition = runtime.status()["cognition"]

    assert set(cognition) == {"causal", "structural"}
    assert cognition["causal"]["memory_episodes"] >= 1
    assert set(cognition["structural"]["resolution_counts"]) >= {
        "resolved",
        "ambiguous",
        "unsupported",
    }
