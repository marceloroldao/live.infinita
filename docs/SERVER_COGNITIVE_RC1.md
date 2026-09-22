# Server Cognitive RC1

## Purpose

Server Cognitive RC1 is the first long-running integration profile built from the Life Gate 028 cognitive-gym freeze.

It is intentionally independent of TikTok, LLMs and renderers. The first server test asks a narrower question:

> Can the authoritative world, Nov, environmental agents, sensors and Memoria.ia V2 remain alive together for repeated cycles and expose their state for inspection?

## Frozen base

Live.infinita cognitive-gym freeze:

- `af2bbe43a28f472197c1bdebffc0413aa9d9d654`

Pinned cross-repository dependencies inherited from the validated workflow:

- bit.analyze: `2192c61e514a7bb500500ab9fff63bd42940dc52`
- Memoria.ia: `45fdbe5b2404e00d40f492c2e503172a8eb22433`

## Runtime cycle

One RC1 cycle performs:

1. one distributed environmental tick;
2. synchronized multimodal sensor frames;
3. Nov autonomous decision;
4. authoritative World Runtime action commit;
5. Memoria.ia V2 learning;
6. need-state update;
7. observable status snapshot.

No LLM can write World State. TikTok and Godot are absent from this milestone.

## Service

The standard-library HTTP service is:

`apps/world-runtime/server_cognitive_rc1_service.py`

Default bind:

`127.0.0.1:8091`

Endpoints:

- `GET /health`
- `GET /api/v1/status`
- `POST /api/v1/step`
- `POST /api/v1/run?cycles=N`

The run endpoint limits one request to 1000 cycles.

## Server smoke sequence

After dependencies are available on `PYTHONPATH`:

```bash
cd ~/live.infinita/apps/world-runtime
python server_cognitive_rc1_service.py --host 127.0.0.1 --port 8091
```

From another shell:

```bash
curl -s http://127.0.0.1:8091/health
curl -s http://127.0.0.1:8091/api/v1/status
curl -s -X POST 'http://127.0.0.1:8091/api/v1/run?cycles=100'
curl -s http://127.0.0.1:8091/api/v1/status
```

## First acceptance target

The first server session should run at least 1000 cycles without TikTok, LLM or renderer authority.

Observe:

- world tick/version continue increasing;
- Water distribution changes according to World Runtime;
- Nov continues selecting only world-offered actions;
- Memoria.ia episode count grows;
- process remains responsive through `/health` and `/api/v1/status`;
- deterministic test runs remain reproducible.

Persistence across process restart is deliberately the next RC1 increment. The first increment establishes the long-running in-process integration boundary before adding durable snapshots.
