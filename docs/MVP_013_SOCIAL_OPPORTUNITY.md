# MVP-013 — Descoberta de oportunidade social verificável

## Contexto

O mundo de produção contém Nov, árvores, fogueira, abrigo e cama; não contém
outro ator social. A necessidade social pode chegar a 1.0, mas nenhum destino
social legítimo pode ser inventado para satisfazer a métrica. O fallback do
MVP-012c permanece válido para outras necessidades urgentes.

## Descoberta passiva e limitada

NpcSocialOpportunity consulta somente a região corrente e vizinhas de um
salto, usando o FileRegionColdStore e o catálogo espacial existentes. O limite
é de 8 regiões e 32 candidatos, com sinalização explícita de truncamento.

Uma entidade de qualquer tipo pode oferecer interação social, inclusive
futuros agentes da natureza, se o próprio estado autoritativo anunciar:
- properties.interaction_capabilities contendo social;
- properties.available_for_interaction igual a true;
- posição finita e região observada válida.

A própria Nov, destinos distantes além do recorte, entidades indisponíveis,
sem capacidade ou com posição inválida são excluídos. A descoberta não cria
entidades, não altera propriedades e não escreve no mundo. O modelo não
deduz capacidade social somente de human, npc, tree ou outro tipo.

## Encaminhamento pelo scheduler

O agendador usa os IDs observados como candidatos opcionais de social,
junto com referências previamente configuradas. A seleção continua usando
NpcNeedLearning e NpcStrategyValue existentes, além da ordem e do
arbitramento autoritativos. Não se cria vínculo permanente por configuração.

A origem observed_social_capability é preservada em proposta, decisão,
intenção direta e fase terminal de estratégias compostas. A previsão
contextual recebe a mesma evidência no pre_tick, mas se abstém diante de
múltiplos alvos sem ranking verificável: ela não se apropria da decisão do
scheduler. Seu resultado continua read-only e sem previsão de ação.

## Contato não é interação

Para planos sociais cuja origem é a descoberta dinâmica, completar
move_to_entity NÃO prova troca social, satisfação ou aprendizagem.

NpcNeedOutcomeProcessor registra exatamente uma observação de encontro,
com co-presença, disponibilidade atual e distância, ou encounter_unverified.
Não reduz social, não reforça NpcNeedLearning, não cria episódio positivo e
não deriva crença. O processador composto audita encounter_only sem
recompensar a estratégia. As regras legadas de alvos sociais explicitamente
configurados não são alteradas por este incremento.

O contrato futuro deverá admitir evidência de interação autorizada, com
identidade, evento, resultado, proveniência e deduplicação. Só então uma
relação e eventual satisfação podem ser inferidas do resultado observado;
proximidade e encontro permanecem evidências distintas.

## Gates

- Mundo sem parceiro: nenhum destino fabricado e nenhuma escrita.
- Região corrente/vizinha, limitação determinística, disponibilidade
  revogável, capacidade explícita, origem registrada.
- Múltiplas opções: baseline contextual se abstém sem inventar ranking.
- Agendador e estratégia composta preservam origem no plano real.
- Encontro sem confirmação: zero satisfação, zero aprendizado e idempotência
  após reinício.
- Suíte completa, CI, replay de snapshot consistente, Single Writer e
  Mutation Gate antes de deploy.

A produção atual terá status no_observed_social_actor até um ator real,
autorizado e disponível entrar no mundo. Não inserir um personagem fictício
para declarar sucesso desse gate.
