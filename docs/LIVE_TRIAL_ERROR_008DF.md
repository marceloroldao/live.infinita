# 008DF — Tentativa e erro na caminhada da live

Integra aprendizagem por caminhadas completas, redução do bônus de experiências com custo maior e painel de evidência. A instalação exige o script de atualização no servidor; este documento descreve o código preparado e validado, não confirma que ele já está rodando na live.

## Comportamento

Na caminhada ao vivo, Nov escolhe passos locais percebidos, usando visitas e experiências, com busca global de rotas desligada. A física continua validando o corpo e o segmento realmente executado. Percepção que rejeita um candidato não é registrada como colisão nem sucesso inventado.

A jornada usa o identificador do objetivo comprometido e o contexto do mundo. Acumula a distância horizontal efetivamente percorrida por quadro, incluindo todos os segmentos de uma ação. A chegada ao objetivo encerra a caminhada e atualiza custos na RAM. Um objetivo encerrado ou substituído gera interrupção; ações antigas não são atribuídas ao objetivo novo. A mesma chegada não é repetida a cada quadro.

Caminhadas incompletas ou com falha física não produzem custo de sucesso. Cada passo efetivamente concluído pode continuar sendo uma experiência temporária, sujeito aos critérios anteriores. Só três reutilizações causais distintas e bem-sucedidas promovem um passo. Nenhuma leitura ou consulta conta como reutilização.

O custo de uma escolha é a distância observada restante até chegar. Compara-se a média com outras escolhas realmente observadas no mesmo endereço; o bônus perde a diferença, limitado a zero. Não existe custo contrafactual de uma ação não tentada. As médias passam a perder gradualmente a influência de observações antigas após 32 amostras. A percepção atual continua prevalecendo diante de um obstáculo novo.

Ao concluir uma caminhada, custos e referências das experiências já promovidas são atualizados no arquivo de promoções. O sincronizador existente os ingere na Memoria.ia; seu exportador recupera os valores dentro do resumo, junto com o ID. A RAM transitória não é transformada em memória persistente sem o critério de promoção.

Não houve alteração no núcleo da Memoria.ia: aprendizagem e seleção pertencem ao motor de Nov, com persistência e recuperação pela API estrutural.

## Painel

No renderizador nativo, mostra fonte da decisão, quantidade de experiências na RAM, promoções, chegadas, interrupções, reutilizações que realmente mudaram um passo concluído e resultado da última caminhada.

No /godot, mostra contadores da sessão do processo no servidor, recebidos pelo mesmo transporte da recuperação de memória. O arquivo de status é pequeno, atualizado a cada dois segundos e não escreve o estado autoritativo do mundo. O exportador rejeita dados de outro mundo, contadores inválidos, links simbólicos e registros fora de uma janela de 60 segundos. Sem dados atuais, a página informa que aguarda o servidor.

Passos lembrados e passos com custo observado são apresentados separadamente. O painel não afirma ganho de desempenho porque houve uma consulta ou lembrança. Comparações controladas permanecem necessárias para demonstrar melhoria.

O painel ocupa o canto superior direito abaixo da marca. A audiência continua à esquerda, o narrador no centro e o botão explorar permanece oculto.

## Testes e resultado

104 testes Python passaram. A suíte Godot inclui os 22 testes anteriores de física, locomação, câmera, programa, memória e objetivos, mais o novo teste de jornadas e painel: 23 verificações.

O ensaio usa o motor de produção com realimentação de jornada ligada durante seis caminhadas de treinamento. Seus trajetos foram 32,67; 27,39; 28,05; 23,92; 23,92; 23,92 metros. A evolução não foi monotônica. Todas chegaram sem colisões e atualizaram um custo de jornada real.

Foram promovidas seis experiências, sustentadas por decisões efetivamente executadas. A API real da Memoria.ia em SQLite isolado confirmou seis ingestões; um segundo processo recuperou os mesmos seis IDs, destinos e custos.

A comparação congelada usou três cenários, três modos e duas repetições, total de 18 avaliações:

| Cenário | Sem experiências | RAM treinada | Memoria.ia após reinício |
|---|---:|---:|---:|
| U original | 40,5753 m | 23,9200 m | 23,9200 m |
| Passagem aberta | 6,0000 m | 6,0000 m | 6,0000 m |
| Passo aprendido bloqueado | 58,5927 m | 30,7959 m | 30,7959 m |

Todas chegaram sem colisões. Não houve busca global de rota. No cenário original, cada repetição teve cinco escolhas causais de RAM ou Memoria.ia; no cenário alterado, três; na passagem aberta, nenhuma. As duas repetições reproduziram os resultados.

O motor integrado atualiza qualidade entre caminhadas e usa médias limitadas; o experimento 008DE calculava uma média congelada de aquisição, incluindo caminhadas frias. São protocolos diferentes: o resultado 19,94 m da 008DE não é apresentado como medida desta versão. Os resultados aqui são de geometrias sintéticas, não de uma medição controlada da live instalada.

## Instalação

O instalador exporta a página, instala os módulos nativos e o exportador de status, reinicia o renderizador, promove a exportação pronta e verifica flags públicas e saúde. Guarda cópias anteriores e restaura o conjunto se ocorrer falha.

No servidor:

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-live-learning-008df-root.sh
```

O registro fica em /home/etbra/008df-renderer-rollout.log. A confirmação é 008DF_OK. Nenhum comando de administração foi executado pela conexão remota durante a preparação.

O código e as evidências devem estar no GitHub antes de rodar o instalador. Para repetir o comparativo sem instalar, use tools/benchmark_navigation_live_trial_error_008df.py com o projeto Godot isolado e um caminho de relatório. Os bancos experimentais são temporários.

## Limites e evolução

Escolhas ainda são endereçadas por objetivo e posição arredondados; a aprendizagem não é geral para qualquer destino. O explorador local pode repetir movimentos ou não encontrar uma saída distante no tempo disponível. A live continua tendo prazo de reavaliação do objetivo; uma tentativa encerrada não é convertida em vitória.

O próximo trabalho é observar jornadas reais, identificar ciclos e melhorar como a experiência é reutilizada entre objetivos semelhantes. Caça pode depois usar o mesmo fluxo: tentativa, resultado observado, experiência temporária, reforço causal e recuperação persistente. Não são introduzidos animais nesta atualização.
