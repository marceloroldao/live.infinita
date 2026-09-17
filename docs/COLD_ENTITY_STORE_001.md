# Cold Entity Store 001

## Objetivo

Retirar payloads completos de entidades cold do `World State` residente em RAM sem alterar a identidade persistente do universo.

## Contrato

- o estado autoritativo mantém regiões, índices, versões, eventos e ponteiros;
- payloads completos cold ficam em storage persistente particionado por `region_id`;
- a RAM mantém apenas manifesto leve (`entity_id -> region_id`, contagens) e um cache LRU limitado de regiões próximas;
- somente regiões candidatas do Spatial Resolver são hidratadas;
- HOT continua sendo materializado;
- WARM continua sendo prefetch leve;
- COLD permanece fora do payload do renderer e, nesta etapa, fora da RAM de payloads completos.

## Implementação atual

`FileRegionColdStore` é um backend de referência baseado em arquivos JSON por região. Ele existe para validar o contrato e poderá ser substituído por DBR/Memoria.ia sem mudar a camada espacial.

`ColdRegionCandidateCache` mantém um número máximo de regiões hidratadas e faz eviction LRU. O cache não é fonte de verdade.

`externalize_world_entities()` persiste `world.entities` e devolve um envelope sem payloads completos residentes, com metadados em `cold_entities`.

## Invariante de escala

O número total de entidades no cold store não deve determinar o número de payloads completos residentes. Com cache de três regiões e vinte entidades por região:

- 5.120 entidades persistentes;
- <= 60 payloads completos residentes;
- resolver examina apenas as regiões candidatas atuais.

## Migração

A baseline atual do Runtime continua suportada. O próximo passo é permitir que `SpatialSession` receba um cold store diretamente e construa HOT/WARM mesmo quando `world.entities` estiver vazio.
