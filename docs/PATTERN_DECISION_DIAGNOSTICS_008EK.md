# 008EK — explicar decisões de padrões e suas abstenções

A live 008EJ acumulou experiências, mas a coleta observada ainda não tinha decisões atribuídas à preferência aprendida. A auditoria reproduzível de 101 resultados físicos encontrou 28 assinaturas: 24 sem duas amostras de cada lado e quatro sem diferença de custo suficiente. Isso explica a ausência de preferência naquela coleta; não há motivo experimental para forçar uma escolha ou reduzir o limiar apenas para aumentar o contador.

## Mudança

`nov_navigation_patterns.evaluate()` passa a ser a fonte única da recomendação e da explicação. Expõe amostras, erros, escores por lado, diferença de escores e margem exigida. Motivos: `disabled`, `insufficient_samples`, `side_without_success`, `insufficient_margin` e `preferred_side`. A regra conservadora já existente que se abstém quando um lado não tem nenhum sucesso é preservada.

O coletor guarda a avaliação no momento da proposta. O contorno copia essa avaliação, e `NOV_PATTERN_DECISION` registra a cópia somente quando a primeira ação física do contato foi executada. O estado de aprendizado inclui `patterns.decision_reasons` e `patterns.last_evaluation`. Exploração continua identificada como `pattern-exploration`; uma proposta de preferência não implica mudança aplicada se a alternativa for rejeitada pela física.

O `contact_id` da decisão é o `attempt_id` do resultado físico em `NOV_PATTERN_OUTCOME`. Isso permite ligar origem, IDs recuperados, lado proposto/aplicado, motivo e custo posterior. Mudança de escolha e vantagem são medidas distintas: uma escolha alterada pode ter resultado pior. Comparação causal exige condições equivalentes e controle das mudanças de cenário.

Não há alteração da margem, penalidades, escala de 3 m, movimento ou política de preferência. O perfil v3 e os arquivos `008ej.json` são mantidos, preservando os fatos já coletados para uso após reiniciar. Não são reingeridos sob outra versão. Nenhum aviso foi adicionado à tela da live.

## Verificação

45 regressões Godot passaram; sintaxe do instalador e unidades systemd verificadas. Os avisos de CPUAccounting em unidades XFS do sistema são alheios a esta atualização. No teste nativo com o núcleo real, o contador `preferred_side` e a recomendação com IDs recuperados foram verificados.

O teste de diagnóstico cobre desativação, falta de amostras, custos iguais, preferência clara, regra conservadora de falhas, separação entre exploração e preferência e cópia que impede alteração externa da avaliação. A recomendação usa a mesma avaliação, evitando duplicação da regra no diagnóstico.

A reanálise em RAM das 101 experiências usa a implementação Godot real e produz `PATTERN_DIAGNOSTIC_AUDIT_008EK.json`; não altera a live nem grava dados no núcleo de produção. Os quatro contextos com ambos os lados avaliáveis ficaram abaixo da margem, e os demais não tinham amostras suficientes.

A comparação física isolada com o núcleo SQLite real, fixado em `dfd87c995b50c49b45a9d5dd4c43cce456983d4f`, preservou o resultado: percepção 234,5723 m / 70,4 s; RAM e núcleo recuperado 106,6055 m / 32 s; sem colisão, resgate ou planejamento global. Quatro resultados nativos recuperados após reabrir o núcleo e remover o cache; um envelope legado sintético, restrito ao teste, ignorado. Isso valida a instrumentação e o mecanismo nesse cenário, não vantagem na live.

## Aplicação

Execute `sudo bash /home/etbra/apply-pattern-decision-diagnostics-008ek-root.sh`. O instalador tem backup e rollback, pausa a ponte durante a troca, verifica estado recente e sinalizador público de diagnóstico. Mantém o perfil v3 e os arquivos da 008EJ. Não foi executado remotamente pelo Codex; a live continua na 008EJ até aplicar.

Após aplicar, observar os motivos em `nov-learning-status-008df.json`, ligar cada decisão ao resultado por identidade e separar exploração, preferência local e preferência com IDs recuperados. A próxima evolução deve ser orientada por esses dados, especialmente se assinaturas semelhantes ocultarem obstáculos diferentes.
