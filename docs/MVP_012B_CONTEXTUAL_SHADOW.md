# MVP-012b — Estado dinâmico, previsão contextual e evidência estacionária

## Correção da fonte de necessidades

O arquivo cold store guarda as propriedades iniciais da entidade. A evolução de
necessidades é persistida separadamente pelo NpcNeedDynamics em
npc-need-state.json. O Cognitive Shadow deve receber o método get_needs da
instância autoritativa de NpcNeedDynamics, **em leitura**, antes e depois do
tick. O JSONL registra need_levels_source_before/after. O fallback para
entity_properties_bootstrap só vale quando o provider não está disponível,
com proveniência explícita; não apresentar fallback como estado dinâmico.

O projetor contrafactual ex ante do MVP-012 passa a receber os níveis dinâmicos
capturados antes do tick, sem aplicar satisfação imaginada.

## Previsão contextual v1

O novo cognitive_contextual_need_target_v1 é uma **baseline explicativa**, não
a seleção real feita por NpcNeedScheduler nem aprendizagem da Memoria.ia.
Ela utiliza, exclusivamente antes do tick:

- necessidades dinâmicas e prioridade/limiar da política existente;
- necessidade dominante por pressão ponderada;
- referências de alvos configurados na própria entidade;
- contexto ambiental (período, clima, risco, região);
- estatística prévia de NpcStrategyExperience, se disponível, apenas
  como proveniência: used_to_rank=false.

Se a necessidade dominante não tem alvo, há múltiplas referências sem ranking
fundamentado, o alvo é inválido, o agente já chegou, ou falta estado completo,
o observador **se abstém**. Não inventa destino. Para um alvo único válido,
congela sua posição/região/ID, a necessidade e a sequência pré-tick.

Depois do tick, compara a direção real com o alvo congelado: hit/miss ou
not_evaluable quando imóvel, lateral, alvo móvel/removido ou dados ausentes.
Mantém predicts_action=false, nenhuma criação de plano/proposta e
world_mutated_by_shadow=false.

## Evidência de imobilidade

stationary_observation identifica somente observações: no_target, cooldown,
already_active, plano com ausência de deslocamento ou ausência de plano
reportado. O campo causal_explanation_evaluable=false evita confundir
correlação de status com causa provada. Não modifica nem interrompe o tick.

## Gate comparativo

Registrar taxa contextual e taxa direcional anterior separadamente. Para
comparação direta, paired_evaluated conta somente ticks em que **as duas**
previsões foram emitidas e avaliadas (hit/miss), reportando os acertos
correspondentes. Denominadores diferentes não são comparáveis como ganho.

Contadores também separam legacy, fontes dinâmicas/fallback,
stationary_evidence_counts e contextual_abstention_reasons. Não atribuir
inteligência cognitiva à Nov ou ganho da Memoria.ia por um baseline passivo.

## Aceitação

- Provider de necessidade dinâmica testado com divergência das propriedades
  iniciais; before/after e deltas comprovados.
- Testes para sem alvo, múltiplos alvos, evidência de experiência,
  baseline pareada discordante, estação, abstenção e JSONL antigo.
- GitHub Actions e suíte total verdes; replay consistente antes de deploy.
- Single Writer e Mutation Gate continuam autoridades exclusivas.
- Flag de shadow continua desabilitada por padrão no template.

Próximo passo: avaliar cobertura e acurácia pareada em vários ciclos reais,
comparar predições de consequências ao horizonte de um plano e testar ranking
contextual com Memoria.ia V2, somente em shadow.
