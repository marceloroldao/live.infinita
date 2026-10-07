# 008EB — Auditoria das tentativas de caminhada

Ferramenta somente de leitura: `python3 /home/etbra/live.infinita/tools/audit_journey_attempts_008eb.py`. Por padrão consulta as últimas duas horas do journal do renderizador, com limite de 10.000 linhas. `--since '2026-10-07 17:11:03 UTC'` seleciona outra janela; `--file arquivo.txt` aceita texto de `journalctl -o cat`. Não modifica objetivos, física, serviços, memória ou World State e não exige novo instalador.

Só os eventos `NOV_JOURNEY_ATTEMPT` com schema v1 entram na análise. O par é identificado por mundo e objetivo; todos os metadados de início precisam coincidir. Campos ausentes, números não finitos, autoridade inesperada, contadores inválidos, divergência entre duração e relógio monotônico, chegada distante do objetivo e duplicatas conflitantes interrompem a análise com erro, sem apresentar resumo parcial. Duplicatas idênticas são ignoradas.

Resultados encerrados com início presente entram nas médias e na contagem por motivo. Inícios sem término ficam em `open_or_censored`: podem estar em andamento, ter sido interrompidos abruptamente ou ter perdido seu encerramento no recorte. Não contam como falhas. Encerramentos cujo início ficou fora da janela são listados separadamente e excluídos das métricas pareadas. O limite de linhas também pode cortar o início de uma tentativa.

A fração de chegadas tem denominador explícito: somente tentativas com início e encerramento no conjunto. Não é taxa sobre todos os inícios nem estimativa de sobrevivência. As médias separam chegadas e interrupções; incluem distância física planar e duração real monotônica. A correção do relógio civil não muda essa duração. O schema 008EA pode capturar o timestamp final poucos milissegundos depois do snapshot; tolerância de 5 ms é aceita.

Os testes cobrem chegada versus interrupção, registros sem par, duplicatas idênticas/conflitantes, metadados divergentes, valores inválidos, correção regressiva do relógio civil, limite de chegada, autoridade, ausência de dados e limites de tamanho. Sete testes passaram.

Primeira aplicação real: desde 17:11:03 UTC em 7 de outubro de 2026, foram observados três inícios, duas chegadas e uma tentativa sem encerramento na coleta. As duas jornadas concluídas totalizaram 1.503,566 m, com duração média de 191,649 s. A amostra não demonstra vantagem causal da memória. Os registros e a hora exata da coleta estão em JOURNEY_ATTEMPT_AUDIT_RESULT_008EB.json.

Próximo uso: coletar amostras mais longas e comparar objetivos/condições equivalentes, preservando tentativas interrompidas e registros censurados. Não há comparação causal entre versões nesta ferramenta.
