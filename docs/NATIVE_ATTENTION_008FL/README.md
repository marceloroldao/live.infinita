# 008FL — orientação real do corpo e reavaliação de custo

O teste anterior apontava o sensor para o último ponto observado do animal. Esta etapa usa os métodos de produção `_update_camera_heading` e `_orient_nov_visual`, com o sensor olhando na direção `nov.global_basis.z`. As varreduras respeitam o agendador de 0,25 s: com passos de 0,1 s, uma varredura acontece a cada três passos. Não há correção artificial do olhar para acompanhar o alvo.

A orientação é calculada pela mesma estabilização utilizada pela câmera da live. O teste não renderiza a câmera completa nem executa streaming de terreno, feed de rede ou aceleração variável. São cenas físicas isoladas, planas, diurnas, com dois animais parados, velocidade de 4 m/s e orientação inicial diagonal. Usa movimento nativo, colisões, desvio observado, coletor real e mundos separados dos experimentos anteriores.

## Comparação

Cada cenário recebe quatro experiências iniciais balanceadas. Depois são comparadas dez escolhas com reavaliação e dez com a preferência antiga congelada. Somente resultados do braço adaptativo entram no núcleo. As decisões de exploração passam pelo guard durável antes do movimento e são encerradas pelo resultado real. Quatro novas amostras são exploradas por cenário; as seis escolhas seguintes não consomem reservas de exploração.

| Cenário | Reavaliação: sucessos | Preferência antiga: sucessos | Reavaliação: distância | Preferência antiga: distância |
|---|---:|---:|---:|---:|
| Barreira alterada | 10/10 | 10/10 | 110,0 m | 158,0 m |
| Barreira mantida | 8/10 | 10/10 | 149,2 m | 158,0 m |

No cenário alterado, a reavaliação permite voltar ao animal próximo alcançável e reduz a caminhada mantendo os sucessos. No cenário mantido, duas explorações perdem o contato visual mais cedo e encerram o trajeto. A distância menor desses fracassos não representa melhoria: a taxa de sucesso piora. Comparar somente distância esconderia esse custo.

## Evidência e limites

O experimento completo executa 48 trajetos físicos e confirma 28 fatos medidos no núcleo SQLite real. Cada incorporação é seguida de reabertura do núcleo, remoção do cache e recuperação sem novo POST; o conteúdo recuperado é comparado aos fatos reais. Logs, arquivos selados, resultados físicos, relatórios por cenário e relatório agregado ficam em `evidence/`. O teste Python de regressão reúne 80 casos aprovados.

A coleta na live foi verificada separadamente em `live-health.json`. A política de escolhas permanece desativada na produção (`decision_use=false`). Nenhum serviço foi reiniciado nem houve alteração na versão publicada. A inferência e a seleção pertencem ao consumidor experimental; o núcleo armazena e recupera os fatos estruturais.

Essas cenas demonstram efeito condicionado ao cenário, não melhoria universal ou benefício já comprovado na live. Antes de habilitar escolhas públicas, falta conectar reserva e encerramento ao ciclo do renderer e testar câmera completa, animais em movimento e terreno variável.

Reprodução sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_native_attention_008fl.py --output-dir /home/etbra/008fl-repeat
```
