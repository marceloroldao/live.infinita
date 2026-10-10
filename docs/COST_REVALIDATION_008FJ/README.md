# 008FJ — revalidar custo mesmo sem falha

A correção experimental evita que uma preferência antiga permaneça indefinidamente apenas porque continua terminando em sucesso. Ela agenda novas amostras a partir dos fatos recuperados, compara o custo recente e mantém a reavaliação por falha de 008FF com prioridade.

## Regra implementada

O seletor `nov_animal_cost_revalidation.py` envolve o anterior, preservando a validação de percepção, identidades estruturais, tempos, duplicatas e escopo. A regra nova atende exatamente dois contextos conhecidos, com pelo menos dois fatos anteriores por contexto; memória vazia, contexto desconhecido ou outro número de contextos mantém o comportamento anterior.

O tempo lógico é dividido em períodos de cinco minutos. Para cada contexto, procura dois resultados medidos de tentativas iniciadas nesse período. Enquanto faltarem amostras, escolhe o contexto menos amostrado e, no empate, aquele cuja observação concluída é mais antiga. A escolha não depende da identidade do animal.

Depois das quatro amostras medidas, a comparação usa os resultados recentes pelo seletor anterior. Nenhum contador persistente em RAM é necessário: reiniciar a leitura do núcleo preserva o andamento porque os instantes das tentativas estão nos fatos recuperados.

O núcleo guarda e recupera fatos; essa regra de exploração e a pontuação pertencem ao seletor experimental. Não existe chamada nova na live.

## Comparação física

Foram executados dois casos independentes, cada um com quatro aproximações iniciais balanceadas e dez pares posteriores. Cada par começa com a mesma percepção e parâmetros físicos; um braço usa a revalidação e o outro mantém os quatro fatos iniciais congelados.

Somente os resultados físicos do braço adaptativo entram na memória. Antes da escolha seguinte, o núcleo é reaberto, o cache de leitura é removido e a recuperação ocorre pela API, sem POST nessa fase. Os controles ficam arquivados fora do núcleo para não influenciar as decisões.

| Caso | Total com revalidação | Total com preferência congelada | Resultado |
|---|---:|---:|---|
| Cerca passa de 6 m para 12,5 m | aproximadamente 110 m | aproximadamente 158 m | A preferência muda para o alvo próximo, reduzindo o custo |
| Cerca permanece a 6 m | aproximadamente 184,4 m | aproximadamente 158 m | A exploração custa mais; duas tentativas perdem contato |

No caso modificado, a escolha antiga continua tendo sucesso e não gera sinal de falha. A revalidação obtém duas amostras de cada contexto e depois escolhe o próximo nas seis tentativas seguintes. As dez tentativas adaptativas têm sucesso.

No caso estável, as amostras próximas voltam a falhar e o seletor mantém a preferência pelo distante nas seis tentativas seguintes. O braço adaptativo tem oito sucessos, contra dez do controle. Essa diferença é o custo de investigar alternativas sem informação antecipada sobre a mudança oculta; não deve ser omitida.

## Verificações

- 48 aproximações físicas: oito iniciais e 40 nos pares.
- 28 fatos medidos confirmados e recuperados do núcleo SQLite real.
- 28 recuperações após reabertura e remoção do cache, sem reingestão.
- Oito escolhas de revalidação no total, quatro por caso; as 12 escolhas posteriores encerram a revalidação daquele período.
- 68 testes Python de contratos, pontuação, revalidação, ponte e instalação.
- Nenhuma colisão, rota global ou captura nos trajetos verificados.
- O arquivo selado original do coletor Godot alimenta a ponte existente, sem adapter de resultado sintético.
- Relatório `COST_REVALIDATION_008FJ.json`, resultados por braço e logs nesta pasta.

Reproduzir sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_cost_revalidation_008fj.py --output-dir /home/etbra/008fj-repeat
```

## Limites e produção

Dois cenários desenhados, terreno plano, velocidade constante de 4 m/s, animais parados e atenção do sensor ao último ponto observado. O período de cinco minutos e duas amostras por contexto são regras explícitas de pesquisa, não parâmetros ótimos demonstrados.

O limite contabiliza resultados medidos. Tentativas censuradas não podem preencher essa quota; a integração de produção precisará limitar também tentativas interrompidas pelo histórico de execução. Mudanças repetidas dentro do mesmo período não foram testadas. A atenção e a câmera completas da live continuam fora deste experimento.

A live permanece com 008FG e influência contextual desligada. A verificação desta etapa encontrou as primeiras duas aproximações contextuais reais, confirmadas e recuperadas pela ponte. Esse dado comprova a operação da coleta e da recuperação; não comprova ganho da nova regra ao vivo.

Antes de instalar o seletor, falta validar o orçamento completo de tentativas, o custo de exploração em mais cenários e a integração com a atenção/câmera reais.
