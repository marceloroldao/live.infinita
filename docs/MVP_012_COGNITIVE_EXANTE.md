# MVP-012 — Cognitive Shadow: previsão ex ante de um tick (baseline)

## Objetivo

Separar um prognóstico emitido **antes** do tick autoritativo da correspondência
estrutural escolhida **depois** do tick. Esta baseline observa se a Nov se
aproxima do alvo estático mais próximo, não prediz a ação que ela escolherá.

O ShadowWorldTickRunner continua estritamente passivo: lê o World State e o
FileRegionColdStore, observa o tick autoritativo e escreve somente no JSONL
memoria-v2-shadow.jsonl. Não cria propostas ou planos, não escreve o mundo e
nunca concede selection_authority.

## Contrato

begin_tick congela exante_forecast e a proveniência:

- forecast_schema=cognitive_exante_direction_v1;
- predictor_id=nearest-target-continuity-baseline-v1;
- selection_phase=pre_tick, horizon_ticks=1, frame, versão e sequência;
- alvo único mais próximo dentre os alvos disponíveis, desempate por abstenção,
  deduplicando ações que apontam para o mesmo alvo;
- posição e região congeladas do alvo e distância de partida;
- predicts_action=false; action/candidate_id nulos.

Se há observação válida de risco e necessidades, registra projeção conservadora
de pressão de necessidades por um tick usando NpcCounterfactualSimulator.
A projeção não supõe satisfação, não é previsão de escolha, não alimenta a
decisão e não é verdade do World State.

complete_tick compara o forecast congelado com o resultado observado:

- hit: deslocamento reduziu a distância ao alvo congelado;
- miss: deslocamento aumentou a distância ao alvo congelado;
- not_evaluable: sem movimento, deslocamento lateral, alvo alterado,
  desaparecido ou posições inválidas;
- abstained: nenhum alvo válido, empate ou já está no alvo.

A taxa exante_directional_alignment_rate usa só hit + miss como denominador.
Não é acurácia de seleção de ações nem aprendizado da Memoria.ia.
best_candidate post hoc e exact_match_rate continuam separados.

O sumário distingue exante_forecasts (tentativas com registro),
exante_issued, exante_evaluated, exante_directional_aligned,
exante_directional_misaligned, exante_forecast_abstentions e
exante_not_evaluable. O campo compatível exante_abstained agrega os dois
últimos. Registros legados não entram no denominador.

## Gates e rollout

- Unitário: previsão pré-tick congelada, desacordo com pós-tick, alvo móvel,
  imobilidade, deslocamento lateral, empate, determinismo, JSONL legado e
  ausência de autoridade de escrita.
- Suite completa na virtualenv do projeto e GitHub Actions.
- Não alterar flags ou conceder autoridade cognitiva neste MVP.
- Implantar somente após CI e replay; preservar histórico em append-only.

## Próximo incremento

Comparar a projeção de pressão de necessidades com outcomes reais em horizonte
definido e testar o modelo causal com contexto e cronograma pré-tick congelados.
Só chamar de aprendizado quando houver evidência longitudinal recuperável e
baseline comparativa.
