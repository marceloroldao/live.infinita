from __future__ import annotations

import json
import math
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from memoria_v2_adapter import (
    CognitiveFrame,
    NOV_ACTIONS,
    build_nov_cognitive_frame,
    target_for_action,
)


@dataclass(frozen=True, slots=True)
class ShadowToken:
    frame: CognitiveFrame
    world_version: int
    world_sequence: int
    observer_snapshot: dict[str, Any]
    target_snapshots: dict[str, dict[str, Any]]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _need_levels(observer: dict[str, Any]) -> dict[str, float]:
    properties = observer.get("properties") if isinstance(observer.get("properties"), dict) else {}
    raw = properties.get("needs") if isinstance(properties.get("needs"), dict) else {}
    result: dict[str, float] = {}
    for name, value in raw.items():
        parsed = _finite_number(value)
        if parsed is not None:
            result[str(name)] = parsed
    return result


class CognitiveShadowRecorder:
    """Observe cognitive alternatives without participating in world authority.

    The recorder is intentionally fail-open and read-only with respect to World State.
    It only appends observational records to its own JSONL file.  No proposal, plan,
    mutation or actor state is created from shadow output.
    """

    def __init__(
        self,
        path: Path,
        *,
        world_provider: Callable[[], dict[str, Any]],
        store: Any,
        observer_id: str = "nov",
        enabled: bool = False,
    ) -> None:
        self.path = Path(path)
        self.world_provider = world_provider
        self.store = store
        self.observer_id = observer_id
        self.enabled = bool(enabled)

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        value = self.store.get_entity(entity_id)
        return value if isinstance(value, dict) else None

    def _targets(self, observer: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for action in NOV_ACTIONS:
            target_id = target_for_action(action, observer)
            if target_id in result:
                continue
            target = self._entity(target_id)
            if target is not None:
                result[target_id] = target
        return result

    def begin_tick(self) -> ShadowToken | None:
        if not self.enabled:
            return None
        world = self.world_provider()
        observer = self._entity(self.observer_id)
        if observer is None:
            return None
        targets = self._targets(observer)
        frame = build_nov_cognitive_frame(
            world=world,
            observer=observer,
            targets=targets,
        )
        return ShadowToken(
            frame=frame,
            world_version=int(world.get("version", 0) or 0),
            world_sequence=int(world.get("sequence", 0) or 0),
            observer_snapshot={
                "id": observer.get("id"),
                "region_id": observer.get("region_id"),
                "position": dict(observer.get("position") or {}),
                "needs": _need_levels(observer),
            },
            target_snapshots={
                key: {
                    "id": target.get("id"),
                    "region_id": target.get("region_id"),
                    "position": dict(target.get("position") or {}),
                }
                for key, target in targets.items()
            },
        )

    @staticmethod
    def _distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
        a_pos = a.get("position") if isinstance(a.get("position"), dict) else {}
        b_pos = b.get("position") if isinstance(b.get("position"), dict) else {}
        try:
            return math.hypot(float(a_pos["x"]) - float(b_pos["x"]), float(a_pos["y"]) - float(b_pos["y"]))
        except (KeyError, TypeError, ValueError):
            return None

    def _nearest_target(
        self,
        observer: dict[str, Any],
        targets: dict[str, dict[str, Any]],
    ) -> tuple[str | None, float | None]:
        ranked: list[tuple[float, str]] = []
        for target_id, target in targets.items():
            distance = self._distance(observer, target)
            if distance is not None:
                ranked.append((distance, target_id))
        if not ranked:
            return None, None
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][1], ranked[0][0]

    def _best_candidate(
        self,
        token: ShadowToken,
        observer: dict[str, Any],
        targets: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        actual_region = str(observer.get("region_id") or "")
        nearest_id, nearest_distance = self._nearest_target(observer, targets)
        candidates_by_proposal = {
            item.proposal_id: item for item in token.frame.candidate_outcomes
        }
        scored: list[tuple[int, str, dict[str, Any]]] = []

        for intervention in token.frame.available_interventions:
            target = targets.get(intervention.target_entity_id)
            if not isinstance(target, dict):
                continue
            target_region = str(target.get("region_id") or "")
            score = 0
            if target_region and target_region == actual_region:
                score += 1
            if nearest_id and nearest_id == intervention.target_entity_id:
                score += 1
            candidate = candidates_by_proposal.get(intervention.proposal_id)
            scored.append((
                score,
                intervention.proposal_id,
                {
                    "proposal_id": intervention.proposal_id,
                    "action": intervention.action,
                    "target_entity_id": intervention.target_entity_id,
                    "target_region_id": target_region or None,
                    "candidate_id": candidate.candidate_id if candidate is not None else None,
                    "match_score": score,
                    "max_match_score": 2,
                    "exact_structural_match": score == 2,
                    "nearest_target_entity_id": nearest_id,
                    "nearest_target_distance": nearest_distance,
                },
            ))

        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1]))
        best_score = scored[0][0]
        best = [item for item in scored if item[0] == best_score]
        result = dict(best[0][2])
        result["ambiguous"] = len(best) > 1
        result["selection_phase"] = "posthoc"
        result["predictive_accuracy_evaluable"] = False
        return result

    def complete_tick(
        self,
        token: ShadowToken | None,
        tick_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled or token is None:
            return None

        world = self.world_provider()
        observer = self._entity(self.observer_id)
        if observer is None:
            return None
        targets = self._targets(observer)
        best = self._best_candidate(token, observer, targets)
        after_tick = int((tick_result.get("clock") or {}).get("tick", world.get("sequence", 0)) or 0)
        shadow_seed = f"{token.frame.frame_id}|{after_tick}|{world.get('version', 0)}|{world.get('sequence', 0)}"
        shadow_id = "shadow_" + sha256(shadow_seed.encode("utf-8")).hexdigest()[:24]

        before_observer = token.observer_snapshot
        before_position = dict(before_observer.get("position") or {})
        after_position = dict(observer.get("position") or {})
        movement_distance = self._distance(before_observer, observer)
        target_id = best.get("target_entity_id") if isinstance(best, dict) else None
        predicted_target_before = token.target_snapshots.get(target_id) if target_id else None
        predicted_target_after = targets.get(target_id) if target_id else None
        distance_before = self._distance(before_observer, predicted_target_before) if predicted_target_before else None
        distance_after = self._distance(observer, predicted_target_before) if predicted_target_before else None
        target_movement = (
            self._distance(predicted_target_before, predicted_target_after)
            if predicted_target_before and predicted_target_after else None
        )
        target_stable = target_movement == 0 if target_movement is not None else None
        target_progress = None
        if target_stable and distance_before is not None and distance_after is not None:
            target_progress = distance_before - distance_after
        needs_before = before_observer.get("needs") or {}
        needs_after = _need_levels(observer)
        need_deltas = {
            name: needs_after[name] - before
            for name, before in needs_before.items()
            if name in needs_after
        }

        terminal = {"completed", "failed", "cancelled", "canceled"}
        plan_outcomes = [
            {
                "plan_id": row.get("plan_id"),
                "status": str(row.get("status") or "").lower(),
                "actor_entity_id": row.get("actor_entity_id"),
                "preemption_count": row.get("preemption_count"),
                "replan_count": row.get("replan_count"),
            }
            for row in (tick_result.get("plans") or [])
            if isinstance(row, dict)
            and str(row.get("status") or "").lower() in terminal
            and row.get("actor_entity_id") in (None, self.observer_id)
        ]
        need_outcomes = [
            {"status": str(row.get("status") or "").lower(), "npc_id": row.get("npc_id") or row.get("actor_entity_id")}
            for row in (tick_result.get("npc_needs") or [])
            if isinstance(row, dict) and str(row.get("status") or "").lower() in {"scheduled", "completed", "failed"}
        ]

        completed_plan_ids = {
            str(row["plan_id"]) for row in plan_outcomes
            if row.get("status") == "completed" and row.get("plan_id")
        }
        satisfaction_outcomes: list[dict[str, Any]] = []
        for row in (tick_result.get("npc_need_outcomes") or []):
            if not isinstance(row, dict) or row.get("npc_id") != self.observer_id:
                continue
            experience = row.get("strategy_experience") if isinstance(row.get("strategy_experience"), dict) else {}
            observed_target_id = experience.get("target_entity_id")
            before = _finite_number(row.get("before"))
            after = _finite_number(row.get("after"))
            delta = before - after if before is not None and after is not None else None
            plan_id = row.get("plan_id")
            satisfaction_outcomes.append({
                "plan_id": plan_id,
                "proposal_id": row.get("proposal_id"),
                "npc_id": row.get("npc_id"),
                "need": row.get("need"),
                "status": row.get("status"),
                "target_entity_id": observed_target_id,
                "before": before,
                "after": after,
                "reported_amount": _finite_number(row.get("amount")),
                "observed_satisfaction_delta": delta,
                "matched_terminal_plan_in_tick": bool(plan_id and str(plan_id) in completed_plan_ids),
                "matches_posthoc_target": (
                    observed_target_id == target_id
                    if observed_target_id and target_id else None
                ),
            })

        record = {
            "shadow_id": shadow_id,
            "frame_id": token.frame.frame_id,
            "observer_id": self.observer_id,
            "before": {
                "tick": token.frame.tick_id,
                "world_version": token.world_version,
                "world_sequence": token.world_sequence,
            },
            "after": {
                "tick": after_tick,
                "world_version": int(world.get("version", 0) or 0),
                "world_sequence": int(world.get("sequence", 0) or 0),
                "region_id": observer.get("region_id"),
                "position": dict(observer.get("position") or {}),
            },
            "candidate_count": len(token.frame.candidate_outcomes),
            "best_candidate": best,
            "evaluation_schema": "posthoc-trajectory-need-v1",
            "predictive_accuracy_evaluable": False,
            "trajectory_observation": {
                "before_position": before_position,
                "after_position": after_position,
                "movement_distance": movement_distance,
                "before_region_id": before_observer.get("region_id"),
                "after_region_id": observer.get("region_id"),
                "need_levels_before": needs_before,
                "need_levels_after": needs_after,
                "need_level_deltas": need_deltas,
                "region_changed": str(before_observer.get("region_id") or "") != str(observer.get("region_id") or ""),
                "predicted_target_entity_id": best.get("target_entity_id") if isinstance(best, dict) else None,
                "distance_to_predicted_target_before": distance_before,
                "distance_to_predicted_target_after": distance_after,
                "predicted_target_movement_distance": target_movement,
                "predicted_target_stable": target_stable,
                "progress_toward_predicted_target": target_progress,
                "moved_toward_predicted_target": target_progress is not None and target_progress > 0.0,
                "plan_outcomes": plan_outcomes,
                "need_outcomes": need_outcomes,
                "need_satisfaction_outcomes": satisfaction_outcomes,
            },
            "tick_activity": {
                "plans": len(tick_result.get("plans") or []),
                "npc_needs": len(tick_result.get("npc_needs") or []),
                "npc_need_outcomes": len(tick_result.get("npc_need_outcomes") or []),
                "npc_strategies": len(tick_result.get("npc_strategies") or []),
                "events": len(tick_result.get("events") or []),
                "conditional_events": len(tick_result.get("conditional_events") or []),
            },
            "authority": "shadow-observer",
            "world_mutated_by_shadow": False,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return record


def summarize_shadow_file(path: Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {
            "records": 0,
            "exact_structural_matches": 0,
            "ambiguous_matches": 0,
            "exact_match_rate": None,
            "trajectory_records": 0,
            "stable_target_records": 0,
            "positive_target_progress_records": 0,
            "need_satisfaction_outcomes": 0,
            "positive_need_satisfaction_outcomes": 0,
            "linked_terminal_plan_outcomes": 0,
            "posthoc_target_matches": 0,
            "last": None,
        }

    records = 0
    exact = 0
    ambiguous = 0
    trajectory_records = stable_target_records = positive_target_progress_records = 0
    satisfaction_records = positive_satisfaction = linked_outcomes = target_matches = 0
    last: dict[str, Any] | None = None
    with file_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            records += 1
            best = row.get("best_candidate") if isinstance(row.get("best_candidate"), dict) else {}
            if bool(best.get("exact_structural_match")):
                exact += 1
            if bool(best.get("ambiguous")):
                ambiguous += 1
            trajectory = row.get("trajectory_observation")
            if isinstance(trajectory, dict):
                trajectory_records += 1
                if trajectory.get("predicted_target_stable") is True:
                    stable_target_records += 1
                progress = _finite_number(trajectory.get("progress_toward_predicted_target"))
                if progress is not None and progress > 0:
                    positive_target_progress_records += 1
                for outcome in trajectory.get("need_satisfaction_outcomes") or []:
                    if not isinstance(outcome, dict):
                        continue
                    satisfaction_records += 1
                    delta = _finite_number(outcome.get("observed_satisfaction_delta"))
                    if delta is not None and delta > 0:
                        positive_satisfaction += 1
                    if outcome.get("matched_terminal_plan_in_tick") is True:
                        linked_outcomes += 1
                    if outcome.get("matches_posthoc_target") is True:
                        target_matches += 1
            last = row

    return {
        "records": records,
        "exact_structural_matches": exact,
        "ambiguous_matches": ambiguous,
        "exact_match_rate": (exact / records) if records else None,
        "trajectory_records": trajectory_records,
        "stable_target_records": stable_target_records,
        "positive_target_progress_records": positive_target_progress_records,
        "need_satisfaction_outcomes": satisfaction_records,
        "positive_need_satisfaction_outcomes": positive_satisfaction,
        "linked_terminal_plan_outcomes": linked_outcomes,
        "posthoc_target_matches": target_matches,
        "last": last,
    }
