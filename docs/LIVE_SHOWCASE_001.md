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
                                             +--> Server Audio: OpenAI TTS + ambiente
```

## Tela Godot

- painel superior esquerdo: estado do mundo, versão, sequência, última ação, event/delta e reconciliação de entidades;
- painel superior direito: últimos eventos de audiência (`join`, `like`, `gift`), por exemplo `Fulano entrou na live`;
- faixa inferior: narrativa autoritativa do `world.narration.text`;
- o Godot não possui botões de mutação nesta versão.

## Áudio

`live-infinita-audio.service` acompanha o mesmo `/ws`, deduplica pelo `last_event.event_id`, sintetiza o texto do World State preferencialmente pela OpenAI configurada no Manager e usa `espeak-ng` como fallback. O ambiente procedural toca continuamente e sofre ducking durante a fala. A saída do programa é `udp://127.0.0.1:5500` em MPEG-TS/AAC estéreo 48 kHz.

## Instalação na VM

```bash
cd ~/live.infinita
git fetch origin
git checkout demo/live-showcase-001
git pull
sudo bash deploy/install-live-showcase.sh
```

Tela:

```text
https://live.etbra.com.br/godot/
```

## Validação durante uma Live

Em terminais separados:

```bash
journalctl -u live-infinita-tiktok -f
```

```bash
journalctl -u live-infinita-audio -f
```

```bash
curl -s http://127.0.0.1:8080/api/replay/verify
```

Critérios:

1. `join` real aparece no painel `AO VIVO` sem alterar o World State;
2. comentário/intenção aceita altera o mundo pelo pipeline existente;
3. Event/Delta aparecem no painel de construção;
4. narrativa textual muda junto com o World State;
5. Server Audio gera a fala correspondente automaticamente;
6. replay continua `ok=true`.

## Limites desta demo

- join/like/gift não são narrados individualmente para evitar poluição sonora; eles aparecem no feed visual e só afetam o mundo pelas regras/propostas já existentes;
- a OpenAI não escreve World State diretamente;
- o broadcaster final ainda deverá consumir vídeo + `udp://127.0.0.1:5500` para formar a transmissão da plataforma.
