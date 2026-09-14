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
    "forest": "a floresta",
    "river": "o rio",
    "village": "a vila",
    "field": "o campo aberto",
}


class NarrationSuppressed(RuntimeError):
    """Expected presentation-only suppression, never a runtime failure."""


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
    """Interaction-only conversational host for Live Infinita.

    Despite the legacy class name, this component no longer narrates the autonomous
    story or keeps a narration history. It speaks only in response to audience
    interaction. Scene intent is extracted independently by CollectiveIntentEngine.
    """

    def __init__(
        self,
        *,
        window_seconds: float | None = None,
        collective_min_interval_seconds: float | None = None,
        timeout_seconds: float = 12.0,
        transport: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> None:
        self.window_seconds = float(
            window_seconds
            if window_seconds is not None
            else os.getenv("LIVE_INFINITA_STORY_WINDOW_SECONDS", "90")
        )
        self.collective_min_interval_seconds = float(
            collective_min_interval_seconds
            if collective_min_interval_seconds is not None
            else os.getenv("LIVE_INFINITA_STORY_COLLECTIVE_MIN_INTERVAL_SECONDS", "8")
        )
        self.timeout_seconds = float(timeout_seconds)
        self.comments: deque[dict[str, Any]] = deque(maxlen=64)
        self.transport = transport or self._openai_transport
        self.sequence = 0
        self.last_collective_cue_at = -1.0e18

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

    @staticmethod
    def _world_context(world: dict[str, Any]) -> dict[str, Any]:
        environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
        return {
            "world_id": world.get("world_id"),
            "sequence": world.get("sequence"),
            "period": environment.get("period"),
            "weather": environment.get("weather"),
            "biome": environment.get("biome"),
            "region_id": environment.get("region_id"),
            "region_label": environment.get("region_label"),
        }

    @staticmethod
    def _collective_context(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "dominant": state.get("dominant"),
            "dominance": state.get("dominance"),
            "contributors": state.get("contributors"),
            "comment_signals": state.get("comment_signals"),
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
        direction = THEME_LABELS.get(theme or "")
        if participants <= 1:
            name = self._display_name(comment)
            if direction:
                return "individual", (
                    f"{name}, ouvi você. {direction.capitalize()} já apareceu como uma direção possível do cenário. "
                    "Continua falando comigo — quero entender onde vocês querem levar este mundo."
                )
            return "individual", (
                f"{name}, ouvi sua pergunta. Estou aqui para conversar com você e acompanhar o que chama sua atenção."
            )
        if direction:
            return "collective", (
                f"Estou ouvindo o grupo: {direction} está ganhando força. "
                "Quero ver se vocês realmente querem levar o cenário para lá ou se outra ideia vai vencer."
            )
        return "collective", (
            "Tem várias ideias aparecendo ao mesmo tempo. Continuem falando; vou responder ao que surgir e observar qual direção ganha força."
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
            "Há uma única pessoa ativa: responda diretamente a ela pelo nome quando o nome estiver disponível."
            if mode == "individual"
            else (
                "Há várias pessoas ativas: responda à pergunta ou ideia mais recente, mas considere também as vozes recentes. "
                "Não tente responder cada comentário separadamente e não cite métricas."
            )
        )
        return (
            "Você é o anfitrião conversacional da Live Infinita. Não é narrador da história. "
            "Sua função é conversar com a audiência somente quando alguém interage. "
            "Responda qualquer pergunta que puder responder, inclusive perguntas gerais que não sejam sobre o mundo virtual. "
            "Quando a pergunta for sobre o cenário atual, use apenas os fatos presentes no contexto; não invente estado do mundo. "
            "Fale em português do Brasil, normalmente em 1 a 3 frases curtas, naturais e vivas. "
            f"{audience_rule} "
            "Mantenha as pessoas curiosas e participando, mas sem forçar suspense, sem transformar toda resposta em conto e sem fingir mistério. "
            "Quando for natural, termine com uma pergunta curta ou provocação ligada ao assunto para incentivar nova interação. "
            "A intenção de cenário já é extraída por outro componente: você pode reconhecer preferências da audiência, mas não execute mudanças e não diga que uma mudança ocorreu antes de ela ocorrer. "
            "Nunca mencione API, JSON, score, modelo, comando, pipeline, World State ou termos internos. "
            "Não use listas, títulos ou emojis, a menos que a própria pergunta peça isso."
        )

    def _render_openai(self, *, api_key: str, model: str, mode: str, payload: dict[str, Any]) -> str:
        request_payload = {
            "model": model,
            "max_output_tokens": 220,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": self._system_prompt(mode)}]},
                {
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "Contexto somente-leitura da interação:\n" + json.dumps(
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
        return " ".join(self._extract_text(response).split())[:800]

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
        if participants > 1 and at - self.last_collective_cue_at < self.collective_min_interval_seconds:
            raise NarrationSuppressed("collective comments are being coalesced")

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

        if mode == "collective":
            self.last_collective_cue_at = at
        theme = str(collective_state.get("dominant") or "").strip() or None
        return StoryCue(
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
        """Compatibility hook: world evolution itself must never produce speech."""
        at = float(now if now is not None else time.time())
        return StoryCue(
            cue_id=self._next_cue_id("silent-evolution", str(evolution.get("chapter") or "")),
            text="",
            mode="silent",
            participants=max(0, int(evolution.get("contributors") or 0)),
            source="collective_intent",
            theme=str(evolution.get("theme") or "").strip() or None,
            generated_by="suppressed",
            created_at_unix=at,
        )

    def _openai_transport(self, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
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
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        return ""
