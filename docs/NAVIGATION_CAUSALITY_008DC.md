# 008DC — Comparação causal entre percepção, RAM e Memoria.ia

Resultado: nestes cenários, ligar a memória não mudou as decisões nem reduziu os percursos. A persistência e a recuperação funcionaram; o benefício causal de navegação não apareceu.

## Protocolo

Código de navegação da 008DB, origem 1f2f3e0. As classes do projeto isolado são verificadas contra os arquivos atuais do repositório por SHA-256.

A aquisição usou caminhadas físicas completas no obstáculo em U. A RAM recebeu somente ações realmente concluídas pelo gravador nativo. A validação das promoções exige três identidades de decisões distintas, escolha diferente da alternativa sem RAM, chegada ao passo selecionado e nenhuma colisão.

Foram obtidas 14 promoções elegíveis. Para avaliar exatamente o mesmo conhecimento nos modos B e C, a recomendação da RAM no momento da promoção foi reconstruída a partir dessas evidências verificadas. A RAM mais recente, após continuar aprendendo, pode conter outras recomendações; isso não é a população avaliada.

Os três modos de avaliação:

- A: RAM e recuperação da Memoria.ia desativadas.
- B: RAM com os 14 passos efetivamente aprendidos e promovidos.
- C: RAM desativada, com os mesmos 14 passos recuperados da API real da Memoria.ia em SQLite isolado.

A gravação e a recuperação da Memoria.ia executaram em processos Python separados. Depois de encerrar o processo que gravou, um novo processo abriu o mesmo SQLite e recuperou os registros. Os IDs recuperados foram conferidos com os ACKs de ingestão, e seus endereços e destinos com o conhecimento usado na RAM.

Cada avaliação começa com um navegador novo e o mesmo estado vazio de planejamento, visitas e recuperação local. Não há aprendizado de passos novos durante a avaliação; a revalidação física ainda pode retirar uma recomendação contradita da RAM.

Cada cenário teve dois ensaios por modo: 18 avaliações no total. O início, objetivo, geometria, cápsula, velocidade de 4 m/s e passo de simulação de 0,1 s foram mantidos iguais entre os modos.

## Relógio do ensaio

Uma simulação acelerada pode executar centenas de segundos de movimento antes de decorrerem cinco segundos reais na CPU. O tempo real de espera para repetir a busca produziu percursos diferentes mesmo com zero decisões causais de memória.

No ensaio final, o instante de última busca é ajustado somente no projeto de teste para usar o mesmo tempo lógico de 0,1 s por quadro em todos os modos. Isso normaliza o intervalo de cinco segundos de replanejamento. O orçamento de CPU das fatias de BFS permanece; seus quadros de planejamento são registrados separadamente. O tempo apresentado de movimento é simulado, não desempenho do servidor.

Também não se deve interpretar as distâncias de aquisição como uma comparação fria/quente: essa fase conserva estado transitório enquanto coleta experiências. A comparação causal usa apenas as avaliações com estado inicial igual.

## Resultado

Distâncias reproduzidas nas duas repetições de cada modo:

| Cenário físico | Sem memória | RAM treinada | Memoria.ia recuperada |
|---|---:|---:|---:|
| U original | 17,6671 m | 17,6671 m | 17,6671 m |
| Parede frontal removida | 6,0000 m | 6,0000 m | 6,0000 m |
| Um passo aprendido passou a estar bloqueado | 35,3376 m | 35,3376 m | 35,3376 m |

Todas as 18 avaliações chegaram ao destino sem colisões. Nos três modos, os tempos simulados de movimento foram respectivamente 5,3 s, 1,8 s e 10,6 s por cenário. Houve zero ações causais de RAM e zero ações causais de Memoria.ia.

A Memoria.ia confirmou a ingestão de 14 registros e recuperou os mesmos 14 após a troca de processo. Isso comprova o fluxo persistente nesse experimento, mas não um ganho causado por lembrar.

No código atual, uma rota física já calculada e um objetivo próximo com corredor livre podem encerrar a decisão antes de escolher entre candidatos de memória. O resultado é consistente com essa prioridade. Não permite concluir que a memória nunca ajuda em outras geometrias.

## Evidência e reprodução

- NAVIGATION_CAUSALITY_RESULT_008DC.json: resumo, parâmetros, hashes, recibos, recuperação, promoções e métricas.
- NAVIGATION_CAUSALITY_EVIDENCE_008DC.json.gz: relatório completo, incluindo ações executadas e evidências de promoção. Seu SHA-256 descomprimido consta no resumo.
- Cinco testes novos rejeitam falso efeito por concordância, reutilização de uma tentativa fracassada, ID recuperado sem recibo, conhecimento desigual entre modos e ausência de um braço. Os 87 testes Python de navegação passaram.
- O roteiro Godot foi executado pelo comparador nas 18 avaliações; os testes da live não precisam ser repetidos porque nenhum arquivo do renderizador foi alterado.

No servidor, sem sudo e sem instalar na live:

```bash
cd /home/etbra/live.infinita
bash deploy/run-navigation-causality-008dc.sh
```

O comando usa o projeto Godot de teste já preparado, grava relatórios com horário em /home/etbra e conclui com 008DC_BENCHMARK_OK. Toda escrita da Memoria.ia ocorre em uma pasta temporária exclusiva; nenhum banco ou serviço de produção é alterado.

## Próximo experimento

Integrar experiências verificadas ao planejamento de corredores e comparar o trabalho de busca, além da distância. A lembrança deve continuar sujeita à física atual, e um caminho pior não deve vencer apenas porque foi repetido. Reusar este mesmo protocolo para verificar ganho, neutralidade ou regressão, incluindo mudanças de obstáculos.

O alcance permanece limitado a geometrias sintéticas finitas em terreno plano. Este resultado não é uma medição controlada da live nem uma prova de generalização irrestrita.
