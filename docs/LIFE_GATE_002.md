# Life Gate 002 — Autonomous Need/Intention Scheduler

## Objetivo

Substituir o comportamento fixo pós-reconhecimento do Life Gate 001 por uma decisão
autônoma baseada em estado interno da Nov, sem transformar necessidades em fatos da
Memoria.ia e sem permitir que o scheduler invente ações.

## Separação de responsabilidades

### Memoria.ia V2

Continua responsável por:

- memória estrutural;
- reconhecimento de contexto;
- previsão;
- surpresa;
- continuidade de regimes;
- identificação de incerteza.

Ela **não recebe** os nomes ou pressões das necessidades internas da Nov.

### Nov Need Scheduler

Mantém estado local e imutável por tick:

- `roam`: pressão para continuar deslocamento/exploração espacial;
- `recover`: pressão para recuperação/repouso.

As pressões aumentam apenas com o relógio lógico. Uma necessidade só é aliviada
depois que uma ação correspondente foi realmente aceita e executada pelo World
Runtime.

### World Runtime

Continua sendo a única autoridade de ações. Cada regra de ação pode declarar
`need_affordances`, por exemplo:

```text
walk -> roam
rest -> recover
```

Isto descreve uma affordance da ação para o scheduler; não cria uma relação
epistêmica dentro da Memoria.ia.

## Ordem de decisão

```text
World State
  -> Memoria.ia avalia previsibilidade/incerteza
  -> se existe incerteza discriminável: curiosidade escolhe PROBE
  -> caso contrário: scheduler avalia pressões internas
  -> escolhe a necessidade mais pressionada que possui ação válida disponível
  -> World Runtime valida e executa
  -> somente após commit a necessidade atendida é aliviada
```

## Cenário do gate

1. Nov começa com `roam > recover`.
2. A fonte ambiental ainda é desconhecida.
3. Mesmo com `roam` maior, curiosidade preempta o scheduler e escolhe `probe`.
4. Duas observações independentes consolidam o regime da fonte.
5. Nov sai da região.
6. O mundo avança 16 ticks.
7. Nov retorna.
8. A Memoria.ia reconhece o contexto antes de nova observação.
9. Curiosidade não precisa repetir `probe`.
10. O scheduler recebe controle e escolhe `walk` porque `roam > recover`.
11. O World Runtime executa `walk`.
12. Somente depois do commit, `roam` é aliviado.
13. `recover` passa a ser a maior necessidade atendível.
14. A decisão seguinte muda para `rest`.

## Propriedades exigidas

- curiosidade só preempta enquanto o contexto relevante está não resolvido;
- necessidades não entram em `state_addresses` enviados à Memoria.ia;
- seleção por necessidade é read-only;
- toda proposta selecionada já deve estar em `generate_valid_actions()`;
- pressão é atualizada pelo tick lógico, não por tempo de parede;
- uma necessidade só é aliviada após ação realmente commitada;
- duas execuções limpas produzem a mesma sequência;
- nenhuma LLM participa deste gate.

## Critério de aprovação

O workflow cross-repo deve incluir:

```bash
test_life_gate_002_crossrepo.py
```

O gate passa se demonstrar, em sequência:

```text
probe -> probe -> ausência -> retorno reconhecido -> walk -> rest
```

onde os dois primeiros `probe` vêm da curiosidade e `walk/rest` vêm de necessidades
internas diferentes.

## Próxima evolução

Depois deste gate, o próximo passo é remover a natureza puramente estática da fonte e
introduzir o primeiro agente ambiental persistente. Água é o candidato natural para o
Life Gate 003 porque pode possuir estado próprio, deslocamento, recorrência e efeitos
observáveis sem exigir semântica especial dentro da Memoria.ia.
