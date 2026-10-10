# 008FK — orçamento durável de exploração, incluindo interrupções

A regra experimental de 008FJ limitava amostras medidas. Esta etapa acrescenta um registro privado de execução para limitar os inícios de exploração, inclusive quando a tentativa não produz resultado de aprendizagem.

## Comportamento implementado

`nov_animal_exploration_guard.py` valida a decisão pelo seletor existente e grava uma reserva antes de devolver autorização para iniciar a tentativa. No máximo quatro reservas de exploração são permitidas por mundo e período lógico de cinco minutos. O orçamento é compartilhado pela revalidação de custo e pela reavaliação após falha.

A gravação usa arquivo selado com checksum, troca atômica, permissões 0600 e trava de arquivo para concorrência local. Uma falha na persistência impede a devolução de uma autorização. O estado é limitado a 16 mundos, com quatro reservas por mundo no período atual.

Uma reserva pendente bloqueia outra autorização, mesmo se o relógio atravessar o limite do período. Para encerrá-la é necessário um registro real do histórico de execução com o mesmo mundo, animal e instante inicial. O encerramento é idempotente; alteração de resultado, vínculo incorreto, token desconhecido, relógio regressivo ou corrupção do registro são rejeitados.

As reservas são intenções de execução, não fatos sobre o movimento. Uma interrupção encerra a reserva e mantém o orçamento consumido, mas não fabrica distância, instante final ou sucesso. O orçamento esgotado devolve uma escolha de percepção sem autorização para exploração; ele não proíbe a caminhada normal.

## Validação física

Dois casos independentes usam quatro aproximações iniciais balanceadas, o coletor de contexto Godot e o núcleo SQLite real.

| Caso | Execução | Resultado verificado |
|---|---|---|
| Interrompido | Quatro trajetos encerrados após cinco passos físicos | Todas as reservas continuam consumidas; nenhuma quinta exploração autorizada |
| Concluído | Quatro novas amostras concluídas e uma escolha posterior | Reservas encerradas; quinta escolha usa o custo recente, sem nova exploração |

No caso interrompido, o processo Godot termina com o checkpoint de tentativa pendente. Uma nova execução carrega esse checkpoint e arquiva `renderer_restart` com distância e instante final desconhecidos. Esse registro real encerra a reserva como interrupção. O arquivo de contexto continua sem fatos novos e o núcleo mantém exatamente os quatro fatos iniciais, também após reabertura e remoção do cache.

No caso concluído, os resultados reais encerram as reservas e são incorporados ao núcleo pela ponte existente. A quinta aproximação continua normalmente, orientada pelo custo recente, sem consumir outra reserva de exploração. O núcleo termina com nove fatos: quatro iniciais e cinco concluídos.

## Evidência

- 17 trajetos com movimento físico: 13 concluídos e quatro interrompidos.
- Quatro recargas do histórico em novas execuções Godot.
- 13 fatos medidos efetivamente confirmados e recuperados do núcleo.
- 17 recuperações após reabertura do núcleo e remoção do cache, sem POST nessa fase.
- 76 testes Python, incluindo concorrência local, persistência, corrupção, relógio, idempotência e vínculos.
- Nenhuma interrupção incorporada como resultado de aprendizagem.
- Históricos selados, logs e registros das reservas preservados nesta pasta.
- Relatório `EXPLORATION_GUARD_008FK.json` reúne os dois casos.

Reprodução sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_exploration_guard_008fk.py --output-dir /home/etbra/008fk-repeat
```

## Escopo

O guard continua experimental e não tem chamada na produção. Os arquivos de teste e os núcleos são temporários e isolados. Nenhum serviço da live foi reiniciado ou modificado.

O teste cobre um ator de execução com trava local, não coordenação distribuída. A geometria é plana, os animais estão parados e o sensor acompanha o último ponto observado; a câmera completa da live ainda precisa ser validada.

Antes de habilitar decisões na live, o consumidor deverá persistir a reserva antes do movimento e encerrá-la com o histórico real, como neste teste. A próxima etapa é reproduzir a atenção e a câmera reais e avaliar os resultados com esse orçamento completo.
