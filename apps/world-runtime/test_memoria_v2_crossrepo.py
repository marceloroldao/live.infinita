from scenario_nova_r1_r2 import build_scenario_frames

from memoria_resolutiva.live_infinita_adapter_v2 import make_live_request
from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2


def _request(payload):
    return make_live_request(
        frame_id=payload["frame_id"],
        state_addresses=payload["state_addresses"],
        intervention_id=payload["intervention_id"],
        intervention_address=payload["intervention_address"],
        candidates=payload["candidates"],
        provenance=payload["provenance"],
    )


def test_live_frames_are_consumed_directly_by_memoria_v2():
    frames = build_scenario_frames()
    assert len(frames) == 5
    for payload in frames:
        request = _request(payload)
        assert request.state.frame_id == payload["frame_id"]
        assert request.intervention.intervention_id == payload["intervention_id"]
        assert len(request.candidates) == 1


def test_r1_r2_r1_preserves_independent_situated_regimes():
    frames = build_scenario_frames()
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    steps = []
    for payload in frames:
        request = _request(payload)
        actual_candidate_id = request.candidates[0].candidate_id
        steps.append(gym.step(request, actual_candidate_id=actual_candidate_id))

    r1_first, r1_second, r2_first, r2_second, r1_return = steps

    assert r1_first.prior_regime.active is None
    assert r1_second.current_regime.active is not None
    r1_active = r1_second.current_regime.active

    assert r2_first.prior_regime.active is None
    assert r2_second.current_regime.active is not None
    r2_active = r2_second.current_regime.active

    assert r1_active != r2_active

    # Returning to R1 must retrieve the already established local continuity before
    # learning the current observation again.
    assert r1_return.prior_regime.active == r1_active
    assert r1_return.current_regime.active == r1_active
    assert r1_return.context_key == r1_second.context_key
    assert r1_return.context_key != r2_second.context_key


def test_crossrepo_run_is_deterministic():
    def run_once():
        gym = SituatedLiveCognitiveGymV2(
            min_independent_episodes=2,
            min_contiguous_support=2,
        )
        result = []
        for payload in build_scenario_frames():
            request = _request(payload)
            step = gym.step(request, actual_candidate_id=request.candidates[0].candidate_id)
            result.append(
                (
                    step.context_key,
                    step.prior_regime,
                    step.current_regime,
                    step.error,
                    step.attention,
                )
            )
        return tuple(result)

    assert run_once() == run_once()
