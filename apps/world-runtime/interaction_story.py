from __future__ import annotations

from copy import deepcopy
from typing import Any


ACTION_CONSEQUENCES: dict[str, str] = {
    "nov_to_fire": "Nov seguiu em direção à fogueira.",
    "nov_to_shelter": "Nov seguiu em direção ao abrigo.",
    "nov_to_forest": "Nov entrou mais fundo na floresta.",
    "nov_explore": "Nov escolheu um novo caminho para explorar.",
    "spawn_person": "Uma nova presença apareceu no mundo.",
    "move_tree": "Uma árvore mudou de lugar no cenário.",
    "toggle_fire": "O estado da fogueira mudou.",
    "set_night": "A noite tomou conta do cenário.",
    "set_day": "A luz do dia voltou ao cenário.",
}

ACTION_THEMES: dict[str, str] = {
    "nov_to_forest": "forest",
}


class InteractionStoryContinuity:
    """Build bounded story-state updates from confirmed runtime consequences.

    This planner is deliberately deterministic and read-only. It never interprets
    free-form language and never consumes LLM prose. Only an already-confirmed
    runtime mutation can become a persistent story beat.
    """

    def __init__(self, max_beats: int = 16) -> None:
        self.max_beats = max(4, int(max_beats))

    @staticmethod
    def _action(interaction_result: dict[str, Any]) -> str:
        event = interaction_result.get("event") if isinstance(interaction_result.get("event"), dict) else {}
        validation = interaction_result.get("validation") if isinstance(interaction_result.get("validation"), dict) else {}
        return str(event.get("action") or validation.get("action") or "").strip()

    def plan(
        self,
        *,
        world: dict[str, Any],
        comment: dict[str, Any],
        interaction_result: dict[str, Any],
        collective_state: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        if not bool(interaction_result.get("world_mutated")):
            return None
        action = self._action(interaction_result)
        if not action:
            return None

        event = interaction_result.get("event") if isinstance(interaction_result.get("event"), dict) else {}
        previous = world.get("story") if isinstance(world.get("story"), dict) else {}
        story = deepcopy(previous)
        beat_number = max(0, int(story.get("beat", 0))) + 1
        collective = collective_state if isinstance(collective_state, dict) else {}
        theme = ACTION_THEMES.get(action) or str(collective.get("dominant") or story.get("motif") or "").strip() or None
        consequence = ACTION_CONSEQUENCES.get(action, "A interação produziu uma mudança confirmada no mundo.")

        beat = {
            "beat": beat_number,
            "kind": "interaction_consequence",
            "source": str(comment.get("source") or "audience"),
            "source_event_id": str(comment.get("source_event_id") or "") or None,
            "world_event_id": str(event.get("event_id") or "") or None,
            "action": action,
            "theme": theme,
            "consequence": consequence,
            "at_unix": now,
        }
        beats = [deepcopy(row) for row in story.get("beats", []) if isinstance(row, dict)]
        beats.append(beat)
        beats = beats[-self.max_beats :]

        story["beat"] = beat_number
        story["beats"] = beats
        story["last_interaction"] = deepcopy(beat)
        story["updated_at_unix"] = now
        if theme and not story.get("motif"):
            story["motif"] = theme
        if not story.get("source"):
            story["source"] = "audience_interaction"

        return {
            "operation": {"op": "set_world", "path": ["story"], "value": story},
            "story": story,
            "beat": beat,
            "consequence": consequence,
        }
