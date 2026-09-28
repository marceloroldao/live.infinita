# MVP-014b — Produtor autoritativo de trocas sociais

## Estado e fronteira de segurança

Este incremento disponibiliza **o produtor interno** para confirmar uma troca
entre dois participantes independentes quando já existe um encontro auditado.
Não cria um segundo agente, não envia mensagens automaticamente e não tem rota
pública de confirmação. Não transforma um comentário do TikTok, curtida,
presente ou fala da LLM em consentimento. Na composição de produção
`key_provider=None`, `binding_provider=None` e
`source_event_verifier=None`: sem credenciais provisionadas, nenhuma troca
pode ser confirmada. A implantação desta versão é fail-closed.

O produtor executa exclusivamente no processo Single Writer, depois da
projeção dos encontros. O diário `npc-social-events.jsonl` é um ledger
autoritativo **de eventos sociais**, distinto dos `events.jsonl` e
`deltas.jsonl` da física do mundo. Não modifica `world.json` nem a posição
das entidades. Cada evento possui `sequence`, `previous_hash` e
`chain_hash`; no reinício, toda a cadeia é verificada. Hash chain detecta
corrompimento casual ou alteração isolada, mas não autentica um escritor com
acesso completo ao arquivo — a autenticação vem dos dois recibos assinados e
do isolamento do processo/escrita.

## Protocolo de dois participantes

Cada recibo `social_participation_receipt_v1` tem:

- `receipt_id`, `exchange_id`, `encounter_evidence_id`;
- `role` (`npc` ou `peer`), `entity_id`, `issuer_id`;
- `channel` (`agent` ou `audience`), `source_event_id`,
  `actor_key` (nulo para agentes), `decision=accepted`;
- `outcome.signal` e `outcome.observed_satisfaction_delta`;
- `signature`, HMAC-SHA256 hexadecimal do JSON canônico de todos os outros
  campos, com chave privada específica para a entidade e a origem.

O produtor **verifica**, mas não cria assinaturas. Não há segredo no repositório,
na narração ou em resposta HTTP. Dois recibos devem concordar sobre encontro,
troca e resultado, com IDs de recibo e evento de origem distintos e chaves
de assinatura diferentes. Nenhum dos participantes pode autenticar o outro
com sua própria credencial. O recibo `npc` somente aceita origem `agent`.

Uma origem `audience` exige, adicionalmente, `binding_provider(actor_key)`
igual à entidade declarada e
`source_event_verifier(source_event_id, actor_key)=True` por um adaptador
autenticado. Esse verificador não pode usar apenas dados da antiga rota de
comentários, que aceita IDs fornecidos pelo cliente. As credenciais e esses
adaptadores são responsabilidade de uma integração posterior com os
controladores e a origem verificada da plataforma; até lá, audiência
permanece fechada.

## Vínculo com o mundo físico e persistência

A troca exige `encounter:<plan_id>` na trilha do MVP-014a, ainda
`observed_unconfirmed`, com os mesmos participantes. O cold store é atualizado
pelo manifesto atual e confirma disponibilidade, capacidade social explícita,
mesma região e distância finita de até 1,0 no momento da confirmação.
O tick é obtido do relógio autoritativo, nunca do cliente.

Após todas as verificações, `NpcSocialExchangeProducer.produce` grava,
com IDs determinísticos e `fsync`, nesta ordem:

1. `social_ack_v1` do NPC;
2. `social_ack_v1` do outro participante;
3. `social_exchange_v1` com os IDs das duas confirmações.

O resultado é então entregue a `NpcSocialEvidenceMemory.record_confirmed`,
que resolve esses três eventos **somente pelo diário interno**. O arquivo da
memória social passa a registrar `source=authoritative_social_event_ledger`.
A redução de social e os aprendizados são idempotentes por
`exchange:<event_id>`. Resultados neutros ou negativos concedem crédito zero.
A relação permanece trajetória de evidências; não recebe rótulo automático
de amizade.

Se o processo parar depois dos três eventos, mas antes da projeção, o
`WorldTickRunner` reconcilia a troca na próxima execução. Se parar após
o primeiro ou segundo acknowledgement, a mesma dupla de recibos assinados
pode ser reapresentada para concluir sem duplicar eventos. Reuso de um
`receipt_id` em outra troca e divergência em um ID já gravado são rejeitados.
Um mesmo evento de decisão/origem da mesma entidade não pode conceder
crédito em outra troca, mesmo que um assinante tente emitir novo `receipt_id`.
O processo não revarre todo o histórico a cada tick ocioso.

## Gates e próximos passos

Os testes cobrem assinaturas falsas, falta de chave, credenciais independentes,
vínculo de audiência revogado, origem não autenticada, incapacidade social,
ausência de co-presença, recibos discordantes, crédito inválido, hash alterado,
reinício, repetição, recuperação após interrupção e integração ao tick.

Para habilitar encontros reais na live ainda faltam **provisionamento seguro
de credenciais por agente, uma decisão/ack produzida por cada controlador e
um adaptador autenticado de audiência**. Esses componentes constituem o
MVP-014c. Não habilitar confirmação por um endpoint que aceite
`accepted=true` do cliente ou permita a um operador produzir os dois
acknowledgements com uma só identidade. Não alterar o estado de mundo apenas
para produzir telemetria de relacionamento.
