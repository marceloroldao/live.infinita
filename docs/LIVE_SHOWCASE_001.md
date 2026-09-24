# Live Infinita Showcase 001

Versão de demonstração para transmissão real, mantendo autoridade do World State no runtime determinístico e usando o Godot somente como apresentação.

## Fluxo

```text
TikTok / API / Agent
        |
        +--> audience side-channel --> Godot feed "AO VIVO"
        |
        +--> Gateway -> Intent -> Validator -> Runtime
                               |
                               +--> Event + Delta + World State
                                             |
                                             +--> Godot: construção do mundo
                                             +--> Godot: narrativa textual
                                             +--> Server Audio: TTS local + ambiente local
```

## Tela Godot

- painel superior esquerdo: estado do mundo, versão, sequência, última ação, event/delta e reconciliação de entidades;
- painel superior direito: últimos eventos de audiência (`join`, `like`, `gift`), por exemplo `Fulano entrou na live`;
- faixa inferior: narrativa autoritativa do `world.narration.text`;
- o Godot não possui botões de mutação nesta versão.

## Áudio 100% local

`live-infinita-audio.service` acompanha o mesmo `/ws`, deduplica pelo `last_event.event_id` e persiste o último evento narrado para não repetir após restart/reconexão.

A voz principal é sintetizada localmente pelo Piper usando `pt_BR-faber-medium`. Se o Piper não estiver disponível, o fallback também é local via `espeak-ng` em pt-BR. A OpenAI não participa da geração de voz.

O ambiente também é 100% local: é gerado proceduralmente pelo `server_audio.py`, toca continuamente e sofre ducking durante a fala. O mixer trabalha em pacing real de blocos de 20 ms para não consumir CPU tentando produzir áudio mais rápido que o relógio.

A saída do programa é `udp://127.0.0.1:5500` em MPEG-TS/AAC estéreo 48 kHz.

A OpenAI pode continuar configurada no Manager para os componentes cognitivos da Live, mas não é usada pelo caminho de áudio.

## Instalação na VM

```bash
cd ~/live.infinita
git fetch origin
git checkout demo/live-showcase-001
git pull
sudo bash deploy/install-live-showcase.sh
```

O instalador baixa uma única vez o modelo Piper brasileiro (~63 MB), instala `piper-tts` localmente e reinicia o serviço de áudio.

Tela:

```text
https://live.etbra.com.br/godot/
```

## Verificação

```bash
systemctl status live-infinita-audio --no-pager
sudo cat /var/lib/live-infinita/audio/status.json
journalctl -u live-infinita-audio -n 50 --no-pager
```

Esperado após uma fala:

```text
tts_local=true
openai_audio_enabled=false
tts_provider=piper-local
ambient_provider=local-procedural
```

## Validação durante uma Live

Critérios:

1. `join` real aparece no painel `AO VIVO` sem alterar o World State;
2. comentário/intenção aceita altera o mundo pelo pipeline existente;
3. Event/Delta aparecem no painel de construção;
4. narrativa textual muda junto com o World State;
5. Server Audio gera a fala correspondente automaticamente com `provider=piper-local`;
6. replay continua `ok=true`.

## Limites desta demo

- join/like/gift não são narrados individualmente para evitar poluição sonora; eles aparecem no feed visual e só afetam o mundo pelas regras/propostas já existentes;
- a LLM não escreve World State diretamente;
- o broadcaster final ainda deverá consumir vídeo + `udp://127.0.0.1:5500` para formar a transmissão da plataforma.
