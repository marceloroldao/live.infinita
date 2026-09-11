# MVP-002 — Deterministic World Runtime

Objetivo: transformar o protótipo visual do MVP-001 em um mundo reconstruível por eventos e deltas.

## Fluxo

```text
Simulator
   |
   v
Event
   |
   v
Delta determinístico
   |
   v
World State N -> N+1
   |
   +----> events.jsonl
   +----> deltas.jsonl
   +----> world.json
   |
   v
WebSocket -> Renderer
```

A narrativa continua sendo consequência da mudança. Ela não é a autoridade do estado.

## Persistência

O estado operacional não fica mais dentro do checkout Git. Na instalação Ubuntu ele vive em:

```text
/var/lib/live-infinita/
├── world.json
├── events.jsonl
└── deltas.jsonl
```

Assim, atualizar `/opt/live.infinita` não deve apagar o mundo em execução.

## Identidade sequencial

Cada ação aceita recebe um contador monotônico:

```text
evt_000001 -> delta_000001
evt_000002 -> delta_000002
...
```

O evento registra a intenção de entrada. O delta registra as operações determinísticas aceitas pelo runtime.

## Hash canônico

Cada World State possui `state_hash`, SHA-256 de uma serialização JSON canônica (`sort_keys`, sem incluir o próprio campo `state_hash`). O mesmo bootstrap + mesma sequência de deltas deve gerar exatamente o mesmo hash final.

## Endpoints

```text
GET  /api/health
GET  /api/world
GET  /api/events
GET  /api/deltas
GET  /api/replay/verify
POST /api/simulate
POST /api/world/reset
WS   /ws
```

`GET /api/replay/verify` reconstrói o mundo a partir do bootstrap e reaplica todos os deltas. O teste passa somente se `current_hash == replay_hash`.

## Atualizar a VM a partir do MVP-001

No checkout autenticado:

```bash
cd ~/live.infinita
git fetch origin
git checkout mvp/deterministic-world-runtime-002
git pull
sudo bash deploy/install-ubuntu.sh
```

Depois:

```bash
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/replay/verify
```

O health esperado contém:

```json
{
  "ok": true,
  "mvp": "002",
  "version": "0.3.0",
  "replay_ok": true
}
```

## Teste manual recomendado

Com o preview aberto, execute pelo Simulator uma sequência como:

1. adicionar visitante;
2. mudar para noite;
3. apagar a fogueira;
4. mover a árvore;
5. voltar para dia.

Depois consulte:

```bash
curl http://127.0.0.1:8080/api/events
curl http://127.0.0.1:8080/api/deltas
curl http://127.0.0.1:8080/api/replay/verify
```

O último endpoint deve retornar `"ok": true` e hashes idênticos.

## Teste automatizado

Na raiz do repositório:

```bash
python3 -m unittest tests/test_mvp002_replay.py -v
```

Os testes verificam:

- replay de uma sequência de ações gera o mesmo hash do estado persistido;
- duas execuções independentes com o mesmo bootstrap e as mesmas ações chegam ao mesmo hash final.

## Critério para considerar MVP-002 validado

Executar pelo menos 100 eventos em uma VM e comprovar:

```text
100 eventos
    +
100 deltas
    +
replay desde o bootstrap
    =
mesmo state_hash final
```

Falha de hash significa divergência determinística e bloqueia o avanço para Gateway/IA/Memoria.ia.
