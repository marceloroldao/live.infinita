# MVP-012c — Seleção por viabilidade de necessidades urgentes

## Incidente e evidência

Na produção após PR #59, a necessidade social da Nov estava em 1.0 sem alvo
social configurado; a curiosidade estava em 1.0 com alvo ancient_tree.
A implementação autoritativa NpcAuditedReorderingNeedScheduler selecionava
somente a necessidade urgente de maior utilidade. Quando ela retornava
no_target, nenhuma alternativa urgente era considerada. Em 4.232 registros
contextuais, a baseline se absteve por no_configured_target e a comparação
pareada não tinha denominador válido.

## Alteração autoritativa

A subclasse de produção, NpcReorderingNeedScheduler, considera as necessidades
urgentes em ordem de utilidade, prioridade e nome:

1. Se uma necessidade possui plano ativo, preserva already_active e não abre
   outro plano; se está em cooldown, preserva cooldown.
2. Para cada necessidade sem destino resolvido, audita no_target com as
   referências existentes e continua para a próxima necessidade urgente.
3. Assim que encontra uma intenção viável, executa o fluxo existente
   de estratégia, eventual reordenação por horizonte, proposta e planejamento
   pelo Single Writer. No máximo um novo objetivo por NPC e tick.
4. Quando todas são inviáveis, não inventa um destino e não cria propostas.
5. Registra highest_urgent_need, skipped_unresolved_needs e
   viability_selection_schema=npc_need_viability_v1 nos resultados,
   nas propostas e no ledger de decisões. O original_need continua sendo
   a necessidade realmente escolhida antes de uma eventual reordenação
   de horizonte; o histórico de no_target é mantido por necessidade.

O agendador básico permanece inalterado como caminho de compatibilidade.
As necessidades, prioridades e alvos não foram modificados artificialmente.

## Contrato de observação

A previsão contextual passiva também examina a próxima necessidade quando
não existe nenhum destino configurado/resolvido para a dominante. Só emite
uma previsão se houver alvo único verificável. Em presença de múltiplos alvos,
posição inválida ou alvo já alcançado, abstém-se sem fabricar ranking.

skipped_unresolved_needs explicita o motivo do fallback. A previsão
continua selection_phase=pre_tick, predicts_action=false,
world_mutated_by_shadow=false; não participa das decisões do scheduler.

Um tick sem deslocamento com no_target e scheduled simultâneos recebe
need_scheduled_without_displacement, e não apenas
need_no_target_observed. Nenhuma dessas etiquetas representa causalidade
comprovada.

## Gate e rollout

- Testar fallback social → curiosidade, alvo prioritário viável, todas as
  necessidades sem destino, reinício com ledger coalescido, cooldown,
  plano ativo, previsão contextual e evidência de imobilidade.
- Rodar suíte completa e CI antes de integração à main.
- Fazer deploy na VM somente após verificação do replay consistente.
- Em produção, conferir no_target de social, agendamento real de
  curiosidade, ausência de novos planos duplicados e taxa pareada em
  denominadores comuns, preservando selection_authority=false.
