# 008DA — Verificar a chegada e liberar o destino físico

A navegação podia classificar como progresso um ponto já visitado a menos de três metros do objetivo, mesmo sem conexão física até o destino. Além disso, a resolução local do destino considerava água e limites, mas não a ocupação pela cápsula do corpo: um alvo dentro de um tronco continuava sendo aceito.

## Mudança

A busca local conecta o objetivo exato, inclusive fora da grade, quando uma origem ou nó observado está a até três metros dele e o corredor completo passa pelo verificador físico. Essa conexão tem prioridade sobre continuar ou retornar pela fronteira. O destino exato é acrescentado aos pontos do caminho. A busca continua dividida em fatias e limitada à mesma janela de 64 por 64 metros.

Sem conexão validada, a proximidade de três metros deixa de tornar novo um ponto de cobertura já visitado. Isso remove uma causa de retorno ao mesmo ponto, sem impedir a exploração de fronteiras realmente novas.

Quando o corpo do renderizador está disponível, resolver um destino passa também a testar sua cápsula inteira no espaço físico. Um ponto ocupado é deslocado para um ponto livre dentre os mesmos candidatos locais de até dezesseis metros. Se nenhum candidato estiver livre, a rota é rejeitada. A referência ao corpo é fraca para não reter objetos liberados.

A consulta de ocupação não exige que o caminho direto do observador até o destino esteja livre: um destino livre atrás de uma árvore continua válido e requer um desvio. Os passos executados mantêm os limites anteriores de altura, água e colisão. Nenhuma coordenada de ponte foi introduzida no planejador. A posição recebida do feed e o World State não são alterados.

## Evidência

Comparação isolada com as classes anteriores do commit f762f24:

- objetivo bloqueado e cobertura conhecida: antes, modo progress com um ponto; depois, modo none com nenhum ponto;
- alvo no centro do mesmo tronco físico: antes, aceito sem ajuste em (-80,0,0); depois, ajustado para (-78,0,0).

No teste físico novo, Nov saiu de (-88,0,0), contornou esse tronco e chegou ao destino ajustado após 11,2721 m, sem colisões ou sobreposição com o tronco.

O teste também verifica objetivo fora da grade, prioridade de uma conexão real sobre retorno de fronteira, destino realmente alcançável dentro de cobertura visitada, região totalmente ocupada sem alternativa em dezesseis metros, chegada em subida por passos permitidos e permanência do conector final dentro da janela observada.

Os vinte e um testes Godot da publicação passaram com código de saída zero e sem erros de script, incluindo câmera 008CW, obstáculos 008CV, coerência de passos 008CU, exploração distante 008CX e atalhos 008CY. Esta etapa não alterou código Python.

## Limites e instalação

Os casos reproduzem duas falhas do código e comprovam a correção nessas geometrias. Não demonstram que toda repetição observada na live teve essas causas nem garantem que qualquer destino no mapa seja alcançável. O ganho na live depende de novos percursos após a instalação. A decisão permanece por percepção; não é prova de aprendizado causal da Memoria.ia.

```bash
cd /home/etbra/live.infinita
git pull --ff-only
sudo bash deploy/apply-goal-approach-008da-root.sh
```

O instalador testa e exporta em cópia isolada, faz backup, atualiza a página e o renderizador e restaura a versão anterior se houver erro. A confirmação final é 008DA_OK no arquivo /home/etbra/008da-renderer-rollout.log. A preparação no GitHub não instala a versão.

Depois da instalação, usar a auditoria 008CZ por sessão para conferir chegadas, repetições e evidência causal separadamente.
