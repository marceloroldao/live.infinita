# Server Cognitive RC1

## Objetivo

Primeiro perfil long-running da Live Infinita após o Life Gate 028. O teste responde se World Runtime, Nov, natureza, bit.analyze e Memoria.ia V2 conseguem permanecer vivos juntos por longos períodos **e continuar do mesmo estado depois de restart**.

## Base congelada

- Live cognitive freeze: `af2bbe43a28f472197c1bdebffc0413aa9d9d654`
- Memoria.ia: `45fdbe5b2404e00d40f492c2e503172a8eb22433`
- bit.analyze: `2192c61e514a7bb500500ab9fff63bd42940dc52`

O branch operacional é `release/server-cognitive-rc1`.

## Autoridade operacional

Use:

`apps/server-cognitive/server.py`

Os arquivos `server_cognitive_rc1_*` dentro de `apps/world-runtime` são harnesses de integração/teste, não um segundo serviço de produção.

## Persistência RC1

Checkpoint JSON explícito, versionado e atômico.

O cold-reopen preserva:

- World State;
- Nov needs;
- episódios causais e regimes;
- memória temporal;
- higher-order context memory;
- admission-state;
- pairwise/higher-order associators;
- event-time watermark e slices pendentes;
- provenance e atividade operacional.

O CI exige que o próximo ciclo pós-restore seja igual ao próximo ciclo de uma execução ininterrupta.

## Servidor

Padrão:

`127.0.0.1:8090`

Dashboard:

`GET /`

Observabilidade:

- `GET /health`
- `GET /snapshot`
- `GET /soak`
- `GET /activity`
- `GET /debug/world`
- `GET /debug/memory`

Controle:

- `POST /step`
- `POST /run`
- `POST /checkpoint`
- `POST /flush`
- `POST /control`

## Critério para primeiro soak real

1. bootstrap das dependências passa;
2. smoke HTTP + restart passa;
3. serviço systemd inicia em autorun;
4. rodar pelo menos 1000 ciclos;
5. processo continua saudável;
6. memórias e world tick crescem sem explosão;
7. watermark permanece monotônico;
8. fluxo interno não produz late rejection;
9. checkpoint é atualizado;
10. reiniciar o serviço e confirmar que `loaded_from_checkpoint=true` e o cycle continua.

## Fora do RC1

TikTok, LLM e Godot ficam desligados. Problemas descobertos no soak real passam a orientar os próximos gates, em vez de continuar estendendo o laboratório indefinidamente.
