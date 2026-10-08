# 008EL — medição de decisões e resultados físicos na live

Foi criada uma ferramenta de leitura que liga `NOV_PATTERN_DECISION`, `NOV_PATTERN_OUTCOME` e `NOV_PATTERN_EXCLUDED` pelo identificador do contato. Ela usa os registros da sessão atual do renderer, preserva os eventos capturados para reprodução e não altera o mundo, serviços ou memórias.

## Classificações

Separa percepção, exploração, preferência local em RAM e preferência com IDs recuperados. Para preferências aprendidas, distingue mudança aplicada, coincidência com a percepção e proposta que não foi aplicada. Separa saída física concluída, falha física, exclusão e resultado não observado. Ausência de resultado não é chamada de falha nem necessariamente contato ainda pendente.

Valida mundo, contexto, lado aplicado, marcadores físicos, distância finita e fundamento da conclusão. Saída executada precisa de avanço de pelo menos 0,75 m. Registros conflitantes não são ocultados; duplicatas iguais não contam duas vezes. Preferência recuperada exige IDs válidos e concordância com a avaliação registrada. Exploração não é tratada como preferência aprendida.

O relatório é observacional: duas situações com mesma assinatura podem ter geometria diferente. Coincidir com a percepção não comprova mudança causada pela memória. Uma escolha alterada com saída concluída também não comprova vantagem sem comparação equivalente. A ferramenta mantém `performance_advantage_demonstrated: false` e não estima ganho contrafactual inexistente.

## Primeira medição

Nos 124 eventos capturados desta sessão, foram classificados 62 contatos: 25 saídas pela percepção, 23 exclusões pela percepção, nove saídas de exploração, uma exclusão de exploração, uma falha física pela percepção, duas saídas com preferência recuperada coincidente com a percepção e uma escolha alterada por preferência recuperada excluída antes da saída confirmada. Não houve linha inválida ou identidade conflitante.

Os contornos recuperados concluídos tiveram custos de 4 m e 5,9604 m. A escolha alterada continua sem resultado completo. Esses casos confirmam funcionamento da ligação entre decisão e consequência observada, mas não demonstram melhoria da memória na live.

Dez testes de contrato passaram: mudança recuperada, coincidência, exploração, censura, ausência de resultado, escopo, previsão, progresso físico, duplicata/conflito, metadados inválidos, falha física e proposta não aplicada. Fixtures sintéticas de teste nunca entram na memória de produção. O replay dos eventos capturados reproduziu as mesmas classificações.

## Uso

Execute `bash /home/etbra/measure-pattern-outcomes-008el.sh`. Não requer instalação nova do renderer nem reinício. O relatório atual fica em `/home/etbra/008el-latest-pattern-outcomes.json` e os eventos em `/home/etbra/008el-latest-pattern-events.log`. Por padrão mede desde o início da sessão atual; use `--since` para restringir a janela. Há limite de 5000 eventos: uma janela maior é rejeitada, sem produzir conclusão parcial silenciosa.

Para replay, use `python3 tools/measure_live_pattern_outcomes_008el.py --input-log docs/PATTERN_OUTCOME_EVENTS_008EL.txt`. A ferramenta pode ser executada novamente para obter uma nova coleta; nenhum monitoramento automático foi configurado.

Próxima etapa: obter escolhas alteradas com resultados completos e preparar comparação em geometrias equivalentes. A censura frequente por novos contatos merece investigação própria; não deve ser transformada artificialmente em sucesso ou erro.

Evidências: `PATTERN_OUTCOME_MEASUREMENT_008EL.json`, `PATTERN_OUTCOME_EVENTS_008EL.txt` e `PATTERN_OUTCOME_TESTS_008EL.txt`.
