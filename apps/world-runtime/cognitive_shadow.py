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
        frame = build_nov_cognitive_frame(
            world=world,
            observer=observer,
            targets=self._targets(observer),
        )
        return ShadowToken(
            frame=frame,
            world_version=int(world.get("version", 0) or 0),
            world_sequence=int(world.get("sequence", 0) or 0),
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
            "tick_activity": {
                "plans": len(tick_result.get("plans") or []),
                "npc_needs": len(tick_result.get("npc_needs") or []),
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
            "last": None,
        }

    records = 0
    exact = 0
    ambiguous = 0
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
            last = row

    return {
        "records": records,
        "exact_structural_matches": exact,
        "ambiguous_matches": ambiguous,
        "exact_match_rate": (exact / records) if records else None,
        "last": last,
    }
