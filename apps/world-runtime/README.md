# World Runtime

Autoridade determinística do mundo.

Responsabilidades:

- carregar estado relevante da Memoria.ia;
- validar `ProposedAction` contra regras e estado atual;
- rejeitar ações inválidas sem alterar o mundo;
- converter ações aceitas em `Delta`;
- gerar eventos e novas versões;
- persistir o commit na Memoria.ia;
- publicar deltas para renderer, TTS e observabilidade.

Invariante: **a LLM nunca escreve diretamente no World State**.

## Environmental Rules

O ambiente físico é derivado em uma camada read-only:

Memoria.ia / recorrência
  -> cognitive terrain
  -> environmental rules
  -> clima local / umidade / neve / rocha / vegetação
  -> agentes e renderer
  -> mutation gate (quando houver mutação persistente)

environmental_rules.py não possui autoridade de escrita no World State. A
projeção cognitiva é apenas estímulo. O módulo calcula um
live-infinita-environmental-state/v1 determinístico por região, incluindo
altitude ambiental efetiva, temperatura, precipitação, umidade do solo,
cobertura de neve, exposição de rocha, densidade vegetal, adequação para árvores
e zona ecológica.

O cognitive_world_builder consulta esse estado antes de propor construções.
Exemplo: um uplift cognitivo alto e frio pode gerar afloramentos rochosos em
vez de árvores. Toda criação persistente continua obrigatoriamente passando pelo
GuardedMutationService.

A projeção ambiental também é entregue ao renderer/agentes em
delivery.environmental_state; ela nunca é injetada no world autoritativo.
