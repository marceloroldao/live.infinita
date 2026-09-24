# Server Audio 001 — narrador e ambiente no servidor

## Objetivo
Remover do Godot a responsabilidade de gerar ou decidir áudio. O servidor acompanha o World State e produz uma trilha contínua de programa, pronta para ser consumida pelo broadcaster FFmpeg.

## Fluxo

`TikTok/API/Agent -> Gateway -> Validator -> Runtime -> World State -> Server Audio -> TTS + ambiente -> mixer -> AAC/UDP`

Saída local inicial:

`udp://127.0.0.1:5500`

Formato: MPEG-TS contendo AAC estéreo 48 kHz / 128 kbps.

## Regras
- Godot continua renderer somente leitura;
- texto de `world.narration.text` é a fonte da fala;
- `last_event.event_id` é usado para deduplicar narração;
- TTS primário usa a chave OpenAI já persistida pelo Integration Manager;
- fallback local usa `espeak-ng`;
- áudio ambiente procedural fica sempre ativo;
- durante narração o ambiente sofre ducking;
- o serviço não escreve World State, Event ou Delta;
- falha do serviço de áudio não para o Runtime determinístico.

## Arquivos
- `apps/audio-service/server_audio.py`
- `deploy/live-infinita-audio.service`
- `deploy/install-server-audio.sh`

Dados operacionais:
- `/var/lib/live-infinita/audio/status.json`
- `/var/lib/live-infinita/audio/narration-events.jsonl`
- `/var/lib/live-infinita/audio/tts/`

## Instalação

```bash
cd ~/live.infinita
git fetch origin
git checkout feature/server-audio-001
git pull
sudo bash deploy/install-server-audio.sh
```

## Observação
A saída UDP é deliberadamente local. No próximo estágio o broadcaster FFmpeg consumirá o vídeo da composição visual e este bus de áudio, enviando o programa final ao destino da Live. Nenhuma credencial de streaming pertence ao serviço de áudio.
