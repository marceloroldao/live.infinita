# Requisitos Arquiteturais — Live Infinita

Este documento registra requisitos obrigatórios para impedir regressões arquiteturais durante a implementação.

## REQ-001 — Autoridade do estado
Somente o World Runtime pode aceitar uma alteração de mundo. LLM, renderer, TTS, painel web e clientes externos não podem escrever diretamente no World State.

## REQ-002 — Persistência desacoplada
O Runtime deve depender de uma interface `WorldStore`. Devem existir pelo menos `LocalWorldStore` e `MemoriaIaWorldStore` como implementações intercambiáveis.

## REQ-003 — MVP não bloqueado pela Memoria.ia
A implementação do MVP-001 deve poder avançar e ser testada com `LocalWorldStore`. A evolução da Memoria.ia para OFF.IA, memoria.ia.server e Live Infinita acontece em paralelo.

## REQ-004 — Memoria.ia genérica
A integração não deve introduzir conceitos específicos de Godot, OBS ou jogo no core da Memoria.ia. O caminho desejado é primitives genéricas, Memory Spaces e adapters de domínio.

## REQ-005 — Renderer principal
Godot 4 é o renderer principal do mundo. GDScript é a linguagem padrão da camada visual. O MVP inicia em 2D/2.5D procedural.

## REQ-006 — Renderer não é fonte de verdade
Godot recebe `WorldSnapshot` e `WorldDelta`. Objetos visuais devem ser indexados por `entity_id`. Recarregar ou reiniciar o renderer não pode alterar o estado persistente.

## REQ-007 — Crescimento por deltas
O cenário cresce incrementalmente. Novas entidades ou mudanças devem preservar o estado anterior. `World(t+1) = World(t) + Delta(t)`.

## REQ-008 — Narração inicial simples
O sistema começa com uma única voz de narrador. Personagens não têm voz individual obrigatória no MVP.

## REQ-009 — TTS barato/local
Piper local é a baseline de TTS. TTS em nuvem é opcional e deve ficar atrás de uma interface substituível.

## REQ-010 — Sem dependência paga no MVP-001
Nenhuma API paga deve ser obrigatória para executar os testes de aceite do MVP-001. Simulator, templates de narração, Piper e LocalWorldStore devem permitir um ciclo completo.

## REQ-011 — Idle eficiente
Sem interação, animações locais podem continuar, mas não devem provocar chamadas obrigatórias de LLM, novos deltas ou novas versões sem mudança real de estado.

## REQ-012 — Admin Web remoto
O servidor deve expor um painel web para observabilidade remota com estado, versão, eventos, deltas, métricas, erros, TTS, renderer e preview.

## REQ-013 — Preview do servidor
O painel administrativo deve ter preview leve do mundo. O preview pode usar baixa resolução e baixa taxa de quadros e nunca participa da autoridade do estado.

## REQ-014 — Linux headless para backend
Gateway, Runtime, Memoria.ia adapter, stores, TTS e APIs de administração devem poder rodar sem GNOME/KDE. A necessidade gráfica deve ficar isolada no renderer/stream-output.

## REQ-015 — Saída de Live substituível
A primeira saída pode ser `Godot nativo -> OBS`. O desenho deve permitir migrar para Spout, NDI, FFmpeg, GStreamer, RTMP ou SRT sem alterar o domínio.

## REQ-016 — Contratos estáveis
As mensagens `LiveEvent`, `Intent`, `ProposedAction`, `WorldEvent`, `WorldDelta` e `WorldSnapshot` devem ser versionadas e validadas.

## REQ-017 — Replay determinístico
Mesmo estado-base + mesma sequência de deltas deve produzir o mesmo estado final e hash final.

## REQ-018 — Idempotência
Um `delta_id` já aplicado não pode ser aplicado novamente. Um `entity_id` persistente não pode ser duplicado por retransmissão de rede.

## REQ-019 — Single writer no MVP
No MVP-001, o World Runtime é o único escritor autoritativo e serializa alterações para reduzir complexidade de concorrência.

## REQ-020 — Observabilidade
Cada tick deve registrar identificador, latência, eventos recebidos, intenções, propostas, deltas, versão resultante, persistência e entrega ao renderer. Métricas de LLM/TTS entram quando esses componentes forem usados.

## Critério arquitetural de revisão
Uma mudança que viole qualquer requisito acima deve ser tratada como alteração arquitetural explícita, documentada antes do merge.
