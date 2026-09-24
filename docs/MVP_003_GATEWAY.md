# MVP-003 — Event Gateway + Intent/Validation Pipeline

Objetivo: desacoplar fontes externas do runtime determinístico validado no MVP-002.

Fluxo:

```text
Simulator/API -> Event Gateway -> Intent Engine -> Rule Validator -> MVP-002 Runtime -> Event/Delta -> World State
```

## Contrato de entrada

`POST /api/gateway/event`

```json
{
  "source": "simulator",
  "actor_id": "local-user",
  "kind": "text",
  "text": "noite",
  "metadata": {}
}
```

O Gateway normaliza a fonte. O Intent Engine do MVP-003 é determinístico e converte texto conhecido em uma ação candidata. O Validator rejeita fontes, ações ou confiança não autorizadas. Apenas ações aceitas chegam ao `DeterministicWorldEngine`.

O endpoint legado `POST /api/simulate` permanece funcional, mas agora passa internamente pelo mesmo pipeline.

## Testes

```bash
python3 -m unittest tests/test_mvp003_pipeline.py -v
curl http://127.0.0.1:8080/api/health
curl -X POST http://127.0.0.1:8080/api/gateway/event \
  -H 'content-type: application/json' \
  -d '{"source":"simulator","actor_id":"vm-test","kind":"text","text":"noite","metadata":{}}'
curl http://127.0.0.1:8080/api/replay/verify
```

Critério mínimo: evento reconhecido deve ser aceito e persistido como `validated_action`; evento desconhecido deve ser rejeitado sem alterar o World State; replay deve continuar produzindo o mesmo hash.

TikTok, YouTube e LLM ainda não são conectados neste MVP. As fontes aparecem apenas no contrato permitido para provar que o runtime não depende da origem física do evento.
