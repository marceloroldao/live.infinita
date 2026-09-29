# MVP-018J — duas vias de lembranças observadas para Nov

## Motivo e evidência

O relatório real MVP-018I com 258 observações confirmou um caso em que cinco
lembranças do baseline são 4/4 coincidentes, mas pertencem a um único perfil de
trajetória. O hybrid estrito manteve esses cinco (2 âncoras, 0 substituições,
1 perfil). O exploratório encontrou cinco perfis com vetor [4,3,3,3,3],
ou seja, ganhou diversidade perdendo quatro coincidências completas.

Não substituímos evidência direta por parcial. O MVP-018J mantém dois
contextos distintos, com proveniência V2 independente:

- **Primário (5 máximo)** — MVP-018I de maior correspondência, com âncoras e
  vetor exato de coincidências preservados.
- **Suplementar (3 máximo)** — outros perfis de trajetória realmente
  observados (endereços + resultado tipado), não presentes na via primária,
  com pelo menos uma coincidência de endereço. Contagens de coincidência são
  expostas separadamente; a via suplementar não altera a primária.

Repetições de perfil não são tratadas como novas rotas apenas por terem
outros IDs. Ausência de alternativa retorna zero evidências adicionais.
Nenhuma lembrança recebe sinal inventado de ação boa/ruim, utilidade,
probabilidade ou causalidade. O resultado complementar não participa da
escolha de alvo ou estratégia.

## Propriedade e execução

`OwnerDualLaneRecallObserver` é invocado apenas no processo temporário
de diagnóstico, separado do tick de 500 ms. Reutiliza o índice privado
`VersionedNovRecallCache` depois de validação pelo EvidenceCore da versão
pinada V2, confere versão antes e depois, e congela primário e suplementar
separadamente com `freeze_memory_context` (IDs, mundo, época, proveniência).
Todo dado sensível permanece na RAM do usuário `liveinfinita`.

O script manual continua o mesmo:

```bash
cd ~/live.infinita && bash deploy/mvp018g-nov-memory-diagnostics.sh
```

O log privado `~/nov-memory-diagnostics.log` (0600) inclui
`dual_lane_comparison`: contagens e perfis distintos em cada via,
vetor de coincidência suplementar e garantia
`supplementary_used_to_rank_primary=false`. Não contém payload, nome de
endereço, valor de outcome, hash ou ID de evidência. O código público vai
para diretório temporário removido no final; a memória original não sai de
`/var/lib/live-infinita/memoria-local`.

Este estágio NÃO liga `memory_recall_provider` ao processo principal,
NÃO cria daemon, thread/timer, cache em disco, ação, World State, central
sync, BDR cutover ou restart. O cache frio ainda pode custar centenas de
milissegundos e, por isso, continua proibido dentro do tick autoritativo.

## Gates

1. Invariância do primário, identidade distinta e abstenção da via extra.
2. Proveniência independente da via suplementar usando núcleo V2 real.
3. Testes de segurança/privacidade e CI integral.
4. Rodada privada com memória real para avaliar quantos novos perfis
   são acrescentados sem degradar as cinco lembranças primárias.

Sem validação de comportamento ou qualidade decisória; o experimento mede
apenas recuperação tipada e diversidade observada.
