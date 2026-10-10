# 008FM — escolhas recuperadas com animais em movimento

Esta etapa testa aproximação com animais que se deslocam fisicamente. São dois corpos `CharacterBody3D` com consultas de colisão, avançando a velocidades constantes de 0,5 m/s ou 1,5 m/s. Não há implementação de alimentação, fuga autônoma, ecologia, caça ou captura.

Nov usa o movimento nativo, a orientação estabilizada do corpo compartilhada com a câmera e a cadência de percepção de 008FL. Somente o sensor físico produz posições observadas. O ambiente desloca os animais depois da decisão de Nov; velocidade e posição futura não são fornecidas ao controlador nem ao seletor. Os diagnósticos de movimento ficam separados dos candidatos enviados à decisão.

## Comparação controlada

Cada velocidade tem um núcleo isolado e quatro experiências iniciais balanceadas, medidas pelo coletor nativo. Os fatos são confirmados pela ponte existente no núcleo SQLite real. Após cada incorporação, o núcleo é reaberto, o cache removido e os fatos recuperados sem POST; a recuperação é comparada ao conteúdo medido.

Depois são realizados quatro pares de aproximações com novos identificadores de animais. Um braço escolhe com fatos recuperados; o controle escolhe o animal visível mais próximo, sem esses fatos. Os dois começam com as mesmas observações, geometria, velocidade e posições. Somente resultados do braço com memória são incorporados ao núcleo.

| Velocidade dos animais | Com fatos recuperados | Por proximidade | Caminhada com fatos | Caminhada por proximidade |
|---|---:|---:|---:|---:|
| 0,5 m/s | 4/4 aproximações | 0/4 aproximações | 73,6 m | 45,6 m |
| 1,5 m/s | 4/4 aproximações | 0/4 aproximações | 111,2 m | 117,6 m |

Nesta geometria, o animal mais próximo fica além de uma barreira longa. As experiências recuperadas favorecem o outro contexto de distância, alcançável mesmo com o animal em movimento. No ritmo lento, fracassar cedo dá uma distância menor ao controle; isso não representa melhoria. A comparação considera sucesso junto com distância.

O guard durável participa de todas as decisões. Neste ensaio, as escolhas usam evidência já disponível dentro do mesmo período lógico; nenhuma reserva de exploração é necessária. A interrupção e o orçamento do guard foram testados separadamente em 008FK.

## Evidência

- 24 trajetos físicos: oito aquisições e oito pares comparativos.
- 16 fatos confirmados e recuperados em 16 reaberturas do núcleo.
- Oito aproximações com fatos recuperados contra oito perdas de contato por proximidade.
- Posições finais comprovam deslocamento de ambos os animais em todos os trajetos.
- 46 testes Python de regressão aprovados; auditoria de fatos, movimento e decisões aprovada.
- Logs, arquivos selados, observações e relatórios por velocidade em `evidence/`.
- Relatório agregado: `evidence/MOVING_ANIMALS_008FM.json`.

O núcleo armazena e recupera fatos estruturais. O consumidor experimental calcula o custo e escolhe o contexto; isso não demonstra que o núcleo sozinho executa a seleção ou prevê trajetórias futuras.

São cenas pequenas, planas, diurnas e desenhadas, com velocidade de Nov fixa em 4 m/s. Não há transferência testada entre velocidades, mudança espontânea de direção, câmera renderizada completa, terreno carregado dinamicamente ou integração dessa política na live. O resultado demonstra efeito neste experimento, sem estabelecer benefício geral.

A live permanece com a política de escolhas desativada (`decision_use=false`), conforme `live-health.json`. Nenhum serviço foi modificado ou reiniciado. A próxima etapa deve testar mudanças de direção e perda/retomada da visão antes de conectar a política ao renderer público.

Reprodução sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_moving_animals_008fm.py --output-dir /home/etbra/008fm-repeat
```
