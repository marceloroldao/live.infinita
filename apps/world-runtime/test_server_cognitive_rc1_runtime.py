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
