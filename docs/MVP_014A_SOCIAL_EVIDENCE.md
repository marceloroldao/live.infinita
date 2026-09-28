# MVP-014a — Evidência social e memória de relações (contrato v1)

## Delimitação operacional

O MVP-013 pode descobrir uma entidade social real e registrar o encontro físico,
mas não deve deduzir conversa, afeto, reciprocidade ou satisfação apenas pelo
deslocamento. O MVP-014a adiciona uma trilha persistente própria
`npc-social-evidence.jsonl`, mantida **somente pelo Single Writer**.

Não existe ainda um produtor autoritativo de eventos de conversa confirmada.
Por isso, na produção atual, o contrato de troca permanece fechado:
`world_event_resolver=None`. Nenhum comentário de público, entrada,
curtida, presente, áudio de narração ou texto de LLM satisfaz esse contrato.

## Trilha fraca: encontro observado

Origem exclusivamente interna: `NpcNeedOutcomeProcessor`, com status
`encounter_observed`, necessidade social, IDs do agente e do outro participante,
plano terminal e evidência de co-presença real (`distance <= 1` e disponibilidade
observada). Não aceita aproximação inferida de outro payload, status
`encounter_unverified`, entidade ausente, IDs contraditórios ou distância inválida.

Identificador imutável: `encounter:<plan_id>`. Registro persistente:
`kind=encounter`, `status=observed_unconfirmed`, `confirmed=false`,
`satisfaction_delta=0`, proveniência da avaliação terminal. Nenhuma mutação
do mundo, recompensa, episódio positivo, crença ou etiqueta de amizade.

Reinício: na primeira projeção, a memória reconcilia o JSONL de resultados
autoritativos; caso o processo tenha parado após registrar o resultado do
plano, mas antes de projetar a relação, recupera-o sem duplicação.

## Contrato futuro de interação confirmada

Somente um componente de autoridade previamente integrado ao runtime poderá
fornecer eventos através de `world_event_resolver(event_id)`. O consumidor
não aceita um payload arbitrário do público nem flags fornecidas pelo cliente.

Evento de troca, resolvido por ID:

```json
{
  "schema": "social_exchange_v1",
  "event_id": "evt_exchange",
  "kind": "social_exchange",
  "status": "completed",
  "npc_id": "nov",
  "peer_entity_id": "outro_agente_real",
  "logical_tick": 123,
  "npc_ack_event_id": "evt_ack_nov",
  "peer_ack_event_id": "evt_ack_peer",
  "provenance": {"channel": "agent"},
  "outcome": {"signal": "positive", "observed_satisfaction_delta": 0.2},
  "context": {"region_id": "clearing", "period": "day"}
}
```

Cada confirmação é um registro autoritativo distinto `social_ack_v1`,
`kind=participant_ack`, com o mesmo `exchange_event_id`, papel
`npc` ou `peer`, ID da entidade correspondente e `status=accepted`.
Um único reconhecimento, confirmação trocada de papel, ID ausente ou divergente
não confirma uma interação.

Para público, `provenance.channel=audience` exige `source_event_id`;
o acknowledgement do participante exige o mesmo evento de origem e
`binding_verified=true`, emitido pela autoridade responsável pelo vínculo
entre conta de origem e entidade. O ingresso terá de validar a identidade na
plataforma e o binding antes de emitir esses registros; a API pública atual
não expõe uma rota para criar confirmações.

O resultado é uma observação explícita: `positive`, `neutral` ou
`negative`, sem atribuição de emoção por LLM. Crédito positivo é numérico,
finito, entre 0 e 0,35, e só pode acompanhar `positive`.
`neutral` e `negative` são experiências, mas não reduzem a necessidade.

## Trajetória de relação, sem rótulo imposto

A projeção `relationship(npc_id, peer_entity_id)` devolve contagens de
encontros, trocas confirmadas, sinais positivos/neutros/negativos, soma da
satisfação efetivamente aplicada e IDs de evidência. `relation_label=null`.
O sistema não nomeia arbitrariamente uma amizade nem perde evidência
desfavorável.

Quando e somente quando houver troca confirmada pela fonte confiável,
`NpcNeedDynamics.satisfy`, `NpcEpisodicMemory.remember` e
`NpcNeedLearning.observe` usam o identificador `exchange:<event_id>`.
A trilha persiste por último; se houver interrupção antes dela, a repetição
é idempotente nos três componentes e reconstrói a trilha sem duplo crédito.
Não se alimenta o modelo de risco `NpcBeliefModel` com esse registro.

## Gate de produção

- Suíte completa e CI verde.
- Fonte publicada na main, arquivos de produção idênticos e replay íntegro.
- Na produção atual sem outro agente, nenhuma evidência social fabricada,
  `npc-social-evidence.jsonl` vazio ou ausente e necessidade social inalterada.
- Shadow continua read-only, sem seleção de ação e sem mutações.
- Uma futura integração de ingressos autenticados e troca real requer PR
  e gate separados: esta etapa não abre uma API de confirmação.
