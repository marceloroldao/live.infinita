# 008EK — primeira influência de padrão recuperado na live

Verificado em 2026-10-08T00:26:39Z. Rollout terminou com `008EK_OK`, versão pública `ab37cde` e diagnóstico ativo. Renderer iniciado em 08/10 às 00:18:19 UTC (07/10 às 21:18:19 em São Paulo), ativo, sem reinícios automáticos e sem erros de script/parse/load encontrados nesta sessão. Os scripts nativos coincidiram com o código aplicado na verificação. O início da sessão carregou 184 fatos persistidos da versão anterior, preservando o histórico v3.

A coleta registra 213 fatos locais acumulados, 29 novos nesta sessão, 209 recuperados carregados. Último ciclo concluído da ponte: 209 confirmados e 209 em cache. Esses contadores têm tempos de atualização diferentes. Não foram abertos arquivos privados do núcleo.

O journal registra três propostas de lado preferido baseadas em evidência recuperada. Duas coincidiram com o lado padrão da percepção. Uma mudou o lado aplicado: contexto `local-clear-v1:255:127`, padrão +1, aplicado -1, origem `recovered-pattern-evidence`, duas amostras de cada lado. Escores: 1,333328 no lado -1 versus 2,161820 no lado +1; diferença 0.828491, margem exigida 0.432364. IDs recuperados do lado escolhido: `structural-event:b86ff9eda0b279b223e948dcc2a5f309ebb64c69` e `structural-event:082894f8aa2039b1b599be9dd2d0cd4323e484e5`.

A decisão foi registrada após uma ação física executada. Isso demonstra que experiências recuperadas influenciaram a escolha de navegação na live. Não é apenas presença no cache ou exploração alternada. Mudanças de exploração são identificadas separadamente e não entram nesta conclusão.

O contato alterado, número 30, foi excluído depois por `new_contact_before_executed_exit`: outro contato começou antes da saída física confirmada. Portanto, não existe resultado concluído para atribuir sucesso ou falha a essa escolha. O contato não foi transformado em sucesso nem recebeu penalidade inventada. Outros contatos mantiveram seus registros. Esta coleta não demonstra ganho de distância, tempo ou taxa de sucesso.

Motivos atuais de decisão: {"insufficient_margin": 17, "insufficient_samples": 16, "preferred_side": 3}. Há 1 chegada, 0 resgates e 0 interrupções na sessão. Próximo passo: obter decisões guiadas por padrões com resultados físicos completos, comparar condições equivalentes e investigar contatos sucessivos censurados, sem alterar a atribuição apenas para obter mais amostras.

Evidências: `PATTERN_DIAGNOSTIC_PRODUCTION_008EK.json`, `PATTERN_DIAGNOSTIC_ROLLOUT_008EK.txt` e `PATTERN_DIAGNOSTIC_BRIDGE_PRODUCTION_008EK.txt`. A verificação não reiniciou serviços nem alterou o mundo.
