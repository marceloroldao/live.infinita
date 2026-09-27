from __future__ import annotations

import math
from hashlib import sha256
from typing import Any

from npc_counterfactual_simulator import NpcCounterfactualSimulator


EPSILON = 1e-6


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    try:
        pa, pb = a["position"], b["position"]
        if not isinstance(pa, dict) or not isinstance(pb, dict):
            return None
        values = [float(pa["x"]), float(pa["y"]), float(pb["x"]), float(pb["y"])]
        if not all(math.isfinite(v) for v in values):
            return None
        return math.hypot(values[0] - values[2], values[1] - values[3])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def build_exante_forecast(
    *,
    frame: Any,
    observer: dict[str, Any],
    targets: dict[str, dict[str, Any]],
    world_version: int,
    world_sequence: int,
    environment: dict[str, Any] | None = None,
    need_levels: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Freeze a simple pre-tick direction baseline; never inspect post-tick state.

    The nearest distinct reachable target is a reference baseline, *not* a
    Memoria.ia inference or a claim that the actor has selected that action.
    """
    forecast: dict[str, Any] = {
        "forecast_schema": "cognitive_exante_direction_v1",
        "predictor_id": "nearest-target-continuity-baseline-v1",
        "selection_phase": "pre_tick",
        "horizon_ticks": 1,
        "issued_frame_id": frame.frame_id,
        "issued_world_version": int(world_version),
        "issued_world_sequence": int(world_sequence),
        "status": "abstained",
        "reason": "no_valid_target",
        "action": None,
        "candidate_id": None,
        "target_entity_id": None,
        "target_region_id": None,
        "target_position": None,
        "distance_before": None,
        "expected_direction": None,
        "forecast_id": None,
        "predicts_action": False,
        "projected_need_pressure": None,
        "need_projection_evaluable": False,
    }
    env = environment if isinstance(environment, dict) else {}
    raw_needs = need_levels if isinstance(need_levels, dict) else {}
    risk_value = env.get("danger_level")
    try:
        risk = float(risk_value)
        risk_available = not isinstance(risk_value, bool) and math.isfinite(risk) and 0.0 <= risk <= 1.0
    except (TypeError, ValueError, OverflowError):
        risk, risk_available = 0.0, False
    if risk_available and all(
        key in raw_needs and isinstance(raw_needs[key], (int, float)) and
        not isinstance(raw_needs[key], bool) and math.isfinite(raw_needs[key])
        for key in NpcCounterfactualSimulator.DEFAULT_NEED_RATES
    ):
        simulation = NpcCounterfactualSimulator(max_steps=1).simulate(
            strategy={"strategy_id": "direct", "phases": [{"kind": "estimated", "estimated_ticks": 1}]},
            context={
                "logical_tick": frame.tick_id,
                "period": env.get("period"),
                "danger_level": risk,
                "needs": raw_needs,
            },
        )
        forecast["projected_need_pressure"] = {
            "source": "existing_npc_counterfactual_simulator",
            "assumption": "one_tick_direct; observed_risk; imagined_satisfaction_disabled",
            "counterfactual_schema": simulation["counterfactual_schema"],
            "start_needs": simulation["start_needs"],
            "end_needs": simulation["end_needs"],
            "projected_need_cost": simulation["projected_need_cost"],
            "mutates_world": False,
        }
    candidates_by_proposal = {item.proposal_id: item for item in frame.candidate_outcomes}
    ranked: list[tuple[float, str, str, Any, Any]] = []
    # Different actions can address the same entity: compare distinct targets,
    # not duplicate proposals masquerading as independent candidates.
    seen: set[str] = set()
    for intervention in frame.available_interventions:
        target_id = str(intervention.target_entity_id or "")
        if target_id in seen:
            continue
        seen.add(target_id)
        target = targets.get(target_id)
        if not isinstance(target, dict):
            continue
        distance = _distance(observer, target)
        if distance is None:
            continue
        candidate = candidates_by_proposal.get(intervention.proposal_id)
        ranked.append((distance, target_id, intervention.action, intervention, candidate))
    if not ranked:
        return forecast
    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    best = ranked[0]
    if len(ranked) > 1 and abs(ranked[1][0] - best[0]) <= EPSILON:
        forecast["reason"] = "distance_tie"
        return forecast
    if best[0] <= EPSILON:
        forecast["reason"] = "already_at_target"
        return forecast

    target = targets[best[1]]
    position = target["position"]
    digest = sha256(
        f"{frame.frame_id}|{world_sequence}|{best[1]}|{best[0]:.12f}".encode("utf-8")
    ).hexdigest()[:24]
    forecast.update({
        "status": "issued",
        "reason": None,
        "action": None,
        "candidate_id": None,
        "target_entity_id": best[1],
        "target_region_id": target.get("region_id"),
        "target_position": {"x": float(position["x"]), "y": float(position["y"])},
        "distance_before": best[0],
        "expected_direction": "toward_frozen_target",
        "forecast_id": f"exante_{digest}",
    })
    return forecast


def evaluate_exante_forecast(
    forecast: dict[str, Any],
    *,
    observer_after: dict[str, Any],
    target_after: dict[str, Any] | None,
    observer_before: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the frozen claim against the real tick, without moving the goalposts."""
    result: dict[str, Any] = {
        "evaluation_schema": "cognitive_exante_direction_evaluation_v1",
        "forecast_id": forecast.get("forecast_id"),
        "status": "not_evaluable",
        "reason": None,
        "observed_progress": None,
        "observer_movement_distance": _distance(observer_before, observer_after),
        "target_stable": None,
        "hit": None,
    }
    if forecast.get("status") != "issued":
        result.update(status="abstained", reason=forecast.get("reason") or "no_forecast")
        return result

    before_target = {
        "position": forecast.get("target_position"),
        "region_id": forecast.get("target_region_id"),
    }
    if not isinstance(target_after, dict):
        result["reason"] = "target_missing"
        return result
    target_shift = _distance(before_target, target_after)
    stable = (
        target_shift is not None
        and target_shift <= EPSILON
        and str(target_after.get("region_id") or "") == str(forecast.get("target_region_id") or "")
    )
    result["target_stable"] = stable
    if not stable:
        result["reason"] = "target_changed"
        return result
    moved = result["observer_movement_distance"]
    if moved is None:
        result["reason"] = "observer_position_missing"
        return result
    if moved <= EPSILON:
        result["reason"] = "observer_stationary"
        return result
    after_distance = _distance(observer_after, before_target)
    initial_distance = forecast.get("distance_before")
    if after_distance is None or not isinstance(initial_distance, (int, float)):
        result["reason"] = "distance_unavailable"
        return result

    progress = float(initial_distance) - after_distance
    if abs(progress) <= EPSILON:
        result.update(reason="lateral_or_indeterminate_movement", observed_progress=progress)
        return result
    hit = progress > EPSILON
    result.update(
        status="hit" if hit else "miss",
        reason=None,
        observed_progress=progress,
        hit=hit,
    )
    return result
