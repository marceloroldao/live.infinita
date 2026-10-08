# 008EP — explorar quando o custo aumenta

Política experimental isolada que compara os novos custos físicos com a média das duas primeiras observações do mesmo lado e assinatura. Se o custo excede 1.5 vezes essa referência e cresce mais de uma unidade de custo (3 m), começa uma janela nova de avaliação. As observações antigas permanecem intactas. A janela pede duas observações reais de cada lado antes de recomendar; propostas de exploração não contam como aplicação de preferência aprendida. Física, sensores, fronteiras, resgates, assinatura e perfil dos fatos não mudam.

Não foi instalada em produção. O núcleo SQLite real guarda os mesmos fatos físicos; a seleção desta janela é feita no aplicativo, não uma nova capacidade semântica autônoma do núcleo.

| Abertura | Economia nas 12 tentativas contra 008EO | Economia de tempo simulado |
|---|---:|---:|
| -20 | 737.84 m | 221.4 s |
| 0 | 248.16 m | 74.4 s |
| 10 | -0.00 m | -0.0 s |

Em z=-20, as escolhas do lado caro caíram de 8 para 2; a primeira exploração do outro lado passou da tentativa 9 para a 2, e a preferência nova em RAM apareceu na tentativa 5 (antes 11). Em z=0, as escolhas caras caíram de 4 para 2; primeira exploração na 2 e preferência nova na 5. Em z=10, a preferência antiga continuou melhor; houve duas explorações mais caras em ambos os braços, apenas em momentos diferentes, e o custo total das 12 tentativas ficou igual. A decisão final foi preservada.

Total medido: 986.00 m e 295.8 s simulados a menos nos três conjuntos de 12 tentativas. É redução do custo de adaptação frente à política anterior, não benefício líquido desde uma memória vazia, nem vantagem em produção. Em z=-20 e z=0 ainda há duas tentativas caras; a adaptação não é instantânea. A aquisição completa foi registrada nos JSONs.

Após reabrir os núcleos temporários e remover os caches, os três braços usam preferência recuperada: z=-20 e z=0 escolhem +1, coincidindo com a percepção; z=10 escolhe -1 e preserva a economia de 103.61 m por travessia contra a percepção. Os conjuntos armazenam 21 fatos físicos por núcleo, sem reingestão na recuperação. Cada braço também repete duas comparações do cenário original: o ganho original permanece.

## Validação e limites

As três execuções físicas passaram, com 36 tentativas de adaptação, verificações finais em RAM e no núcleo reaberto, zero colisões/resgates/busca global. O teste unitário sintético passou: dados estáveis não disparam mudança, previsões são recusadas, avaliações repetidas não criam crédito, fatos antigos permanecem, exploração é identificada separadamente e uma opção que ainda é melhor é preservada. Dados sintéticos do teste unitário não são evidência de aprendizado físico. Sintaxe Python/shell, resumo e diff foram verificados.

O limiar 1.5 e a amostra de duas experiências são escolhas de política, não parâmetros aprendidos. O teste assume uma mudança por assinatura; a primeira mudança permanece como início da janela. Ainda falta validar mudanças sucessivas, variação normal do custo, dados fora de ordem, ruído, censura de contatos e falhas físicas. Não é uma solução geral de detecção de mudanças.

Apenas arquivos de teste, ferramenta de medição, script de execução e evidência foram adicionados; nenhum arquivo da aplicação de produção foi modificado. A live permanece ativa na 008EM.

Repetir: `bash /home/etbra/measure-cost-shift-008ep.sh`. Resultados em `/home/etbra/008ep-results/`. JSON de comparação, três conjuntos de logs físicos e teste unitário estão em `docs/COST_SHIFT_008EP/`. O runner permite `--resume` para refazer apenas a síntese ou completar cenários faltantes. Não há timer ou monitoramento automático.

Próximo passo antes de instalação: validar uma segunda alteração na mesma situação e retorno ao estado anterior, para não manter uma janela de comparação obsoleta.
