# Broadcaster 001 — saída final sem autoridade sobre o mundo

## Objetivo

Preparar a camada que, no futuro, substituirá a captura manual de janela como caminho principal de transmissão. O Broadcaster recebe **vídeo já renderizado** e o **Program Audio local**, codifica o programa e envia ao endpoint da plataforma.

Ele não interpreta comentários, não altera World State e não conhece regras do mundo.

## Fluxo

```text
World State -> Godot/renderer -> video input ----+
                                                  +-> Broadcaster/FFmpeg -> plataforma
World State -> Server Audio -> UDP :5500 --------+
```

## Arquivo

`apps/broadcaster/broadcaster.py`

## Variáveis

- `LIVE_INFINITA_VIDEO_INPUT`: entrada de vídeo local. Ainda não é fixada nesta etapa; será definida pelo adaptador de captura server-side.
- `LIVE_INFINITA_AUDIO_INPUT`: padrão `udp://127.0.0.1:5500?...`.
- `LIVE_INFINITA_STREAM_OUTPUT`: URL RTMP/RTMPS completa fornecida pela plataforma.
- `LIVE_INFINITA_STREAM_WIDTH`: padrão 1280.
- `LIVE_INFINITA_STREAM_HEIGHT`: padrão 720.
- `LIVE_INFINITA_STREAM_FPS`: padrão 30.
- `LIVE_INFINITA_VIDEO_BITRATE_KBPS`: padrão 3500.
- `LIVE_INFINITA_AUDIO_BITRATE_KBPS`: padrão 128.

## Segurança operacional

A URL real de saída nunca é impressa integralmente: o componente final do caminho e query string são mascarados. O Broadcaster não persiste a stream key e não a compartilha com Runtime, Godot ou áudio.

### Dry-run

Valida configuração e gera o comando FFmpeg sem iniciar transmissão:

```bash
python3 apps/broadcaster/broadcaster.py --dry-run
```

### Probe

Valida as entradas e codificação descartando a saída; não usa endpoint de transmissão:

```bash
python3 apps/broadcaster/broadcaster.py --probe
```

## Decisão desta fase

Não instalar serviço systemd nem ativar saída externa antes de existir um adaptador de vídeo server-side validado. Isso evita que uma configuração parcial tente transmitir ou reinicie continuamente.

O próximo passo desta trilha é produzir o vídeo no servidor de forma determinística, provavelmente por um browser/renderer headless isolado, e entregar esse vídeo ao Broadcaster como uma fonte local. O Broadcaster permanece independente dessa escolha.
