# 008EN — comparação pareada e adaptação física

Teste isolado executado usando a política 008EM, cápsula física real do Godot, callbacks nativos do coletor, ponte de produção e núcleo Memoria.ia SQLite real. Não altera nem reinicia a live, não grava na memória de produção e não requer instalação root.

| Cenário | Sem padrões | Com padrões recuperados |
|---|---:|---:|
| Abertura original: distância | 234.57 m | 106.61 m |
| Abertura original: tempo simulado | 70.4 s | 32.0 s |
| Abertura movida, memória antiga: distância | 106.61 m | 234.57 m |
| Abertura movida, memória corrigida: distância | 106.61 m | 106.61 m |

No cenário original, duas repetições determinísticas deram a mesma redução: 127.97 m e 38.4 s (aproximadamente 54.6%). Dentro de cada par, início, destino, geometria, velocidade de 4 m/s, passo de 0.1 s e política física são iguais. A única intervenção é habilitar os padrões recuperados. Memória antiga usa lado -1; percepção usaria +1. Zero colisões, resgates e buscas globais nas travessias verificadas. Essas duas repetições não são amostras independentes nem demonstram generalização ampla.

A abertura passa de z=-110 para z=-10, mantendo o mesmo início e destino. A assinatura sensorial local é ambígua: a preferência antiga continua aplicável, mas agora aumenta o custo em 127.97 m. As seis primeiras tentativas de adaptação usam o lado antigo; da sétima em diante, usam o lado +1. Foram executadas 12 tentativas, seguidas de uma verificação em RAM que também gera uma observação física. A recuperação corrigida foi então testada após reabrir o núcleo e remover o cache exportado: chega em 106.61 m e 32 s, igual à percepção, recuperando a perda causada pela preferência antiga. Isso não significa ganho sobre a percepção no cenário alterado.

O núcleo armazena e recupera 21 fatos físicos: oito travessias de calibração (quatro em cada fase) e treze travessias no cenário alterado (12 tentativas e uma verificação em RAM). Essa aquisição custou 3514.93 m e 1054.8 s simulados. As economias de travessia acima excluem esse custo; não foi demonstrado benefício líquido desde a memória vazia. As travessias de controle não entram no aprendizado adaptado. Armazenamento e recuperação após reabertura foram idempotentes, sem reingestão. Associações semânticas continuam adiadas no contrato real do núcleo; o aplicativo calcula a preferência pelos custos físicos.

Este teste amplia a evidência: benefício causal da recomendação no cenário físico isolado, prejuízo quando a geometria muda e correção por novas experiências com persistência no núcleo. Não reproduz exatamente o contato observado na live e não comprova vantagem causal em produção. O ambiente é uma parede com abertura e terreno plano, sem relevo variável, rio, fauna ou percepção ruidosa. Não houve colisão ou resgate nesse experimento; ele mede custo de escolhas concluídas e não valida a penalidade de falhas físicas.

## Repetir

Executar `bash /home/etbra/measure-paired-adaptation-008en.sh`. Saídas em `/home/etbra/008en-paired-results/`. O script usa um projeto Godot separado e um núcleo temporário isolado; não há monitoramento automático.

## Validação

Execução completa do comando público em projeto separado passou, com todas as verificações físicas, as duas comparações pareadas, 12 tentativas de adaptação e recuperação corrigida após reinício. Sintaxe shell e diff verificados. A live permaneceu ativa no build bc3c580, sem reinícios automáticos. Os arquivos JSON e três logs brutos estão junto deste documento.

Próxima evolução: avaliar múltiplas geometrias alteradas, falhas físicas e política de exploração diante de aumento de custo, mantendo comparações pareadas e contabilizando a aquisição.
