# 008DG — Painel direto e amostras independentes por caminhada

Retira a frase solicitada do painel. Durante uma jornada ativa, o painel nativo e a página /godot mostram a distância percorrida na caminhada atual, em vez de exibir o resultado da chegada anterior como situação atual. O transporte de status agora preserva distance_m e active, validando distância finita e não negativa. O comportamento de aguardar dados recentes permanece.

## Qualidade da experiência

Uma escolha repetida no mesmo endereço dentro de uma jornada completa fornece somente uma amostra de custo. A primeira saída realmente executada é usada, incluindo todo o custo posterior do circuito; a atualização não escolhe a revisita mais barata e não multiplica a confiança dentro de uma única caminhada.

Uma caminhada posterior fornece outra amostra independente. A média continua limitada a 32 observações, conservando a adaptação a experiências recentes.

Os custos antigos persistidos, que podiam contar visitas repetidas, são conservados como uma estimativa prévia única na próxima atualização. Novas estatísticas registram sample_unit=completed_journey, preservado junto com o custo na Memoria.ia. A mudança não apaga promoções nem fabrica suas provas de reutilização causal.

As validações físicas, a câmera, o narrador central, a audiência e o logo são mantidos. Os custos continuam sendo atualizados somente em caminhadas completas elegíveis; custos sozinhos não promovem lembranças.

## Verificação

24 verificações Godot e 105 testes Python passaram, incluindo transporte da distância atual e rejeição de valores inválidos. O novo teste Godot cobre circuito repetido, custo completo da primeira saída, segunda caminhada independente, limite de influência, migração de contagens antigas, ausência de promoções fabricadas e apresentação da distância atual.

O comparativo reutiliza o protocolo físico da 008DF com o código atual e os novos critérios. Cinco experiências realmente promovidas foram gravadas pela API em SQLite isolado e recuperadas por outro processo, com IDs, destinos e qualidade conferidos.

| Cenário | Sem experiências | RAM | Memoria.ia após reinício |
|---|---:|---:|---:|
| U original | 40,5753 m | 20,0518 m | 20,0518 m |
| Passagem aberta | 6,0000 m | 6,0000 m | 6,0000 m |
| Passo aprendido bloqueado | 53,7431 m | 30,8435 m | 30,8435 m |

As 18 avaliações chegaram sem colisões nem busca global. A nova aquisição promove um conjunto diferente de passos, por isso a posição do obstáculo colocado sobre um passo lembrado pode mudar entre versões. A tabela é uma comparação entre modos desta aquisição, não uma medição pareada de melhoria contra a 008DF.

O relatório completo fica em LEARNING_PROGRESS_EVIDENCE_008DG.json.gz, e o resumo com hashes e resultados em LEARNING_PROGRESS_RESULT_008DG.json.

Antes desta atualização foi verificado 008DF_OK no registro do servidor. Naquela sessão, o status observado tinha duas chegadas, zero bloqueios físicos e zero escolhas causais por RAM/Memoria.ia. São dados de uma janela da execução, não o histórico completo. Este documento não declara que a 008DG já foi instalada.

## Instalação

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-learning-progress-008dg-root.sh
```

O instalador recompila a página, instala os módulos nativos e o exportador de status, reinicia o renderizador e verifica a publicação. Usa backup e restauração em caso de falha. O registro fica em /home/etbra/008dg-renderer-rollout.log; a confirmação é 008DG_OK.
