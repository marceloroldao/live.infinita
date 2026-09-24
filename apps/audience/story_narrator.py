from __future__ import annotations

import json
import os
import re
import time
import unicodedata
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
        self.last_generation_error: str | None = None
        self.last_generation_source = "none"

    @staticmethod
    def _normalize(text: str) -> str:
        value = unicodedata.normalize("NFKD", str(text or "").lower())
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(value.split())

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

    def _display_name(self, row: dict[str, Any]) -> str | None:
        value = str(row.get("display_name") or "").strip()
        if not value:
            value = str(row.get("actor_id") or "").strip()
        if not value or value.lower() in {"anonymous", "visitante"}:
            return None
        normalized = re.sub(r"[^a-z0-9]+", "", self._normalize(value))
        # The broadcaster may post from the channel account itself. Saying
        # "Live Infinita, ..." aloud makes the host sound like a bot reading its
        # own brand name as a viewer, so treat those labels as self-identifiers.
        if normalized in {"liveinfinita", "liveinfinitabr", "liveinfinitatv"}:
            return None
        return value[:60]

    @staticmethod
    def _starts_like_greeting(normalized: str) -> bool:
        return bool(re.match(r"^(oi|ola|opa|e ai|eae|bom dia|boa tarde|boa noite)\b", normalized))

    @staticmethod
    def _looks_like_thanks(normalized: str) -> bool:
        return any(term in normalized for term in ("obrigado", "obrigada", "valeu", "brigado", "brigada", "tmj"))

    @staticmethod
    def _asks_about_live(normalized: str) -> bool:
        patterns = (
            "que live e essa",
            "o que e live infinita",
            "o que e a live infinita",
            "como funciona essa live",
            "como funciona a live",
            "quem e voce",
            "quem e vc",
        )
        return any(pattern in normalized for pattern in patterns)

    def _fallback_interaction(
        self,
        *,
        comment: dict[str, Any],
        active: dict[str, Any],
        collective_state: dict[str, Any],
    ) -> tuple[str, str]:
        """Natural local safety net used only when the conversational model fails."""
        participants = int(active.get("participants", 0))
        raw_text = str(comment.get("text") or "").strip()
        normalized = self._normalize(raw_text)
        name = self._display_name(comment)
        theme = str(collective_state.get("dominant") or "").strip() or None
        direction = THEME_LABELS.get(theme or "")

        if participants > 1:
            if direction:
                options = (
                    f"Olha só, o papo de vocês está puxando para {direction}. Vamos ver se essa ideia segura a liderança.",
                    f"Vocês estão convergindo em {direction}. Se continuar assim, isso pode acabar aparecendo no mundo.",
                    f"Tem uma direção ficando clara por aqui: {direction}. Mas ainda dá para virar o jogo.",
                )
            else:
                options = (
                    "O chat está bem dividido agora. Quero ver qual ideia vai começar a se repetir de verdade.",
                    "Tem bastante coisa diferente vindo do chat. Continuem, porque ainda não apareceu uma direção dominante.",
                    "Boa, agora ficou interessante: tem várias ideias concorrendo ao mesmo tempo.",
                )
            return "collective", options[self.sequence % len(options)]

        prefix = f"{name}, " if name else ""
        if self._asks_about_live(normalized):
            return "individual", (
                f"{prefix}essa é a Live Infinita: eu converso com o chat enquanto o mundo virtual continua rodando, "
                "e as intenções que mais aparecem por aqui podem mudar o cenário."
            )
        if self._starts_like_greeting(normalized):
            options = (
                f"{prefix}opa! Bom te ver por aqui.",
                f"{prefix}e aí! Chegou numa hora boa.",
                f"{prefix}fala! Bem-vindo por aqui.",
            )
            return "individual", options[self.sequence % len(options)]
        if self._looks_like_thanks(normalized):
            options = (
                f"{prefix}tamo junto!",
                f"{prefix}valeu você por participar.",
                f"{prefix}boa! É isso aí.",
            )
            return "individual", options[self.sequence % len(options)]
        if direction:
            options = (
                f"{prefix}boa, {direction} entrou forte no radar do chat. Se essa ideia continuar aparecendo, o cenário pode ir nessa direção.",
                f"{prefix}peguei a ideia de {direction}. Agora quero ver se mais gente embarca junto.",
                f"{prefix}{direction.capitalize()} está começando a ganhar espaço por aqui. Ainda não está decidido, mas já chamou atenção.",
            )
            return "individual", options[self.sequence % len(options)]
        if raw_text.endswith("?"):
            options = (
                f"{prefix}essa é boa. Vou no ponto, sem enrolar — se o sistema de resposta falhar, a conversa continua daqui.",
                f"{prefix}boa pergunta. Não quero te devolver uma frase pronta; quero responder isso direito.",
                f"{prefix}essa merece resposta de verdade, não texto automático. Segura comigo um instante.",
            )
            return "individual", options[self.sequence % len(options)]
        options = (
            f"{prefix}boa, peguei a ideia.",
            f"{prefix}entendi. Isso pode render por aqui.",
            f"{prefix}legal — vamos ver onde esse papo leva.",
        )
        return "individual", options[self.sequence % len(options)]

    def _next_cue_id(self, prefix: str, source_event_id: str | None = None) -> str:
        self.sequence += 1
        suffix = str(source_event_id or "").strip().replace(" ", "-")[:80]
        if suffix:
            return f"{prefix}:{suffix}:{self.sequence}"
        return f"{prefix}:{int(time.time() * 1000)}:{self.sequence}"

    @staticmethod
    def _system_prompt(mode: str) -> str:
        audience_rule = (
            "Há uma única pessoa ativa: converse diretamente com ela. Use o nome só quando soar espontâneo; não repita o nome em toda resposta."
            if mode == "individual"
            else (
                "Há várias pessoas ativas: aja como apresentador lendo um chat movimentado. Responda à fala mais recente e, quando fizer sentido, "
                "costure rapidamente uma tendência que apareceu nas falas recentes. Não responda comentário por comentário e não cite métricas."
            )
        )
        return (
            "Você apresenta a Live Infinita ao vivo. Soe como um apresentador humano de live lendo o chat em tempo real, e não como assistente virtual, "
            "SAC, tutorial, narrador de RPG ou mensagem institucional. "
            "Responda primeiro ao conteúdo concreto que a pessoa acabou de escrever. Se for uma pergunta factual e você souber, dê a resposta diretamente. "
            "Se for opinião, brincadeira, provocação ou comentário, reaja de forma espontânea e breve. "
            "Você pode responder perguntas gerais que não tenham relação nenhuma com o mundo virtual. "
            "Quando a pergunta for sobre o cenário atual, use apenas fatos presentes no contexto e não invente estado do mundo. "
            "Fale em português do Brasil, normalmente em 1 a 3 frases curtas, próprias para serem ditas em voz alta. Varie a abertura e o ritmo das respostas. "
            f"{audience_rule} "
            "Pode usar expressões naturais como 'boa', 'olha só', 'essa é boa', 'e aí', 'sim', 'não', 'depende' ou simplesmente começar pela resposta, "
            "mas não transforme nenhuma dessas expressões em bordão repetitivo. "
            "Não comece respostas dizendo 'Live Infinita'. Não diga 'ouvi sua pergunta', 'estou aqui para responder', 'estou aqui para conversar', "
            "'acompanhar o que chama sua atenção' ou frases equivalentes de atendimento. Não explique sua função a menos que perguntem sobre a própria live. "
            "Não termine toda resposta com uma pergunta. Quando houver um gancho realmente bom, convide o chat de forma curta e orgânica. "
            "A intenção de cenário é extraída por outro componente: reconheça naturalmente ideias sobre floresta, rio, vila ou campo quando surgirem, "
            "mas não fale em voto, score, algoritmo ou consenso e não afirme que o mundo mudou antes da mudança acontecer. "
            "Mantenha energia de apresentador, sem exagerar em entusiasmo e sem inventar suspense. "
            "Nunca mencione API, JSON, modelo, comando, pipeline, World State ou termos internos. "
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
        self.last_generation_error = None
        self.last_generation_source = "fallback"
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
                    self.last_generation_source = generated_by
                else:
                    self.last_generation_error = "empty_response"
            except Exception as exc:
                self.last_generation_error = f"{type(exc).__name__}: {exc}"[:240]
                print(
                    f"[presenter] conversational model unavailable; using natural fallback "
                    f"({self.last_generation_error})",
                    flush=True,
                )
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
