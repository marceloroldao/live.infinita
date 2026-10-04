# 008CM — auditoria observacional da caminhada na live

Leitura do arquivo nativo de episódios, sem modificar o renderer, o percurso, o World State ou a Memoria.ia de produção. A ferramenta usa o validador existente, registra o hash do snapshot normalizado, IDs de episódios, intervalo e descarte por retenção. Não acumula snapshots sobrepostos como novas evidências; identidades repetidas são deduplicadas e conflitos são recusados.

Uma decisão só entra na contagem causal da RAM quando há marcação de mudança e o ponto selecionado difere mais de 5 cm da alternativa registrada sem RAM. Para a memória de disco, exige fonte memoria.ia e alternativa registrada sem Memoria diferente. Acordo com percepção não entra na contagem causal.

## Janela registrada

Resultado completo: LIVE_NAVIGATION_RESULT_008CM.json. Janela observada: 223,1 segundos, aproximadamente 3,7 minutos.

| Evidência | Valor |
|---|---:|
| Ações únicas | 813 |
| Passos concluídos | 758 |
| Passos interrompidos | 55 |
| Colisões registradas | 0 |
| Escolhas diferentes verificadas por RAM | 22 |
| Dessas escolhas, passos concluídos | 21 |
| Dessas escolhas, passos interrompidos | 1 |
| Escolhas diferentes verificadas por Memoria.ia recuperada | 0 |
| Chegadas a objetivo final | 0 |
| Endereços de RAM reutilizados causalmente pelo menos duas vezes | 2 |

Os 55 interrompidos tinham motivo new_decision; isso não prova mudança de objetivo ou falha física. O contador cumulativo nativo durante a verificação mostrou 33 reutilizações causais na sessão atual, 512 entradas de RAM e três promoções residentes. As três promoções foram confirmadas pela sincronização anteriormente; esse contador não equivale a três novas promoções nesta janela.

## O que é demonstrado e o que falta

A RAM influencia escolhas físicas reais e há passos bem-sucedidos após a escolha. Não há controle executado para a alternativa sem memória, portanto não foi medida redução causal de distância ou de tempo na live. O ganho de aproximadamente 61% de percurso da 008CL continua sendo resultado do experimento isolado.

Os zero usos causais de Memoria.ia nesta janela não significam que a consulta não funciona: o cache público contém 200 registros recuperados. Também não provam ausência de influência em toda a execução, pois o arquivo de episódios é uma janela limitada.

Repetir uma célula quantizada não garante o mesmo início, objetivo, terreno ou estado de navegação. Não se compara média de duração de passos da RAM com passos da percepção como se fosse teste controlado.

A próxima prioridade é obter percursos naturais concluídos e comparáveis, identificando objetivo e condições estáveis e distinguindo desvio temporário de progresso final. Isso permite avaliar o uso da memória de disco sem atribuir à aprendizagem decisões já impostas pela percepção.

## Execução

`PYTHONDONTWRITEBYTECODE=1 python3 /home/etbra/live.infinita/tools/audit_live_navigation_008cm.py --report /home/etbra/nov-navigation-audit.json`

O comando apenas lê os episódios e escreve o relatório solicitado. Não exige instalação em /opt nem reinício de serviços. O resultado publicado no repositório é uma fotografia desta análise; não é atualizado automaticamente.

Validação: 61 testes Python, incluindo não atribuir acordo à memória, separar passo de objetivo, não contar interrupção como sucesso, deduplicar evidência e recusar alteração da mesma identidade.
