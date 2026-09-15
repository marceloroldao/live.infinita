from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from story_narrator import LiveStoryNarrator, StoryCue, THEME_LABELS


class StoryContinuityNarrator(LiveStoryNarrator):
    """Interaction-only host that can continue from deterministic story state."""

    @staticmethod
    def _world_context(world: dict[str, Any]) -> dict[str, Any]:
        base = LiveStoryNarrator._world_context(world)
        story = world.get("story") if isinstance(world.get("story"), dict) else {}
        beats = [deepcopy(row) for row in story.get("beats", []) if isinstance(row, dict)][-4:]
        base["story"] = {
            "chapter": story.get("chapter"),
            "beat": story.get("beat"),
            "title": story.get("title"),
            "arc": story.get("arc"),
            "motif": story.get("motif"),
            "target_region_id": story.get("target_region_id"),
            "target_entity_id": story.get("target_entity_id"),
            "last_interaction": deepcopy(story.get("last_interaction")) if isinstance(story.get("last_interaction"), dict) else None,
            "recent_confirmed_beats": beats,
        }
        return base

    @staticmethod
    def _system_prompt(mode: str) -> str:
        return LiveStoryNarrator._system_prompt(mode) + (
            " Você também mantém continuidade narrativa usando o campo story do contexto. "
            "Os story.recent_confirmed_beats são fatos determinísticos já aceitos pelo runtime; pode tratá-los como acontecimentos reais. "
            "Se interaction_result.world_mutated for verdadeiro, a mudança já aconteceu: descreva a consequência concreta em vez de falar como possibilidade. "
            "Conecte a consequência ao capítulo atual em linguagem natural e, quando couber, termine com um gancho curto para a continuação. "
            "Se houver confirmed_collective_evolution, esse novo capítulo também já aconteceu e deve ser narrado como consequência da direção coletiva. "
            "Nunca transforme sua própria frase, interpretação ou sugestão em fato persistente."
        )

    def render_interaction(
        self,
        *,
        config: dict[str, Any],
        comment: dict[str, Any],
        world: dict[str, Any],
        collective_state: dict[str, Any],
        interaction_result: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> StoryCue:
        cue = super().render_interaction(
            config=config,
            comment=comment,
            world=world,
            collective_state=collective_state,
            interaction_result=interaction_result,
            now=now,
        )
        if not bool((interaction_result or {}).get("world_mutated")) or not cue.generated_by.startswith("fallback"):
            return cue

        story = world.get("story") if isinstance(world.get("story"), dict) else {}
        last = story.get("last_interaction") if isinstance(story.get("last_interaction"), dict) else {}
        consequence = str(last.get("consequence") or "").strip()
        if not consequence:
            return cue
        name = self._display_name(comment)
        prefix = f"{name}, " if cue.mode == "individual" and name else ""
        title = str(story.get("title") or "").strip()
        hook = f" A história agora segue por {title}." if title else " A história continua a partir daí."
        return StoryCue(
            cue_id=cue.cue_id,
            text=f"{prefix}{consequence}{hook}",
            mode=cue.mode,
            participants=cue.participants,
            source=cue.source,
            actor_id=cue.actor_id,
            display_name=cue.display_name,
            theme=cue.theme,
            generated_by="fallback:story-continuity",
            created_at_unix=cue.created_at_unix,
        )

    def render_collective_evolution(
        self,
        *,
        config: dict[str, Any],
        world: dict[str, Any],
        collective_state: dict[str, Any],
        evolution: dict[str, Any],
        now: float | None = None,
    ) -> StoryCue:
        at = float(now if now is not None else time.time())
        active = self.active_snapshot(at)
        participants = int(active.get("participants", 0))
        if participants <= 0:
            return StoryCue(
                cue_id=self._next_cue_id("silent-evolution", str(evolution.get("chapter") or "")),
                text="",
                mode="silent",
                participants=0,
                source="collective_intent",
                theme=str(evolution.get("theme") or "").strip() or None,
                generated_by="suppressed:no-active-interaction",
                created_at_unix=at,
            )

        theme = str(evolution.get("theme") or "").strip() or None
        direction = THEME_LABELS.get(theme or "", "um novo caminho")
        story = world.get("story") if isinstance(world.get("story"), dict) else {}
        title = str(story.get("title") or "").strip()
        text = (
            f"Vocês puxaram a história para {direction}. Nov segue a mudança e um novo trecho do mundo se abre. "
            + (f"Agora começa: {title}." if title else "A história continua dali.")
        )
        generated_by = "fallback:collective-story"
        api_key = str(config.get("openai_api_key") or "").strip()
        model = str(config.get("openai_model") or "gpt-5-mini").strip()
        self.last_generation_error = None
        if api_key and model:
            payload = {
                "mode": "collective",
                "recent_audience": active,
                "collective_intent": self._collective_context(collective_state),
                "world": self._world_context(world),
                "confirmed_collective_evolution": deepcopy(evolution),
            }
            try:
                candidate = self._render_openai(api_key=api_key, model=model, mode="collective", payload=payload)
                if candidate:
                    text = candidate
                    generated_by = f"openai:{model}:collective-story"
            except Exception as exc:
                self.last_generation_error = f"{type(exc).__name__}: {exc}"[:240]

        return StoryCue(
            cue_id=self._next_cue_id("collective-evolution", str(evolution.get("chapter") or "")),
            text=text,
            mode="collective",
            participants=participants,
            source="collective_intent",
            theme=theme,
            generated_by=generated_by,
            created_at_unix=at,
        )
