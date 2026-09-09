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
