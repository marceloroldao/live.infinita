# MVP-015 — índice frio para planos encerrados (incidente #66)

## Evidência observada em produção

Em 28/09/2026, o JSONL de planos havia alcançado cerca de 330 MB,
aproximadamente 247 mil transições e 75.708 IDs distintos. Quase todos
os planos estavam encerrados. A implementação anterior construía primeiro
uma lista de TODO o histórico e mantinha o objeto integral da última versão
de cada plano, incluindo o plano, seus passos e contextos, em _view_by_id.
Essa representação retinha memória sem necessidade para o tick corrente.

A mesma VM tinha 4,2 GiB RAM, nenhum swap e dois OOM do processo
autoritatitivo registrados no kernel. O diagnóstico não prova que o
PlanLedger seja a única fonte de retenção; medir RSS após implantação
e continuar a investigação dos demais componentes.

## Contrato novo

O arquivo plans.jsonl NÃO é modificado, compactado nem removido.
No primeiro acesso, PlanLedger._iter_rows_with_offsets percorre o JSONL
em streaming e preserva por plan_id a posição em bytes do registro mais
recente. Em memória, o último objeto integral permanece SOMENTE para planos
não-terminais. Uma busca por ID encerrado abre o arquivo, faz seek(offset)
e valida que o ID lido coincide com o solicitado.

Preserva:
- ordem ORIGINAL de criação em current(), active(), eventos recuperados
  e candidatos de satisfação;
- idempotency keys por primeira correspondência e último registro;
- consulta de planos ativos sem percorrer antigos planos encerrados;
- pending_need_outcome_candidates(processed_ids) sem ler payload dos
  registros já processados;
- detachment de objetos retornados e índice invalidado por alterações
  externas;
- reparo somente de última linha parcial, falha fechada para corrupção no
  meio e fsync na escrita.

current() e history() continuam explícitos e completos para auditoria,
mas não são usados no ciclo normal. A primeira varredura de startup tem
custo de E/S proporcional ao tamanho do arquivo; histórico permanece
autoritativo e RAM quente cresce principalmente com planos ativos e índices
compactos de IDs/offsets, não com payloads de todos os planos históricos.

## Proteção operacional imediata

deploy/enable-live-swap-guard.sh cria idempotentemente swap de 2 GiB em
/swapfile-live-infinita, modo 0600, entrada única em /etc/fstab,
vm.swappiness=10, após validar disco. Execute como etbra pelo alias
~/enable-live-swap-guard.sh. Swap é proteção contra encerramentos
repentinos, não substitui otimização ou aumento de RAM. Não altera JSONL.

O deploy do índice deve ter preflight de swap ativo, testes e replay,
backup do módulo de produção, atualização cirúrgica e restart somente
do Single Writer. Verificar hash de replay, HTTP, PID, gate social, RSS
e ausência de novas falhas por OOM antes de declarar estabilidade.
