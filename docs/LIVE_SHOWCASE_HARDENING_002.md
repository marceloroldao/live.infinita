# Live Showcase Hardening 002

## Objetivo

Reduzir dependência de validação manual na VM e preparar a Live Infinita para operar com vídeo, áudio e controle integralmente no servidor.

## Arquitetura desta baseline

```text
TikTok / fontes
      |
      v
Gateway -> AI Router -> Validator -> World State
                                  |        |
                                  |        +-> Server Audio -> UDP :5500
                                  |
                                  +-> Godot nativo -> Xvfb -> FFmpeg -> UDP :5600

UDP :5600 (vídeo) + UDP :5500 (áudio)
                 |
                 v
          Broadcaster Core
                 |
           RTMP/RTMPS futuro
```

O Broadcaster é preparado, mas permanece explicitamente desabilitado nesta fase.

## Hardening implementado

- CI com compileall, bateria unitária/API, soak test, preflight e validação shell.
- Godot validado headlessly e também por smoke test gráfico real em Xvfb.
- Server-side renderer nativo em `apps/headless-renderer/headless_renderer.py`.
- Serviço `live-infinita-renderer.service` supervisiona Xvfb + Godot + FFmpeg.
- Vídeo interno isolado em UDP loopback `:5600`.
- Áudio interno permanece em UDP loopback `:5500`.
- Broadcaster Core usa os dois buses e exige saída externa explícita.
- Unidade `live-infinita-broadcaster.service` é instalada desabilitada.
- `prepare-broadcaster.sh` força o serviço a permanecer parado após instalação.
- `--probe` do Broadcaster termina automaticamente após 5 segundos por padrão.
- Stream key é mascarada em logs.
- Browser Audio continua disponível para inspeção humana em `/godot/`, mas não faz parte do caminho do broadcast server-side.
- Godot Web suporta `?capture=1` sem controles de áudio HTML, embora o pipeline preferido no servidor seja Godot nativo.
- AudienceAggregator mantém somente janelas temporais necessárias; não cresce com a duração da Live.
- Soak test cobre 20.000 eventos de audiência e 500 commits de mundo com replay determinístico.

## Segurança operacional

World State continua sendo a única autoridade do mundo. Renderer, áudio e Broadcaster são saídas.

O Broadcaster não inicia automaticamente. O instalador falha se detectar `live-infinita-broadcaster.service` ativo nessa fase.

A stream key deve existir somente em `/etc/live-infinita/broadcaster.env`, com permissões restritas, e nunca no repositório.

## Próxima validação física

Quando for conveniente usar a VM:

1. `python3 deploy/showcase_preflight.py --host`
2. instalar `hardening/live-showcase-002`
3. confirmar Runtime, Audio e Renderer ativos
4. executar Broadcaster `--probe` por 5 s, sem saída externa
5. validar o frame/fluxo local
6. somente então configurar uma saída RTMP/RTMPS e habilitar Broadcaster

Até essa etapa, a branch permanece em draft e a baseline `demo/live-showcase-001` não é alterada.
