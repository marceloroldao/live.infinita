# 008EO — matriz de geometrias e custo de adaptação

Experimento isolado com Godot físico nativo e núcleo Memoria.ia SQLite real, usando a política 008EM. Três variantes de abertura previamente definidas: z=-20, z=0 e z=10. Início, destino, velocidade, sensores e parede permanecem iguais dentro de cada comparação. Cada variante tem núcleo e arquivos de memória isolados. Não altera a live ou a memória de produção.

A variante 008EN z=-10 já demonstrou que uma preferência antiga pode piorar quando a passagem muda. Esta matriz permite resultados em qualquer direção: não exige que a memória antiga seja pior ou que novas tentativas melhorem. Mantém obrigatórias a chegada física, ausência de colisão/resgate e ausência de busca global no fixture. Um primeiro ensaio falhou justamente por herdar a hipótese “preferência antiga piora” da 008EN: em z=10 ela era melhor. Essa hipótese foi removida para medir o efeito, e o ensaio foi repetido. Não houve erro de colisão nesse caso.

Cada variante mantém 12 tentativas em RAM, uma verificação adicional que gera observação física e um teste após reabrir o núcleo e remover o cache. São 21 observações físicas armazenadas por núcleo: oito calibrações e treze travessias no cenário alterado. Os controles não entram nas observações de adaptação.

Distinguir três mecanismos: preferência recuperada aplicada, preferência recuperada que coincide com a percepção e abstenção por margem insuficiente. Coincidir com a percepção não prova vantagem sobre ela. As etiquetas técnicas “repaired” herdadas do runner 008EN significam teste após novas tentativas; não asseguram que ocorreu correção.

O relatório mede distância e tempo de cada braço, custo de aquisição, diferenças acumuladas das 12 tentativas contra a percepção e fonte/motivo da decisão posterior. “Primeira tentativa com o lado da percepção” não significa primeira escolha ótima: na variante z=10 a própria percepção percorre mais distância. A geometria e a política de contorno podem inverter essa relação.

São variantes determinísticas de uma mesma parede em terreno plano; não são amostras independentes e não cobrem relevo, rios, fauna, percepção ruidosa ou falhas físicas. Não demonstram benefício líquido em produção nem validam a penalidade de colisão/resgate.

Repetir com `bash /home/etbra/measure-adaptation-matrix-008eo.sh`. Saídas em `/home/etbra/008eo-results/`. O runner aceita `--resume` para reutilizar as capturas concluídas, recalcular a síntese e executar só variantes faltantes. Não há monitoramento automático.

## Resultados medidos

| Abertura z | Percepção | Memória antiga | Após tentativas e reabertura | Decisão posterior |
|---|---:|---:|---:|---|
| -20 | 92.31 m | 215.29 m | 92.31 m | preferência recuperada |
| 0 | 129.72 m | 253.80 m | 129.72 m | abstenção; percepção |
| 10 | 377.79 m | 274.18 m | 274.18 m | preferência recuperada |

Em z=-20, a primeira escolha do lado da percepção ocorre na tentativa 9, por abstenção; a preferência nova em RAM aparece na 11. As 12 tentativas acumulam 983.79 m e 295.2 s a mais que a percepção. Após recuperação do núcleo, a preferência coincide com a percepção: corrige a perda antiga, sem ganho sobre o baseline.

Em z=0, o lado da percepção aparece na tentativa 5 e a preferência nova em RAM na 8. As 12 tentativas acumulam 496.32 m e 148.8 s extras. Após reabertura, o núcleo recupera as quatro observações originais mais as 17 observações da fase seguinte; com esse conjunto mais amplo, a margem fica insuficiente. Nov usa a percepção. Isso não é prova de aplicação de uma preferência corrigida nesse braço.

Em z=10, a preferência antiga já é melhor: 274.18 m/82.3 s contra 377.79 m/113.3 s. A recuperação posterior mantém -1 e muda a decisão inicial em relação à percepção, preservando 103.61 m e 31 s de economia por travessia. A política de contorno e suas reversões tornam inadequado supor que o lado +1 seja sempre melhor só porque a abertura está acima.

As três execuções físicas completas passaram, incluindo duas repetições pareadas do cenário original por variante, 36 tentativas de adaptação e três verificações após reabertura do núcleo com cache removido. Foram armazenados 63 fatos em três núcleos temporários distintos. Resultados e logs estão no subdiretório ADAPTATION_MATRIX_008EO. Validação da síntese confirma contagem, cálculo do custo, recuperação sem reingestão e ausência de colisões/resgates. Sintaxe Python/shell e diff verificados. A live permanece no build bc3c580, ativa e sem reinícios automáticos.

Próximo alvo experimental: detectar aumento de custo e antecipar exploração limitada, preservando a preferência antiga quando ela ainda ajuda. Comparar o custo acumulado das tentativas, não apenas a travessia final. Não foi alterada a política em produção nesta etapa.
