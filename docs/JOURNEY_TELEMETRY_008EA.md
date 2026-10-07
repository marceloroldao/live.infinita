# 008EA — Registro das tentativas físicas de navegação

Cada identidade de objetivo possui um início e, quando seu encerramento é observado, um resultado. O renderizador nativo publica `NOV_JOURNEY_ATTEMPT` seguido de JSON no journal. Não somar esses eventos a `NOV_JOURNEY_COMPLETE`, mantido por compatibilidade.

Campos: identidade do objetivo e mundo, ponto inicial e atual, destino, distância inicial e restante, distância física acumulada, início/fim no relógio civil, duração pelo relógio monotônico do processo, bloqueios e passos concluídos/causais por tentativa. A duração permanece correta se o relógio civil for corrigido. São metros no plano XZ, como na qualidade existente. A duração é tempo real de processo, inclui intervalos sem movimento e não é tempo lógico do mundo.

Resultados: `arrived`, `stuck_recovery`, `goal_changed`, `world_changed`, `goal_idle_timeout`, `goal_hard_timeout`, `goal_ended`, `search_intent_changed`, `feed_unavailable`, `renderer_shutdown` ou `interrupted` para chamadas genéricas. A expiração encerra a identidade anterior antes da nova tentativa. O retorno ao início não aumenta a distância nem gera chegada.

Qualidade e promoção continuam recebendo somente jornadas físicas completas elegíveis. Os registros novos têm `learning_evidence=false` e `world_write_authority=false`. Passo causal registra mudança de escolha frente à alternativa calculada; não demonstra vantagem de resultado.

O estado existente `user://nov-learning-status-008df.json` recebe `active_attempt` e até 32 resultados recentes, mantendo schema e contadores do painel. Somente o renderizador nativo publica estado e os novos eventos; Web e testes offline não os publicam. O histórico completo depende da retenção do journal. Não há cópia em World State ou Memoria.ia.

Limite: desligamento abrupto ou falha do processo pode deixar um início sem término. Uma análise deve marcá-lo como censurado/desconhecido, nunca inventar sucesso, duração final ou motivo de interrupção. `_exit_tree` registra encerramentos normais quando executado. Os resultados recentes são por sessão, sem restauração após reinício.

Instalação: `sudo bash /home/etbra/apply-journey-telemetry-008ea-root.sh`. Exige contorno 008DZ instalado, valida exportação, faz backup, atualiza quatro scripts nativos e a prévia Web e verifica serviços/build. Preserva histórico privado de memória e animais. O reinício pode interromper uma busca ativa pelo mecanismo existente. A release v0.1.0 permanece preservada.

Validação: teste determinístico cobre correção regressiva do relógio civil, abortos repetidos, mudança de objetivo/mundo, chegada física, expiração por inatividade/tempo máximo, histórico limitado e preservação da qualidade. A suíte completa verifica movimento, câmera, colisões, painel, encontros e buscas.
