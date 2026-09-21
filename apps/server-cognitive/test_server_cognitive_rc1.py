from __future__ import annotations

from bootstrap_paths import configure_runtime_paths

configure_runtime_paths()

from engine import ServerCognitiveEngine


def _signature(engine: ServerCognitiveEngine):
    snapshot = engine.snapshot()
    return {
        "cycle_id": snapshot["cycle_id"],
        "simulation_time": snapshot["simulation_time"],
        "world": snapshot["world"],
        "nov": snapshot["nov"],
        "environment": snapshot["environment"],
        "bit_analyze": snapshot["bit_analyze"],
        "memoria_v2": snapshot["memoria_v2"],
        "event_time": snapshot["event_time"],
        "activity": engine.activity_snapshot(100),
    }


def test_server_cognitive_rc1_initial_snapshot_is_observable_without_external_services():
    engine = ServerCognitiveEngine()
    snapshot = engine.snapshot()

    assert snapshot["profile"] == "server-cognitive-rc1"
    assert snapshot["status"] == "ready"
    assert snapshot["cycle_id"] == 0
    assert snapshot["world"]["world_id"].startswith("server-cognitive-rc1-")
    assert snapshot["nov"]["region_id"]
    assert snapshot["bit_analyze"]["pairwise_links"] == 0
    assert snapshot["memoria_v2"]["temporal_observations"] == 0
    assert snapshot["event_time"]["late_rejections"] == 0


def test_server_cognitive_rc1_step_advances_world_and_commits_nov_action():
    engine = ServerCognitiveEngine()
    before = engine.snapshot()

    result = engine.step()
    after = engine.snapshot()

    assert result.cycle_id == 1
    assert after["cycle_id"] == 1
    assert after["world"]["tick"] > before["world"]["tick"]
    assert after["world"]["version"] > before["world"]["version"]
    assert result.nov_mode in {"curiosity", "need"}
    assert result.nov_action
    assert result.nov_consequence
    assert after["nov"]["last_decision"]["action"] == result.nov_action
    assert after["world"]["events"] > before["world"]["events"]
    assert after["world"]["deltas"] > before["world"]["deltas"]
    assert len(engine.activity_snapshot()) == 1


def test_server_cognitive_rc1_multiple_cycles_feed_bit_analyze_and_event_time():
    engine = ServerCognitiveEngine()
    results = engine.run_steps(6)
    snapshot = engine.snapshot()

    assert len(results) == 6
    assert snapshot["cycle_id"] == 6
    assert snapshot["bit_analyze"]["pairwise_links"] > 0
    assert snapshot["bit_analyze"]["known_slices"] >= 4
    assert snapshot["event_time"]["max_event_time"] is not None
    assert snapshot["event_time"]["watermark"] is not None
    assert snapshot["event_time"]["late_rejections"] == 0
    assert snapshot["nov"]["causal_memory_observations"] >= 1


def test_server_cognitive_rc1_memoria_layers_remain_separate():
    engine = ServerCognitiveEngine()
    engine.run_steps(8)
    debug = engine.debug_memory()

    assert set(debug) == {
        "temporal",
        "context",
        "admission",
        "causal",
        "regimes",
    }
    assert isinstance(debug["temporal"], list)
    assert isinstance(debug["context"], list)
    assert isinstance(debug["admission"], list)
    assert isinstance(debug["causal"], list)


def test_server_cognitive_rc1_flush_emits_pending_event_time_slice_without_new_world_action():
    engine = ServerCognitiveEngine()
    engine.step()
    before = engine.snapshot()
    pending_before = tuple(before["event_time"]["pending_slice_ids"])

    emitted = engine.flush_event_time()
    after = engine.snapshot()

    assert pending_before
    assert emitted == pending_before
    assert after["world"] == before["world"]
    assert after["event_time"]["pending_slice_ids"] == ()


def test_server_cognitive_rc1_run_limit_is_bounded():
    engine = ServerCognitiveEngine()

    for invalid in (0, -1, 1001):
        try:
            engine.run_steps(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid run_steps count must fail")


def test_server_cognitive_rc1_is_deterministic_for_same_episode():
    a = ServerCognitiveEngine(episode_id=77)
    b = ServerCognitiveEngine(episode_id=77)

    a.run_steps(5)
    b.run_steps(5)

    assert _signature(a) == _signature(b)
