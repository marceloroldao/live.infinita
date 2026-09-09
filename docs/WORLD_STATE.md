# World State

O mundo evolui por deltas validados e versionados:

`World(t+1) = World(t) + Delta(t)`

Domínios principais: metadata, time, space, entities, relations, claims, knowledge, rules, events, deltas, versions, snapshots, trajectories e provenance.

Cada entidade recebe `entity_id` estável. Relações usam `subject -> predicate -> object`. Claims representam afirmações não resolvidas e mantêm fonte, confiança, suporte, contradições e status. Eventos explicam como o estado mudou. Deltas aplicam mudanças locais sem regenerar o mundo inteiro.

`World != Scene`: o mundo pode ter milhões de entidades, enquanto a cena é apenas uma projeção local. Regiões/chunks permitem crescimento indefinido sem carregar tudo simultaneamente.

Snapshots periódicos permitem reconstruir o estado a partir do snapshot mais recente + deltas posteriores. A remoção física deve ser rara; entidades destruídas permanecem historicamente acessíveis.

Uma entidade pode possuir trajetórias espaciais, sociais, narrativas, emocionais e de propriedade. Conhecimento e crenças devem poder ser indexados por observador para evitar NPCs oniscientes.
