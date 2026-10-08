# 008EQ — mudanças sucessivas e retorno

Experimento físico isolado, mesma cápsula e política de contorno da 008EM, três políticas de seleção: produção, janela fixa 008EP e janela renovável 008EQ. Sequência planejada de aberturas: -20, -110, 0, -20. Cada fase tem 12 tentativas com memória acumulada, sem apagar o aprendizado entre mudanças. Quatro travessias iniciais de calibração iguais por política. Os controles de percepção por fase não entram na memória: seu arquivo é restaurado antes das tentativas.

A 008EQ renova o início da comparação toda vez que o custo físico ultrapassa 1.5 vezes a média das duas primeiras amostras do lado naquela janela e aumenta mais de 3 m. Reinicia a amostra de comparação com a observação que detectou o aumento, mantendo todos os fatos históricos. Explora até ter duas observações atuais por lado, depois usa os mesmos scores e margem da política anterior. A renovação responde ao custo observado, não conhece a posição da passagem nem recebe sinal de mudança do cenário.

| Política | Distância nas 48 tentativas | Tempo simulado |
|---|---:|---:|
| baseline | 7570.83 m | 2271.6 s |
| fixed_epoch | 6832.99 m | 2050.2 s |
| renewable_epoch | 5801.48 m | 1740.6 s |

A regra renovável economizou 1769.35 m (23.37%) contra a política atual, incluindo o custo das 48 tentativas, e 1031.51 m contra a 008EP. Os tempos são simulados, não tempo de execução na VM. A calibração inicial é igual nos três braços; o relatório também soma esse custo, que não altera a economia absoluta. Os controles extras de medição e a verificação do núcleo não entram nessa soma.

Ao retornar a z=-110, a 008EP permanece no lado +1 durante todas as 12 tentativas (234.57 m cada). A 008EQ detecta o novo aumento, realiza três propostas de exploração identificadas como tal e estabelece -1 a partir da quinta tentativa, chegando em 106.61 m. Na terceira fase z=0, paga 248.16 m extras contra a política anterior para reaprender +1; essa regressão de fase está incluída no saldo. Na volta final a z=-20, preserva +1 e percorre 92.31 m em todas as tentativas. Não cria uma nova janela quando o custo apenas cai.

## Núcleo e validade

52 observações nativas da política renovável foram armazenadas em um núcleo SQLite real isolado usando a ponte existente. O núcleo foi reaberto e o cache de recuperação removido. Recuperou as 52 observações sem reingestão; a travessia posterior usa IDs reais de observações recuperadas, lado +1 e 92.31 m. Nesse estado, a memória coincide com a percepção; essa verificação demonstra persistência e uso, não vantagem causal adicional. Os outros dois braços geraram 52 fatos físicos cada, arquivados, sem ingressá-los nesse núcleo.

As três sequências passaram: 144 tentativas e 12 calibrações, além de controles e recuperação final. Zero colisões, resgates ou buscas globais no fixture. O teste unitário sintético valida uma segunda mudança, renovação da janela, preservação dos fatos, rejeição de previsões e ausência de crédito por propostas repetidas. Esses fatos sintéticos são apenas testes de contrato. Sintaxe Python/shell, resumo e diff verificados.

Ainda é uma parede plana com uma passagem e mudanças predeterminadas. Não valida ruído, relevo, rio, obstáculos múltiplos, custos variáveis normais ou a penalidade de falhas físicas. Os limiares são escolhas de política, não parâmetros aprendidos. Não demonstra melhoria na live. A reconstrução depende da ordem dos timestamps, como o coletor existente.

A live continua na 008EM; nenhum arquivo da aplicação de produção foi alterado. O próximo passo é preparar a integração controlada da política renovável, com opção de desligar e validação das regressões físicas, antes do instalador da live.

Repetir com `bash /home/etbra/measure-repeated-changes-008eq.sh`. Saídas em `/home/etbra/008eq-results/`; cada execução cria seus próprios arquivos temporários e núcleo. Logs e fatos físicos completos estão em `docs/REPEATED_CHANGES_008EQ/`. Não há tarefa automática de monitoramento.
