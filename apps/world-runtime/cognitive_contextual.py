from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import math
from typing import Any

from cognitive_exante import EPSILON, _distance, evaluate_exante_forecast
from npc_need_scheduler import NpcNeedScheduler


def _usable(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None


def freeze_contextual_forecast(
    *,
    frame_id: str,
    world_version: int,
    world_sequence: int,
    observer: dict[str, Any],
    needs: dict[str, Any],
    target_provider: Any,
    threshold: float = 0.70,
    environment: dict[str, Any] | None = None,
    experience_provider: Any | None = None,
    need_source: str = "entity_properties_bootstrap",
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Read-only baseline from existing need policy and configured target evidence.

    This is NOT the runtime's action/strategy selection. If a unique configured
    target does not exist, abstain rather than inventing an intent.
    """
    env = environment if isinstance(environment, dict) else {}
    entity_props = observer.get("properties") if isinstance(observer.get("properties"), dict) else {}
    value_map = {key: _usable(needs.get(key)) for key in NpcNeedScheduler.DEFAULT_PRIORITIES}
    forecast: dict[str, Any] = {
        "forecast_schema": "cognitive_contextual_need_target_v1",
        "predictor_id": "need-pressure-configured-target-baseline-v1",
        "selection_phase": "pre_tick",
        "horizon_ticks": 1,
        "issued_frame_id": frame_id,
        "issued_world_version": int(world_version),
        "issued_world_sequence": int(world_sequence),
        "predicts_action": False,
        "action": None,
        "candidate_id": None,
        "status": "abstained",
        "reason": "need_state_unavailable",
        "need_source": need_source,
        "needs": value_map,
        "selected_need": None,
        "need_pressure": None,
        "threshold": float(threshold),
        "target_entity_id": None,
        "target_region_id": None,
        "target_position": None,
        "distance_before": None,
        "expected_direction": None,
        "forecast_id": None,
        "context": {
            "region_id": observer.get("region_id"),
            "period": env.get("period"),
            "weather": env.get("weather"),
            "danger_level": env.get("danger_level"),
        },
        "experience": None,
    }
    if any(value is None for value in value_map.values()):
        return forecast, None

    ranked = [
        (value * NpcNeedScheduler.DEFAULT_PRIORITIES[key], key, value)
        for key, value in value_map.items()
        if value is not None and value >= threshold
    ]
    if not ranked:
        forecast["reason"] = "no_urgent_need"
        return forecast, None
    ranked.sort(key=lambda row: (-row[0], row[1]))
    pressure, need, value = ranked[0]
    forecast.update(selected_need=need, need_pressure=value, weighted_pressure=pressure)

    references = set()
    singular = str(entity_props.get(NpcNeedScheduler.TARGET_FIELDS[need]) or "").strip()
    if singular:
        references.add(singular)
    plural = entity_props.get(NpcNeedScheduler.TARGET_LIST_FIELDS[need])
    if isinstance(plural, list):
        references.update(str(item).strip() for item in plural if str(item).strip())
    forecast["configured_target_ids"] = sorted(references)
    if not references:
        forecast["reason"] = "no_configured_target"
        return forecast, None
    if len(references) != 1:
        forecast["reason"] = "multiple_targets_without_ranked_evidence"
        return forecast, None
    target_id = next(iter(references))
    target = target_provider(target_id)
    if not isinstance(target, dict):
        forecast["reason"] = "target_unavailable"
        return forecast, None
    distance = _distance(observer, target)
    if distance is None:
        forecast["reason"] = "target_position_unavailable"
        return forecast, None
    forecast.update(
        target_entity_id=target_id,
        target_region_id=target.get("region_id"),
        target_position=deepcopy(target.get("position")),
        distance_before=distance,
    )
    if distance <= EPSILON:
        forecast["reason"] = "already_at_target"
        return forecast, deepcopy(target)
    context = {
        "period": env.get("period"),
        "weather": env.get("weather") or env.get("weather_state"),
        "danger_level": env.get("danger_level"),
        "region_id": observer.get("region_id"),
    }
    stats_getter = getattr(experience_provider, "stats", None)
    if callable(stats_getter):
        evidence = stats_getter(str(observer.get("id") or ""), need, target_id, context)
        if isinstance(evidence, dict):
            forecast["experience"] = {
                "source": "npc_strategy_experience",
                "sample_count": int(evidence.get("count", 0)),
                "empirical_ready": bool(evidence.get("empirical_ready", False)),
                "mean_elapsed_ticks": evidence.get("mean_elapsed_ticks"),
                "last_plan_id": evidence.get("last_plan_id"),
                "used_to_rank": False,
            }
    key = f"{frame_id}|{world_sequence}|{need}|{target_id}|{distance:.12f}"
    forecast.update(
        status="issued", reason=None,
        expected_direction="toward_frozen_target",
        forecast_id="context_exante_" + sha256(key.encode("utf-8")).hexdigest()[:24],
    )
    return forecast, deepcopy(target)


def evaluate_contextual_forecast(
    forecast: dict[str, Any],
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    target_after: dict[str, Any] | None,
) -> dict[str, Any]:
    return evaluate_exante_forecast(
        forecast,
        observer_before=before,
        observer_after=after,
        target_after=target_after,
    )


def stationary_evidence(
    *,
    movement_distance: float | None,
    tick_result: dict[str, Any],
    contextual_forecast: dict[str, Any] | None,
    observer_id: str = "nov",
) -> dict[str, Any]:
    """Label observed preconditions, never claim to identify a causal blocker."""
    result = {
        "schema": "cognitive_stationary_evidence_v1",
        "stationary": movement_distance is not None and movement_distance <= EPSILON,
        "evidence_label": None,
        "need_statuses": [],
        "plan_statuses": [],
        "contextual_forecast_reason": (contextual_forecast or {}).get("reason"),
        "causal_explanation_evaluable": False,
    }
    if not result["stationary"]:
        return result
    needs = [
        str(item.get("status") or "").lower()
        for item in (tick_result.get("npc_needs") or [])
        if isinstance(item, dict) and str(item.get("npc_id") or "") in {observer_id, ""}
    ]
    plans = [
        str(item.get("status") or "").lower()
        for item in (tick_result.get("plans") or [])
        if isinstance(item, dict) and str(item.get("actor_entity_id") or "") in {observer_id, ""}
    ]
    result["need_statuses"] = sorted(needs)
    result["plan_statuses"] = sorted(plans)
    if "no_target" in needs:
        label = "need_no_target_observed"
    elif "cooldown" in needs:
        label = "need_cooldown_observed"
    elif "already_active" in needs:
        label = "need_active_observed"
    elif plans:
        label = "plan_status_without_displacement"
    else:
        label = "no_plan_result_in_tick"
    result["evidence_label"] = label
    return result
