# 008FI — transferência para animais novos e limite do contexto

Experimento isolado: treinam-se quatro tentativas físicas e, depois, comparam-se cinco pares sem incorporar os resultados de avaliação à memória. O coletor e a ponte de 008FG usam o núcleo SQLite real; cada par consulta os mesmos quatro fatos recuperados após reabertura.

## O que foi observado

A escolha mudou para dez identidades de animais que não aparecem nos fatos de treinamento. A regra não consulta o histórico por identidade de coelho: usa faixa de distância, perfil físico e bloqueio inicial observado. Os resultados de transferência ficam dentro das faixas já treinadas.

| Cenário | Velocidade | Distância próxima / distante | Cerca | Resultado |
|---|---:|---:|---|---|
| Animais 20/21 | 2 m/s | 14 / aproximadamente 21 m | 60 m, a 6 m | Falha evitada |
| Animais 40/41 | 6 m/s | 17 / aproximadamente 23 m | 100 m, a 6 m | Falha evitada |
| Animais 60/61 | 4 m/s | 15 / aproximadamente 22 m | 70 m, a 7 m | Falha evitada |
| Animais 80/81 | 4 m/s | 17,5 / aproximadamente 20,5 m | 90 m, a 5 m | Falha evitada |
| Animais 90/91 | 4 m/s | 16 / aproximadamente 22 m | 80 m, a 12,5 m | Escolha mais longa sem necessidade |

Nos quatro primeiros pares, a percepção escolhe o animal próximo e a aproximação falha; os fatos recuperados levam à escolha do outro animal, que é alcançado. O desvio, a perda de contato e o custo são medidos pela locomoção e pelo sensor físicos; não se atribui falha artificialmente ao obstáculo.

O quinto caso revela um limite: o animal próximo é alcançável antes da cerca. A percepção confirma a aproximação após cerca de 9,8 m, enquanto a memória mantém a escolha distante e percorre cerca de 15,8 m. Ambos têm sucesso, mas a memória gasta aproximadamente seis metros a mais.

A varredura de quatro metros está livre em todos esses cenários. O contexto atual não distingue a barreira a seis metros daquela a 12,5 m. As experiências antigas, portanto, também podem provocar uma preferência inadequada. Esse resultado deve permanecer junto das evidências favoráveis.

## Método

- Quatro tentativas iniciais, agendadas de forma balanceada: duas falhas e dois sucessos, com animais 0/1 e velocidade de 4 m/s.
- 14 aproximações físicas no total: quatro de aquisição e dez de avaliação.
- Quatro fatos efetivamente confirmados e recuperados do núcleo.
- Nove recuperações após reabertura do núcleo e remoção do cache, sem POST nessa fase.
- Cinco pares com os mesmos candidatos, contexto, estado físico e parâmetros entre controle e memória.
- Identidades de avaliação ausentes no treinamento; inverter a ordem dos candidatos não muda a decisão.
- Ablação de memória vazia restaura a escolha pela percepção.
- Resultados dos pares são medidos e arquivados, mas não entram no núcleo; a contagem permanece quatro, evitando contaminação da avaliação.
- Nenhuma construção de rota global, contato físico ou captura nos trajetos verificados.

O arquivo selado original do coletor é preservado para cada tentativa. `NATIVE_TRANSFER_008FI.json` contém decisões, referências estruturais, medições e controles. O teste é considerado aprovado quando detecta tanto os quatro casos favoráveis quanto a escolha mais longa do quinto caso; aprovação não significa ausência de regressão comportamental.

Reproduzir sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_native_transfer_008fi.py --output-dir /home/etbra/008fi-repeat
```

## Limites e próxima correção

São cinco cenários desenhados, não uma estimativa estatística de sucesso. Terreno plano, animais parados, velocidade constante e atenção do sensor ao último ponto observado. Isso não reproduz a câmera completa da live nem demonstra caça ou generalização para novas faixas de distância.

A Memoria.ia guarda e recupera os fatos; a pontuação e a escolha pertencem ao seletor experimental. O teste comprova transferência limitada entre identidades e parâmetros, e também sobreaplicação do mesmo padrão.

A próxima correção deve permitir revalidar preferências mesmo quando elas continuam produzindo sucesso: uma escolha pode ficar mais cara sem gerar falha. Um orçamento controlado de exploração e resultados recentes de custo devem ser avaliados antes de ativar essa influência na live.

A live permanece em 008FG, apenas coletando contexto. Este experimento não instala código, reinicia serviços nem modifica o núcleo de produção.
