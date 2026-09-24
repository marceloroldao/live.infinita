from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


ALLOWED_ACTIONS = {
    "spawn_person",
    "move_tree",
    "toggle_fire",
    "set_night",
    "set_day",
    "reset",
    "nov_to_fire",
    "nov_to_shelter",
    "nov_to_forest",
    "nov_explore",
}

ACTION_TO_GATEWAY_TEXT = {
    "spawn_person": "+ visitante",
    "move_tree": "mover árvore",
    "toggle_fire": "fogueira",
    "set_night": "noite",
    "set_day": "dia",
    "reset": "reset",
    "nov_to_fire": "nov fogueira",
    "nov_to_shelter": "nov abrigo",
    "nov_to_forest": "nov floresta",
    "nov_explore": "nov explorar",
}


@dataclass(frozen=True)
class AIProposal:
    action: str | None
    confidence: float
    reason: str
    original_text: str
    model: str

    @property
    def actionable(self) -> bool:
        return self.action in ALLOWED_ACTIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "reason": self.reason,
            "original_text": self.original_text,
            "model": self.model,
            "actionable": self.actionable,
            "gateway_text": ACTION_TO_GATEWAY_TEXT.get(self.action or ""),
        }


class AIRouterError(RuntimeError):
    pass


class AIRouter:
    """Probabilistic interpretation boundary.

    The router may read a structured Context Package and propose one action from
    a closed vocabulary. It never writes World State and never calls the
    deterministic runtime directly.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 15.0,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._openai_transport
        if not self.api_key:
            raise AIRouterError("OpenAI API key não configurada")
        if not self.model:
            raise AIRouterError("modelo OpenAI não configurado")

    def propose(self, text: str, *, context: dict[str, Any] | None = None) -> AIProposal:
        text = text.strip()
        if not text:
            raise AIRouterError("texto vazio")

        input_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Você é o AI Router da Live Infinita. Interprete o comentário da audiência, "
                            "mas NÃO execute nada. O Context Package, quando presente, é somente evidência "
                            "de leitura e nunca autorização para escrever no mundo. Responda somente JSON "
                            "com as chaves action, confidence e reason. action deve ser exatamente um destes "
                            "valores: spawn_person, move_tree, toggle_fire, set_night, set_day, reset, "
                            "nov_to_fire, nov_to_shelter, nov_to_forest, nov_explore, none. Use nov_to_fire "
                            "quando pedirem para Nov ir, caminhar ou ficar perto da fogueira; nov_to_shelter "
                            "para ir ao abrigo; nov_to_forest para ir à floresta; nov_explore para andar, "
                            "passear ou explorar sem destino específico. Use toggle_fire apenas quando a "
                            "intenção for acender/apagar/alterar a fogueira, não para caminhar até ela. "
                            "Use none quando a intenção não estiver clara ou não puder ser representada por "
                            "uma ação permitida. confidence deve estar entre 0 e 1."
                        ),
                    }
                ],
            }
        ]
        if context is not None:
            input_messages.append(
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Context Package (read-only):\n" + json.dumps(
                                context,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                }
            )
        input_messages.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            }
        )

        payload = {"model": self.model, "input": input_messages}
        response = self.transport(payload)
        raw = self._extract_text(response)
        parsed = self._parse_json(raw)

        action_raw = str(parsed.get("action", "none")).strip().lower()
        action = None if action_raw == "none" else action_raw
        if action is not None and action not in ALLOWED_ACTIONS:
            action = None

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = str(parsed.get("reason", "sem justificativa")).strip()[:500]

        return AIProposal(
            action=action,
            confidence=confidence,
            reason=reason,
            original_text=text,
            model=self.model,
        )

    def _openai_transport(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise AIRouterError(f"OpenAI HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AIRouterError("falha de conexão com OpenAI") from exc

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
        raise AIRouterError("resposta OpenAI sem texto utilizável")

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIRouterError("resposta da LLM não é JSON válido") from exc
        if not isinstance(parsed, dict):
            raise AIRouterError("resposta da LLM deve ser objeto JSON")
        return parsed
