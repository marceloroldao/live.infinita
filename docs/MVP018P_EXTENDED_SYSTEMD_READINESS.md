# MVP-018P — validação prolongada no sandbox systemd, no ritmo de produção

## Evidência de entrada

O segundo teste real do MVP-018O, com scratch separado e a memória
operacional somente leitura, produziu **uma** leitura pronta em 12 amostras:
cinco lembranças primárias e três suplementares, com 3/3 coincidências
registradas. Houve sete estados `pending`, quatro `query_changed`,
quatro envios e 11 avanços de tick sem regressão. O máximo de
`step` foi 163,308 ms, abaixo do limite de 250 ms, mas o gate
`readiness_or_accounting` bloqueou corretamente por exigir pelo menos
duas leituras prontas. O rollback do systemd foi verificado.

Não tratamos uma única recuperação como demonstração de prontidão
contínua. Também não atribuímos causalidade a `pending` ou
`query_changed` sem ensaio adicional. O intervalo de 12 ciclos
contém apenas cerca de 24 segundos e pode capturar poucas janelas
entre mudanças do contexto observado.

## Ensaio controlado

A unidade temporária continua usando exatamente o modo contínuo
(`--period 2 --refresh 4 --scratch-root
/run/live-infinita-nov-preparer`), **sem `--canary` com espera
especial**. Só a duração finita mudou, de 12 para 60 ciclos, ou
aproximadamente dois minutos. A supervisão espera até 165 segundos
pela conclusão antes de aplicar rollback obrigatório.

O gate passa a exigir evidência sustentada: ao menos 12 leituras
prontas e 30% de prontidão nas amostras, até 20 amostras seguidas
sem contexto, cinco avanços ou mais e zero regressões de tick.
O limite de 250 ms por etapa, memória máxima de 384 MiB, ausência
de ações/BDR/sync central/escrita do mundo e integridade contábil
são preservados, sem qualquer relaxamento. O relatório redigido
inclui `status_counts`, `ready_fraction` e
`longest_not_ready_streak`, nunca IDs, endereços nem outcomes.

O contrato do scratch separado permanece: memória operacional e
World State somente leitura; apenas um RuntimeDirectory 0700 em
`/run` pode receber os backups V2 temporários. A unidade é
colocada só em `/run/systemd/system`, sem seção `[Install]`,
sem restart e sem comunicação com o tick autoritativo.

## Execução operador

```bash
cd ~/live.infinita && bash deploy/mvp018o-nov-systemd-canary.sh
```

O comando requer senha sudo no terminal e reescreve o relatório 0600
`~/nov-memory-systemd-canary.log`. Os marcadores de aprovação são
`MVP018O_CANARY_GATE_OK`,
`MVP018O_SYSTEMD_FINITE_TRIAL_OK`,
`MVP018O_ROLLBACK_OK` e
`MVP018O_NO_PERMANENT_UNIT_OR_CUTOVER`. Se bloquear, não repetir
automaticamente: coletar o último resumo `MVP018L_OWNER_STOPPED`
do journal e verificar rollback antes de mudar o desenho.

Aprovação desse ensaio comprova apenas a recuperação por período
finito sob restrições reais de systemd. Não comprova estabilidade
permanente, atualização imediata para todo ACK, melhora de decisão
do Nov ou segurança de IPC entre processos com mesmo UID.
A unidade permanente permanece não instalada.
