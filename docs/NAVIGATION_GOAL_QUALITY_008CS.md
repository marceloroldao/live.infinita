# 008CS — destino próximo visível e memória diante de obstáculos novos

## Mudança

Se o destino está a até três metros, o navegador consulta a percepção
física sobre todo o segmento até ele. Somente quando allowed e clear_ahead
são verdadeiros escolhe o próximo passo direto, sem bônus de um desvio
lembrado. A percepção percorre o segmento em subpassos; verificar apenas
o ponto final não é suficiente.

A regra não supõe visibilidade para destinos distantes. Se o corredor
até o destino está bloqueado, a seleção normal por percepção e memória
continua. A validação física também continua durante cada avanço.

O episódio registra goal_corridor_clear. Concordância de memória com
a escolha direta continua distinguida de uso causal: não atribuir
aprendizado a uma alternativa que a percepção já escolheria.

## Experimento controlado

Aprendizado em RAM, promoção pelo sincronizador de produção, confirmação
pela API real do core em SQLite temporário e exportação do recall.
Nenhuma memória de produção foi escrita.

Três cenários, dois modos e duas repetições por combinação: 12 percursos
com início (-100,0), destino (-94,0), terreno plano, delta 0,1 s e
velocidade configurada de 4 m/s. As duas repetições de cada combinação
coincidiram; todas chegaram e nenhuma teve colisões.

| Cenário | Sem memória | Com Memoria.ia | Colisões |
|---|---:|---:|---:|
| Obstáculo em U | 40.58 m | 42.13 m | 0 |
| Passagem aberta | 6.00 m | 6.00 m | 0 |
| Passo aprendido bloqueado | 58.59 m | 30.80 m | 0 |

No cenário de bloqueio novo, três candidatas lembradas foram rejeitadas
pela percepção. O primeiro passo escolhido difere da lembrança bloqueada.

A passagem aberta percorreu os seis metros sem afastamento do destino
nem retorno a células anteriores. A versão anterior fazia uma pequena
volta com memória (6,53 m). Antes e depois aprenderam sementes próprias:
não interpretar essa diferença como uma comparação causal entre
algoritmos com exatamente a mesma memória. O teste de regressão
também verifica diretamente que RAM e recall de desvio não dominam
um corredor próximo observado como livre.

## Limites

No U mantido, o recall atual ainda produziu um caminho um pouco maior
que o controle atual. A correção não estabelece que toda lembrança
melhora um percurso. Passos reutilizados continuam sendo promovidos
por três sucessos locais, não por redução comprovada de custo total.

Retornar a uma célula ou afastar-se do destino pode ser necessário
para sair de um obstáculo. Esses indicadores são medidas do percurso,
não motivos automáticos para punir uma experiência. Próxima prioridade:
comparar custos de rotas completas com condições equivalentes antes
de reforçar preferências. Não há planner global ou garantia de saída
de qualquer terreno.

O JSON NAVIGATION_ENVIRONMENT_RESULT_008CS.json guarda as duas rodadas,
hashes e os limites da comparação. O experimento é sintético;
nenhum ganho controlado na live foi medido.

## Verificação

72 testes Python e 14 testes Godot de publicação, incluindo prioridade
de destino próximo, preservação de desvio seguro, ausência de falsa
atribuição causal, limite de três metros e obstáculo depois do destino.
O runner valida cobertura das 12 combinações, repetibilidade, chegada,
ausência de colisão, rejeição de lembrança bloqueada e trajeto aberto
direto. Tempo simulado não mede desempenho do servidor.

Reproduzir em projeto isolado importado:

```bash
/opt/live.infinita/.venv/bin/python tools/benchmark_navigation_promotion_008cq.py --godot-project /home/etbra/008bz-godot-test --report /home/etbra/promotion-quality.json --environment-report /home/etbra/environment-quality.json
```

Instalador preparado: deploy/apply-navigation-goal-quality-008cs-root.sh.
Sucesso: 008CS_OK. Atualiza Web e renderer nativo com backup/rollback,
preserva a marca no topo, audiência e narrador no centro.
Log: /home/etbra/008cs-renderer-rollout.log.
