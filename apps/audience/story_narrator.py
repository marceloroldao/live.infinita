from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


THEME_LABELS = {
    "forest": "a floresta e seus caminhos escondidos",
    "river": "o rio e o que pode existir além da margem",
    "village": "uma vila e a possibilidade de novos encontros",
    "field": "o campo aberto e um horizonte ainda desconhecido",
}


@dataclass(frozen=True)
class StoryCue:
    cue_id: str
    text: str
    mode: str
    participants: int
    source: str
    actor_id: str | None = None
    display_name: str | None = None
    theme: str | None = None
    generated_by: str = "fallback"
    created_at_unix: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "text": self.text,
            "mode": self.mode,
            "participants": self.participants,
            "source": self.source,
            "actor_id": self.actor_id,
            "display_name": self.display_name,
            "theme": self.theme,
            "generated_by": self.generated_by,
            "created_at_unix": self.created_at_unix,
        }


class LiveStoryNarrator:
    """Interaction-only presentation narrator.

    The narrator observes audience language and World State but never mutates the
    world. Its short in-memory history is presentation context only, enough to
    continue a story between human interactions without becoming a second source
    of truth.
    """

    def __init__(
        self,
        *,
        window_seconds: float | None = None,
        timeout_seconds: float = 12.0,
        transport: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self.window_seconds = float(
            window_seconds
            if window_seconds is not None
            else os.getenv("LIVE_INFINITA_STORY_WINDOW_SECONDS", "90")
        )
        self.timeout_seconds = float(timeout_seconds)
        self.comments: deque[dict[str, Any]] = deque(maxlen=64)
        self.history: deque[dict[str, Any]] = deque(maxlen=8)
        self.transport = transport or self._openai_transport
        self.sequence = 0

    def _prune(self, now: float) -> None:
        cutoff = now - max(10.0, self.window_seconds)
        while self.comments and float(self.comments[0]["at_unix"]) < cutoff:
            self.comments.popleft()

    @staticmethod
    def _actor_key(source: str, actor_id: str) -> str:
        return f"{str(source).strip().lower()}:{str(actor_id).strip()}"

    def observe_comment(
        self,
        *,
        source: str,
        actor_id: str,
        display_name: str | None,
        text: str,
        source_event_id: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        at = float(now if now is not None else time.time())
        self._prune(at)
        row = {
            "at_unix": at,
            "source": str(source).strip().lower(),
            "actor_id": str(actor_id).strip() or "anonymous",
            "actor_key": self._actor_key(source, actor_id or "anonymous"),
            "display_name": str(display_name or "").strip() or None,
            "text": str(text or "").strip()[:500],
            "source_event_id": str(source_event_id or "").strip() or None,
        }
        self.comments.append(row)
        return deepcopy(row)

    def active_snapshot(self, now: float | None = None) -> dict[str, Any]:
        at = float(now if now is not None else time.time())
        self._prune(at)
        actors: dict[str, dict[str, Any]] = {}
        for row in self.comments:
            actors[str(row["actor_key"])] = row
        return {
            "participants": len(actors),
            "participant_keys": sorted(actors),
            "recent_comments": [deepcopy(row) for row in list(self.comments)[-6:]],
            "window_seconds": self.window_seconds,
        }

    def story_snapshot(self) -> list[dict[str, Any]]:
        return [deepcopy(row) for row in self.history]

    def _remember(self, cue: StoryCue) -> StoryCue:
        self.history.append({
            "cue_id": cue.cue_id,
            "text": cue.text[:650],
            "mode": cue.mode,
            "theme": cue.theme,
            "participants": cue.participants,
            "created_at_unix": cue.created_at_unix,
        })
        return cue

    @staticmethod
    def _world_context(world: dict[str, Any]) -> dict[str, Any]:
        environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
        story = world.get("story") if isinstance(world.get("story"), dict) else {}
        return {
            "world_id": world.get("world_id"),
            "sequence": world.get("sequence"),
            "period": environment.get("period"),
            "weather": environment.get("weather"),
            "biome": environment.get("biome"),
            "region_id": environment.get("region_id"),
            "region_label": environment.get("region_label"),
            "story": deepcopy(story),
        }

    @staticmethod
    def _collective_context(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "dominant": state.get("dominant"),
            "dominance": state.get("dominance"),
            "contributors": state.get("contributors"),
            "comment_signals": state.get("comment_signals"),
            "chapter": state.get("chapter"),
            "ready": bool(state.get("ready")),
        }

    @staticmethod
    def _display_name(row: dict[str, Any]) -> str:
        value = str(row.get("display_name") or "").strip()
        if value:
            return value[:60]
        actor = str(row.get("actor_id") or "Visitante").strip()
        return actor[:60] or "Visitante"

    def _fallback_interaction(
        self,
        *,
        comment: dict[str, Any],
        active: dict[str, Any],
        collective_state: dict[str, Any],
    ) -> tuple[str, str]:
        participants = int(active.get("participants", 0))
        theme = str(collective_state.get("dominant") or "").strip() or None
        theme_phrase = THEME_LABELS.get(theme or "", "um caminho que ainda não tomou forma")
        continuing = bool(self.history)
        if participants <= 1:
            name = self._display_name(comment)
            opening = f"{name}, a história continua de onde ficou. " if continuing else f"{name}, Nov percebeu sua presença. "
            return "individual", (
                opening
                + f"Sua voz aproxima {theme_phrase}; Nov observa o caminho por um instante, "
                "como se esperasse o seu próximo sinal."
            )
        opening = "A história muda de direção outra vez. " if continuing else "As vozes começam a se encontrar. "
        return "collective", (
            opening
            + f"Elas apontam para {theme_phrase}; Nov ainda não sabe o que existe adiante, "
            "mas o próximo gesto do grupo pode abrir uma passagem nova."
        )

    def _fallback_evolution(
        self,
        *,
        evolution: dict[str, Any],
        collective_state: dict[str, Any],
    ) -> str:
        theme = str(evolution.get("theme") or collective_state.get("dominant") or "").strip() or None
        phrase = THEME_LABELS.get(theme or "", "um lugar que ainda não tinha nome")
        chapter = int(evolution.get("chapter") or collective_state.get("chapter") or 0)
        bridge = "O fio da história encontra uma resposta. " if self.history else "Desta vez as vozes concordaram. "
        return (
            bridge
            + f"{phrase.capitalize()} começa a ganhar forma no capítulo {chapter}; "
            "Nov segue adiante, enquanto uma nova pergunta permanece aberta no caminho."
        )

    def _next_cue_id(self, prefix: str, source_event_id: str | None = None) -> str:
        self.sequence += 1
        suffix = str(source_event_id or "").strip().replace(" ", "-")[:80]
        if suffix:
            return f"{prefix}:{suffix}:{self.sequence}"
        return f"{prefix}:{int(time.time() * 1000)}:{self.sequence}"

    @staticmethod
    def _system_prompt(mode: str) -> str:
        audience_rule = (
            "Há uma única pessoa interagindo: responda diretamente a ela pelo nome, sem soar como atendimento ao cliente."
            if mode == "individual"
            else "Há várias pessoas interagindo: sintetize a direção que surge entre as vozes; não responda comentário por comentário e não cite métricas."
        )
        return (
            "Você é a voz narrativa da Live Infinita, uma história contínua acontecendo ao vivo. "
            "Fale em português do Brasil, em 2 ou 3 frases curtas, naturais e cinematográficas. "
            f"{audience_rule} "
            "Continue o fio das falas anteriores quando houver histórico narrativo. "
            "Conecte a fala ao estado atual do mundo e à intenção da audiência. "
            "Nunca mencione API, sistema, score, porcentagem, JSON, modelo, comando, evento, World State ou termos técnicos. "
            "Não narre ações autônomas como relatório. Não invente fatos que o contexto não confirma; desejos ainda não realizados devem soar como possibilidades. "
            "Termine com um pequeno gancho narrativo para o próximo gesto da audiência. "
            "Não use listas, títulos, aspas ou emojis."
        )

    def _render_openai(self, *, api_key: str, model: str, mode: str, payload: dict[str, Any]) -> str:
        request_payload = {
            "model": model,
            "max_output_tokens": 160,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": self._system_prompt(mode)}],
                },
                {
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "Contexto narrativo somente-leitura:\n" + json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }],
                },
            ],
        }
        response = self.transport(request_payload, api_key)
        return " ".join(self._extract_text(response).split())[:650]

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
        at = float(now if now is not None else time.time())
        active = self.active_snapshot(at)
        participants = max(1, int(active.get("participants", 0)))
        fallback_mode, fallback_text = self._fallback_interaction(
            comment=comment,
            active=active,
            collective_state=collective_state,
        )
        mode = "individual" if participants <= 1 else "collective"
        text = fallback_text
        generated_by = "fallback"
        api_key = str(config.get("openai_api_key") or "").strip()
        model = str(config.get("openai_model") or "gpt-5-mini").strip()
        if api_key and model:
            payload = {
                "mode": mode,
                "current_comment": deepcopy(comment),
                "recent_audience": active,
                "story_history": self.story_snapshot(),
                "collective_intent": self._collective_context(collective_state),
                "world": self._world_context(world),
                "interaction_result": deepcopy(interaction_result or {}),
            }
            try:
                candidate = self._render_openai(api_key=api_key, model=model, mode=mode, payload=payload)
                if candidate:
                    text = candidate
                    generated_by = f"openai:{model}"
            except Exception:
                mode = fallback_mode
                text = fallback_text

        theme = str(collective_state.get("dominant") or "").strip() or None
        return self._remember(StoryCue(
            cue_id=self._next_cue_id("interaction", comment.get("source_event_id")),
            text=text,
            mode=mode,
            participants=participants,
            source=str(comment.get("source") or "audience"),
            actor_id=str(comment.get("actor_id") or "") or None,
            display_name=comment.get("display_name"),
            theme=theme,
            generated_by=generated_by,
            created_at_unix=at,
        ))

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
        participants = max(int(active.get("participants", 0)), int(evolution.get("contributors") or 0), 2)
        fallback = self._fallback_evolution(evolution=evolution, collective_state=collective_state)
        text = fallback
        generated_by = "fallback"
        api_key = str(config.get("openai_api_key") or "").strip()
        model = str(config.get("openai_model") or "gpt-5-mini").strip()
        if api_key and model:
            payload = {
                "mode": "collective_chapter",
                "recent_audience": active,
                "story_history": self.story_snapshot(),
                "collective_intent": self._collective_context(collective_state),
                "world": self._world_context(world),
                "evolution": deepcopy(evolution),
            }
            try:
                candidate = self._render_openai(api_key=api_key, model=model, mode="collective", payload=payload)
                if candidate:
                    text = candidate
                    generated_by = f"openai:{model}"
            except Exception:
                pass
        theme = str(evolution.get("theme") or collective_state.get("dominant") or "").strip() or None
        return self._remember(StoryCue(
            cue_id=self._next_cue_id("collective", str(evolution.get("chapter") or "")),
            text=text,
            mode="collective_chapter",
            participants=participants,
            source="collective_intent",
            theme=theme,
            generated_by=generated_by,
            created_at_unix=at,
        ))

    def _openai_transport(self, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("falha de conexão com OpenAI") from exc

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        value = part["text"].strip()
                        if value:
                            return value
        raise RuntimeError("resposta OpenAI sem texto narrativo")
