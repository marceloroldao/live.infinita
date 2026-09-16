from scenario_nova_r1_r2 import build_scenario_frames


def _consequence(payload):
    candidates = payload["candidates"]
    assert len(candidates) == 1
    return tuple(candidates[0][1])


def test_scenario_has_expected_r1_r2_r1_sequence():
    frames = build_scenario_frames()
    assert len(frames) == 5
    assert "live:region:r1" in frames[0]["state_addresses"]
    assert "live:region:r1" in frames[1]["state_addresses"]
    assert "live:region:r2" in frames[2]["state_addresses"]
    assert "live:region:r2" in frames[3]["state_addresses"]
    assert "live:region:r1" in frames[4]["state_addresses"]


def test_r1_and_r2_consequences_are_structurally_distinct():
    frames = build_scenario_frames()
    r1 = _consequence(frames[0])
    r2 = _consequence(frames[2])
    assert r1 != r2
    assert "live:entity:outcome_x" in r1
    assert "live:entity:outcome_y" in r2


def test_return_to_r1_reuses_same_structural_consequence():
    frames = build_scenario_frames()
    assert _consequence(frames[0]) == _consequence(frames[1])
    assert _consequence(frames[0]) == _consequence(frames[4])


def test_payloads_are_deterministic():
    assert build_scenario_frames() == build_scenario_frames()
