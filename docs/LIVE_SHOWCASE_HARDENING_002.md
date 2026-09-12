# Live Showcase Hardening 002

## Objetivo

Preparar o Live Infinita para uma prova ponta a ponta de longa duração sem exigir validações manuais a cada alteração. Esta etapa não muda a autoridade do mundo: ela endurece transporte, apresentação, áudio e instalação.

## Fluxo preservado

`TikTok/API/Agent -> Gateway -> Intent/Validator -> Runtime -> World State`

Saídas somente leitura:

- `World State -> Godot Web`
- `World State -> Server Audio -> AAC/UDP -> Browser Audio Relay -> Edge/Live Studio`
- `TikTok audience -> side-channel -> Godot feed`

## Melhorias desta etapa

### CI

A workflow `.github/workflows/ci.yml` executa automaticamente:

1. instalação das dependências de teste;
2. `compileall` do código Python;
3. bateria unitária/API;
4. `bash -n` dos instaladores;
5. abertura headless do projeto Godot para validar GDScript e recursos.

### Browser Audio

O relay agora:

- verifica se FFmpeg realmente existe;
- publica no health o input UDP efetivo;
- limita o número de clientes simultâneos;
- encerra o FFmpeg filho quando o navegador desconecta;
- desabilita buffering de proxy para reduzir latência.

### Nginx

A criação da rota `/audio/` saiu do shell embutido e foi isolada em `deploy/nginx_audio_patch.py`.

O patch é:

- idempotente;
- aplicado a todos os blocos HTTP/HTTPS do hostname;
- compatível com aliases em `server_name`;
- coberto por testes;
- fail-closed em configuração estruturalmente inválida.

### TikTok

Chamadas HTTP para o Gateway não bloqueiam mais o event loop do TikTokLive. Falhas temporárias de transporte são contidas no bridge e não devem derrubar a conexão da Live por causa de um POST local que falhou.

### Godot

O renderer reconecta automaticamente ao `/ws` usando backoff exponencial. Uma interrupção do WebSocket não exige mais recarregar manualmente a página. A reconexão do áudio do navegador também impede múltiplos timers concorrentes.

### Instalação

`deploy/install-live-showcase.sh` passa a fechar todo o caminho:

1. valida Runtime;
2. instala Server Audio;
3. instala Browser Audio, patch Nginx e exporta Godot;
4. confirma Runtime, Server Audio, Browser Audio e replay determinístico.

## O que continua deliberadamente fora desta etapa

- credenciais ou RTMP do broadcaster;
- mutação direta do World State por renderer, áudio ou LLM;
- mudança da baseline validada do runtime;
- implantação automática na VM sem uma janela explícita de validação.

## Próxima validação na VM

Quando for conveniente testar no servidor, a intenção é que reste apenas uma validação operacional curta: instalar a branch, abrir `/godot/`, ativar o áudio e provar o fluxo real TikTok -> mundo -> imagem -> narração -> transmissão. Até lá, toda evolução possível deve permanecer coberta pelo CI.
