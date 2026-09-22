# Decision Provenance 001

## Objetivo

Separar claramente duas trilhas:

1. **Decision provenance**: tudo que tentou modificar o mundo e a decisão da política.
2. **Authoritative replay**: somente mudanças realmente aceitas e aplicadas ao universo.

Uma proposta rejeitada deve ser auditável, mas nunca virar evento/delta do World State.

## Fluxo

```text
TikTok / YouTube / IA / Memoria.ia / agente
        |
        v
proposal / intent
        |
        v
validator
        |
        v
Mutation Gate
   | accepted              | rejected
   v                       v
Decision Log             Decision Log
   |                       |
   v                       +--> fim (sem mutation)
GuardedMutationService
   |
   v
ColdAuthoritativeWorldEngine
   |
   +--> event + delta + state_hash
   |
   v
Authoritative Replay
```

## Decision log

Arquivo padrão no runtime cold:

`DATA_DIR/mutation-decisions.jsonl`

Cada registro contém:

- `accepted`
- `reason`
- principal (`source`, `actor_id`, `authority`, `subject_entity_id`)
- operações propostas
- `before_state_hash`
- `after_state_hash`
- `state_changed`
- `world_event_id` quando aceito
- contexto da proposta/aprovação
- timestamp de auditoria

O decision log não participa do `state_hash` do universo e não entra no replay autoritativo.

## Invariante de rejeição

Para toda decisão rejeitada:

```text
before_state_hash == after_state_hash
world_event_id == null
no event
no delta
no cold-store mutation
```

## Invariante de aceitação

Para toda decisão aceita:

```text
world_event_id != null
mutation_provenance.policy == mutation_gate_v1
mutation_provenance.decision == accepted
```

O registro do decision log aponta para o evento autoritativo correspondente.

## Autoridade

- `system`: acesso completo.
- `operator`: acesso completo.
- `world_agent`: create/set/move/link/unlink.
- `entity_agent`: set/move/link/unlink apenas na própria entidade.
- `audience`: proposal-only.
- `observer`: sem escrita direta.

## Aprovação de audiência e IA

Audiência e fontes externas não recebem autoridade de mutação por terem produzido uma proposta válida. A proposta pode ser aprovada por uma origem com autoridade suficiente (por exemplo, operador), e só então chegar à Gate com essa autoridade explícita.

A autorização deve estar na proveniência do commit; não deve ser inferida da qualidade semântica da proposta.

## Relação com Memoria.ia

A Memoria.ia poderá produzir contexto, evidência ou proposta de mudança. Isso não concede escrita direta no universo. O boundary permanece:

```text
Memoria.ia -> proposal -> Mutation Gate -> authoritative mutation
```

Essa separação preserva proveniência, causalidade e capacidade de auditoria.
