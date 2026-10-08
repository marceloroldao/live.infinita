# 008ER — produção verificada

Build 5e3ef78 publicado; instalador concluiu com 008ER_OK. Fonte pública consultada confirma a versão e capacidade de janelas adaptativas. Código nativo de padrões e coletor coincide byte a byte com o checkout. Estado nativo confirma cost_shift_enabled=true. Renderer ativo, sem reinícios automáticos, ponte com Result=success e timer ativo. Sem erros de script, parse ou carregamento na janela consultada.

O arranque carregou 512 registros locais v3 existentes. O status recente também mostra 512 registros recuperados; esses conjuntos podem se sobrepor e não devem ser somados. 512 é o limite de cada janela de registros, não o total histórico do núcleo. Os recibos da ponte continuam confirmando novos armazenamentos e recuperação. Não houve reset ou alteração de perfil/schema.

O renderer atual iniciou 2026-10-08 06:54:07 UTC (03:54:07 America/Sao_Paulo). O rollout registrou a promoção pública antes desse início; a captura usa o início efetivo da sessão atual, sem atribuir motivo a reinícios anteriores.

## Execução real da nova regra

A captura delimitada contém 42 eventos, 21 contatos, nenhum evento inválido, conflito de identidade ou resultado sem decisão. Classificações: {"perception_completed": 6, "exploration_completed": 7, "perception_excluded": 6, "exploration_excluded": 2}.

Contato `828a49353931acbb3ff24dc245618a61:68580ea9ae14436eccda115e4ff49b2a:2:9`, contexto `capsule044-height18-lookahead3-contour64-localexit-v3|nov-live-autonomous-001|local-clear-v1:126:126`: cost_shift_exploration baseada em aumento de custo medido e janela recente. Saída física concluída (10.000003 m, projeção 0.876485 m).

Contato `828a49353931acbb3ff24dc245618a61:68580ea9ae14436eccda115e4ff49b2a:1:2`, contexto `capsule044-height18-lookahead3-contour64-localexit-v3|nov-live-autonomous-001|local-clear-v1:255:190`: cost_shift_exploration baseada em aumento de custo medido e janela recente. Saída física concluída (4.000000 m, projeção 1.417309 m).

Ambas são exploração, com IDs de recomendação vazios, e coincidem com o lado da percepção (changed_initial_side=false). Demonstram detector e execução física funcionando em produção; não são decisões aprendidas que mudaram o lado, nem evidência de vantagem causal. Os IDs de experiências anteriores no diagnóstico explicam a janela, mas não transformam a exploração em preferência aprendida.

A comparação de desempenho de 23% permanece resultado do teste isolado 008EQ/008ER. Esta captura não compara trajetórias equivalentes com/sem regra. Um desvio concluído e uma chegada não permitem atribuir melhoria à nova política. Ainda falta medir o custo de adaptação em produção.

A observação é pontual, sem criação de timer de monitoramento. A opção pode ser desligada pelo controle root existente sem apagar memória. Próximo acompanhamento: distinguir propostas de exploração de escolhas aprendidas, verificar seus custos e resultados e confirmar a preferência posterior com dados recuperados.
