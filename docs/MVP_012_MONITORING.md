# MVP-012 — central de monitoramento

O Manager passa a abrir na Visão geral e reúne o estado operacional da Live
Infinita sem exigir acesso ao shell. A tela é atualizada a cada cinco segundos.

## Indicadores

- Runtime e tempo ativo.
- Estado persistente do conector TikTok, usuário e última atividade.
- Configuração, último teste e latência da OpenAI.
- Clientes WebSocket conectados.
- Entradas, curtidas, presentes, atores e vínculos.
- Versão, sequência, entidades, período e integridade do replay.
- Atividade recente de audiência e alterações do mundo.

O endpoint `/api/manage/monitor` exige a sessão da gerência ou Bearer de
operador. Ele não devolve chaves, tokens, mensagens de erro brutas ou conteúdo
de configuração secreto.
