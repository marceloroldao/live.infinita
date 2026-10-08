# 008EM — produção verificada

Build bc3c580 ativo desde 2026-10-08 01:06:07 UTC (2026-10-07 22:06:07 America/Sao_Paulo). Instalador concluiu com sucesso. Renderer ativo, zero reinícios automáticos; ponte de padrões com Result=success e recibos reais de armazenamento/recuperação. Nenhum erro de script, parse ou carregamento na janela consultada. Há um aviso de inicialização ALSA sem dispositivo de áudio, seguido de fallback Dummy; isso não comprova funcionamento do áudio transmitido.

O arranque carregou 346 registros v3 anteriores, preservando a memória acumulada. A medição de contatos é uma captura delimitada da sessão, não monitoramento automático.

## Primeiro desvio aprendido com saída física concluída nesta sessão

Contato `94a08faa5356943664d303345844273a:dc3096ce8fe9810b9d309cd430499f2f:2:7`. Contexto `capsule044-height18-lookahead3-contour64-localexit-v3|nov-live-autonomous-001|local-clear-v1:255:238`. Percepção escolheria +1; a recomendação recuperada aplicou -1. Duas observações recuperadas para cada lado; scores -1=1.1666667 e +1=1.6666667, margem observada 0.5 acima do mínimo 0.3333333. Saída efetivamente executada: 4.000016 m, projeção de saída 0.999897 m.

A captura contém 109 eventos, 55 contatos, zero eventos inválidos, zero identidades conflitantes e zero resultados sem decisão. Classificações: {"perception_unresolved": 1, "perception_excluded": 9, "exploration_excluded": 3, "exploration_completed": 10, "perception_completed": 29, "core_same_completed": 1, "core_same_excluded": 1, "core_changed_completed": 1}.

Isso demonstra influência da memória recuperada em uma escolha aplicada, com conclusão física associada ao mesmo contato. Não demonstra vantagem causal de desempenho: falta comparação pareada no mesmo cenário sem memória. Duas chegadas e zero bloqueios/resgates no status arquivado não podem ser atribuídos exclusivamente a esse desvio. As exclusões observed_side_end agora distinguem a mudança de enquadramento da saída física; a política de movimento não foi alterada.

Próxima validação: comparação pareada do mesmo cenário e estado físico com/sem recomendação, seguida de cenário alterado para medir adaptação e custo de erros.
