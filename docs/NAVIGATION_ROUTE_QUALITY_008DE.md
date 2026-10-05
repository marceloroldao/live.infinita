# 008DE — Qualidade da experiência pelo custo do percurso completo

A avaliação do resultado completo removeu a regressão observada na 008DD. No U original, o percurso com cinco experiências promovidas caiu de 42,13 m para 19,94 m. Nos outros dois cenários os resultados foram preservados. O teste e o novo motor são experimentais e isolados; não houve instalação na live nem alteração de sua memória.

## Regra implementada

Para cada ação de uma caminhada realmente concluída, o comparador soma as distâncias dos segmentos executados daquela ação até a chegada. Guarda a média desse custo restante para o endereço objetivo/origem e o destino selecionado. Usa somente episódios completos, sem colisões nem ações interrompidas ou bloqueadas.

A referência é o menor custo médio entre escolhas efetivamente observadas naquele endereço. Não é uma rota ideal calculada nem o custo de uma ação que Nov nunca executou. A penalidade é a diferença não negativa entre o custo da escolha e essa referência. O bônus de memória passa a ser max(0, bônus original − penalidade). A regra somente reduz o incentivo de uma recomendação: nunca autoriza atravessar obstáculos e nunca aumenta o bônus.

O motor mantém os candidatos locais, a percepção física, os registros de resultado e as alternativas usadas para medir causalidade. A busca global continua desligada. A função de seleção experimental é uma cópia verificável da versão de produção: um teste garante que as únicas diferenças são a redução dos dois bônus de memória e os campos de evidência.

A implementação está em tests/nov_trial_error_quality_008de.gd. O aprendizado dos custos observados está em tools/benchmark_navigation_route_quality_008de.py. Nesta etapa, os custos são calculados após a aquisição e congelados antes da avaliação; a atualização dentro de uma sessão da live ainda não foi integrada.

## Aquisição e persistência

A aquisição reproduz a 008DD: duas caminhadas sem memória e seis caminhadas que aprendem na RAM. O estado transitório é limpo entre caminhadas. A avaliação de qualidade usa os oito episódios físicos completos, sem dados dos cenários de avaliação.

A RAM adquiriu 27 recomendações; cinco satisfizeram o critério de três reutilizações causais bem-sucedidas e foram promovidas. O comparativo usa somente essas cinco, igualando o conhecimento disponível nos modos RAM e Memoria.ia. Cada promoção recebe o custo observado, a referência e o número de amostras.

A API real do SDK da Memoria.ia confirmou cinco gravações no SQLite temporário. Um segundo processo reabriu o banco e recuperou os mesmos cinco IDs, destinos e valores de qualidade. O comparador verifica essa igualdade antes de iniciar a avaliação. Nenhum peso foi recuperado de um arquivo lateral no modo Memoria.ia.

A Memoria.ia continua responsável pela persistência e recuperação. O cálculo de qualidade pertence ao motor experimental; não foi acrescentado um algoritmo de aprendizado ao núcleo da Memoria.ia.

## Comparação controlada

Três geometrias, três modos de memória e duas repetições, com e sem redução de bônus: 36 avaliações. Todas usam início, objetivo, cápsula física, velocidade de 4 m/s, passo de simulação de 0,1 s e estado inicial novos. Nenhuma aprende passos ou custos novos durante a avaliação. Recomendações permanecem sujeitas à percepção atual.

| Cenário | Sem experiências | Bônus anterior | Bônus com qualidade |
|---|---:|---:|---:|
| U original | 40,5753 m | 42,1322 m | 19,9373 m |
| Parede frontal removida | 6,0000 m | 6,0000 m | 6,0000 m |
| Passo aprendido bloqueado | 58,5927 m | 30,7959 m | 30,7959 m |

Os modos RAM e Memoria.ia após reinício produziram as mesmas distâncias em cada condição. As duas repetições também reproduziram os resultados. Todos os 36 ensaios chegaram ao objetivo sem colisões. As construções de rota global foram zero.

No U original, a nova regra reduziu o percurso em 52,68% contra o bônus anterior e 50,86% contra ausência de experiências. O tempo simulado de movimento caiu de 12,5 para 6,0 segundos contra o bônus anterior. Com qualidade, houve quatro escolhas causais de RAM ou Memoria.ia por repetição; no cenário alterado, três. Na passagem aberta, nenhuma.

O controle sem memória produziu exatamente a mesma distância, tempo, revisitas e chegada com a regra ligada e desligada. Seu resultado é conferido pelo comparador.

## Validação e reprodução

Cem testes Python de navegação passaram. Os seis novos verificam custo de segmentos executados, comparação somente com escolhas observadas, exclusão de episódios incompletos ou falhos, média e quantidade de observações, arredondamento compatível com Godot e preservação da lógica de seleção.

O contrato executado no Godot verifica regra desligada, ausência de evidência, redução parcial, piso zero, referência igual, valores inválidos e qualidade recuperada por JSON. Godot converte números JSON para float; o carregamento aceita contagens inteiras representadas por float e rejeita valores fracionários.

No servidor:

```bash
cd /home/etbra/live.infinita
bash deploy/run-navigation-route-quality-008de.sh
```

O script prepara o módulo experimental no projeto isolado, verifica a importação, executa aquisição, gravação/recuperação em processos separados e as 36 avaliações. Conclui com 008DE_BENCHMARK_OK. Não solicita instalação.

NAVIGATION_ROUTE_QUALITY_RESULT_008DE.json contém o resumo, hashes de origem, qualidade recuperada, métricas e comparação dos pesos. NAVIGATION_ROUTE_QUALITY_EVIDENCE_008DE.json.gz inclui todas as ações de aquisição/avaliação e as amostras de custo. O SHA-256 descomprimido consta no resumo.

## Limites e próxima integração

O custo observado mistura diferentes políticas durante a aquisição; ele associa escolhas ao resultado que aconteceu, não estima um contrafactual ótimo. Endereços de um metro e destinos arredondados a cinco centímetros podem agrupar estados próximos. A referência deve ser reavaliada quando o ambiente muda; nenhum valor antigo elimina a validação física.

São três geometrias sintéticas em terreno plano, não uma medição controlada da live. O resultado sustenta a regra neste protocolo, sem demonstrar generalização irrestrita.

A próxima integração deve acumular o custo real por passo durante uma caminhada completa, atualizar qualidade somente ao encerramento, registrar a nova evidência e recuperar seus valores pela Memoria.ia. Caminhadas abandonadas exigem um tratamento separado; não devem receber custo de sucesso inventado. Antes de instalar, o comportamento com rotas físicas planejadas e objetivos mutáveis precisa de um ensaio próprio.
