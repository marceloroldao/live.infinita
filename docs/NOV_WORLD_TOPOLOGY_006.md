# NOV World Topology 006

## Objetivo

Transformar os POIs do Vale de Nov em regiões persistentes reais do World State,
sem mover a autoridade para o Godot. O renderer continua apenas projetando a
posição autoritativa recebida por `delivery.observer`.

A topologia base passa de 3 para 12 regiões conectadas. As regiões históricas
`clearing`, `shelter` e `deep_forest` mantêm seus centros originais. Os
novos centros foram calculados pela inversa da transformação de similaridade
usada por `world_map_live_visual.gd`, de modo que cada centro runtime projete
sobre o mesmo landmark do mapa de 2.048 × 2.048 m.

## Regiões

- clearing
- shelter
- deep_forest
- river_crossing
- village
- ridge
- waterfall_overlook
- watchtower
- stone_circle
- cave
- meadow
- ruins

A definição versionada está em
`examples/nov-world-regions-005.json`. O arquivo não substitui o World State;
é apenas a entrada declarativa da migração.

## Persistência

A migração usa `ColdAuthoritativeWorldEngine.commit_operations()` com uma
única operação `set_world(["regions"])`. Assim a expansão entra na cadeia
normal de `sequence`, `events.jsonl`, `deltas.jsonl` e `state_hash`.

O bootstrap histórico não é alterado. Isso preserva o hash inicial usado por
replay. O operador `replace_world_from_bootstrap` foi ajustado para manter
`world.regions` já persistidas, portanto um reset de entidades/ambiente não
apaga o mapa que cresceu depois do bootstrap.

Regiões não conhecidas pela topologia base, como regiões coletivas criadas no
futuro, são preservadas. Vizinhos extras já associados às regiões centrais
também são mantidos pelo merge.

## Runtime autônomo

Ao abrir um mundo já existente,
`build_authoritative_autonomous_runtime()` agora cria o catálogo inicial a
partir de `engine.load_world()`, e não do bootstrap histórico. O planner já
continua atualizando a topologia a partir do World State antes de cada
planejamento.

Com isso, `NpcIdleWander` passa a enxergar os novos vizinhos no catálogo
persistido e pode atravessar a rede regional sem rota hardcoded ou LLM.

## Rollout

`deploy/nov-world-topology-006-root.sh`:

1. executa os testes e valida o arquivo declarativo;
2. cria snapshot consistente sob `world-mutation.lock`;
3. verifica replay do histórico antes da mudança;
4. pausa os dois writers por uma janela curta;
5. aplica a topologia como delta canônico;
6. tira o snapshot pós-migração e instala os dois módulos alterados;
7. religa os serviços;
8. verifica replay no snapshot estável, health, API e SpatialSession;
9. em qualquer falha posterior à migração, grava a topologia anterior como
   outro delta canônico e restaura o código anterior.

Nenhum passo faz edição direta de `world.json`.

## Gates

Os testes cobrem:

- 12 regiões conectadas e vizinhança simétrica;
- preservação dos três centros históricos;
- projeção dos centros runtime exatamente sobre os landmarks Godot;
- preservação de regiões coletivas e vizinhos extras;
- reset sem perda da topologia persistente;
- restart carregando o catálogo do estado persistido;
- aplicação da migração com replay válido;
- rollout com snapshot, flock e rollback explícito.
