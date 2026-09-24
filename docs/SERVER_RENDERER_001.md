# Server Renderer 001

## Objetivo

Remover Edge/Chromium/Live Studio do caminho de geração da imagem. O projeto Godot roda nativamente no servidor, conectado ao mesmo World State, e sua janela é capturada em um framebuffer X11 virtual.

## Pipeline

```text
World State :8080/ws
       |
       v
Godot 4 nativo
       |
       v
Xvfb :99 (1280x720)
       |
       v
FFmpeg x11grab
       |
       v
UDP MPEG-TS/H.264 :5600   ----+
                                 |
Server Audio -> AAC/TS :5500 ----+--> Broadcaster Core --> RTMP/RTMPS
```

## Por que Godot nativo

O projeto já funciona fora do Web export e, no modo nativo, usa diretamente `ws://127.0.0.1:8080/ws`. Isso elimina navegador, autoplay, DOM, botão de áudio, captura de janela no desktop do operador e dependência do Edge.

O Web export continua existindo para monitoramento humano em `/godot/`, mas deixa de ser requisito para produzir a transmissão.

## Segurança e isolamento

- Xvfb usa `-nolisten tcp`; não abre servidor X11 TCP.
- Video bus usa somente loopback `127.0.0.1:5600`.
- Audio bus usa somente loopback `127.0.0.1:5500`.
- Stream key só existe na configuração do Broadcaster.
- Renderer não conhece TikTok, chave RTMP nem OpenAI.
- World State continua sendo a autoridade; renderer é somente projeção.

## Serviços

`live-infinita-renderer.service` supervisiona Xvfb, Godot e FFmpeg como um único pipeline. Se um dos filhos morrer, o processo supervisor termina e o systemd reinicia a unidade inteira, evitando estado parcialmente vivo.

## Contratos de mídia

Vídeo interno:

- MPEG-TS sobre UDP loopback
- H.264 `yuv420p`
- 1280x720
- 30 fps
- GOP de 2 s
- preset `ultrafast`, tune `zerolatency`
- porta 5600

Áudio interno permanece no Server Audio:

- MPEG-TS/AAC sobre UDP loopback
- 48 kHz estéreo
- porta 5500

O Broadcaster faz a união dos dois buses e é o único componente autorizado a gerar uma saída externa.

## Estado

Implementado em `hardening/live-showcase-002`, porém ainda não ativado na VM. A validação operacional será feita somente quando conveniente, após o CI permanecer verde.
