# OBS Preview 001 — recepção segura do programa da Live.infinita

## Objetivo

Permitir que o OBS Studio receba exatamente o programa produzido no servidor (Godot + Program Audio) sem habilitar TikTok, YouTube ou qualquer outro destino externo.

## Fluxo

```text
Godot -> UDP :5600 ---+
                       +-> Broadcaster/FFmpeg -> SRT -> OBS Studio
Audio -> UDP :5500 ---+
```

O OBS é somente receptor/monitor nesta etapa. O World State continua autoritativo no Runtime.

## Servidor

Defina explicitamente um destino SRT para a máquina que executa o OBS:

```bash
LIVE_INFINITA_STREAM_OUTPUT='srt://IP_DO_OBS:9000?mode=caller&latency=200000'
python3 apps/broadcaster/broadcaster.py --dry-run
```

Quando o destino começa com `srt://`, o Broadcaster usa MPEG-TS automaticamente em vez de FLV.

Antes disso, valide vídeo e áudio sem rede externa:

```bash
python3 apps/broadcaster/broadcaster.py --probe
```

## OBS Studio

Crie uma fonte **Media Source / Fonte de mídia**, desative arquivo local e use como entrada:

```text
srt://0.0.0.0:9000?mode=listener&latency=200000
```

A porta UDP 9000 deve ser permitida somente entre o servidor Live.infinita e a máquina do OBS.

## Segurança

- O serviço `live-infinita-broadcaster.service` permanece desabilitado por padrão.
- Não configure RTMP/RTMPS do TikTok nesta etapa.
- O teste SRT exige configuração explícita de `LIVE_INFINITA_STREAM_OUTPUT`.
- `--probe` continua descartando a saída e não transmite.
- Nenhuma stream key é necessária para o preview OBS.

## Gate de aceite

1. CI verde.
2. `--probe` termina com código 0.
3. OBS recebe vídeo 720x1280 a 30 FPS.
4. OBS recebe áudio AAC 48 kHz estéreo.
5. Interromper o Broadcaster encerra o fluxo sem alterar World State.
