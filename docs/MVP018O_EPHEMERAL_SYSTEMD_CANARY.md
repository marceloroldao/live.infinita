# MVP-018O — ensaio real do sandbox systemd, sem instalação permanente

## Base verificada

O MVP-018N corrigiu o template que apontava para um módulo inexistente em
`/opt/live.infinita/apps/world-runtime/`. O preflight de empacotamento passou
na VM e a Memoria.ia local permaneceu independente do mundo. O relatório
MVP-018M mais recente mediu 60 leituras prontas em 94 amostras, máximo de
4,168 ms por `step`, zero etapas acima de 250 ms; um pico anterior de
760,384 ms permanece sem causa determinada.

## Ensaio deste estágio

O comando do operador autentica `sudo` no próprio terminal e entrega o
commit atual a um script root de uso único. O script trava execuções
concorrentes, verifica `main` sem alterações rastreadas e recusa a
existência da unidade permanente ou de uma unidade de canary anterior.

Somente onze módulos Python públicos e o avaliador do canary são lidos
diretamente dos objetos do commit Git e copiados para
`/opt/live-infinita-nov-preparer/releases/<commit completo>` com
proprietário root, arquivos 0644 e diretório 0755. Nenhum arquivo de
`/var/lib/live-infinita/memoria-local` é copiado. O núcleo Memoria.ia V2
permanece fixado na versão implantada e o ambiente Python continua o
existente em `/opt/live.infinita/.venv`.

A unidade de teste herda as restrições de produção (usuário e grupo
`liveinfinita`, memória máxima 384 MiB, CPU/IO com baixa prioridade,
`NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, filesystem estrito,
raízes do mundo e memória **somente leitura** e rede IP negada).
Apenas `Restart=no`, `--cycles 12` e a remoção da seção
`[Install]` distinguem este ensaio da unidade permanente.

A unidade é colocada apenas em
`/run/systemd/system/live-infinita-nov-memory-prepare-canary.service`.
O script chama `systemd-analyze verify`, recarrega a configuração de
unidades e executa por aproximadamente 24 segundos. Não habilita a
unidade, não inicia a unidade permanente e não injeta o provider no
`autonomous_runtime_main.py`.

No fim, lê o journal da unidade e aceita um único resumo
`MVP018L_OWNER_STOPPED` tipado. O gate exige doze ciclos, pelo menos
duas leituras prontas, progresso de tick sem regressões, relatórios
contábeis consistentes, máximo de 250 ms por chamada e RSS abaixo de
384 MiB. Ausência de evidência, alteração do mundo ou qualquer alegação
de autoridade decisória bloqueia o resultado. Logs publicados ao
operador contêm somente códigos e contagens agregados, sem endereços,
IDs, hashes, outcomes ou payloads.

A limpeza é obrigatória mesmo se falhar um gate: tenta parar a unidade,
confere PID inativo, remove a unidade temporária, recarrega systemd e
remove apenas o diretório de release criado por aquela execução. Se o
processo não parar, **não remove código sob um processo vivo** e informa
rollback bloqueado; requer intervenção manual de investigação.

## Execução operator-only

```bash
cd ~/live.infinita && git pull --ff-only && bash deploy/mvp018o-nov-systemd-canary.sh
```

Os marcadores esperados, em `~/nov-memory-systemd-canary.log` (0600),
são `MVP018O_ROOT_RELEASE_OK`,
`MVP018O_EPHEMERAL_UNIT_READY`,
`MVP018O_EPHEMERAL_UNIT_RUNNING`,
`MVP018O_CANARY_GATE_OK`,
`MVP018O_SYSTEMD_FINITE_TRIAL_OK`,
`MVP018O_ROLLBACK_OK` e
`MVP018O_NO_PERMANENT_UNIT_OR_CUTOVER`.
Se o processo não puder ser parado, nunca tratar a ausência de marcador
de sucesso como aprovação.

Este ensaio prova execução e limpeza da unidade sob as restrições reais
do systemd, **não** horas de estabilidade, retorno de todas as novas
observações, IPC autenticado ou melhora cognitiva. A unidade permanente
continua não instalada. Para compartilhar contextos com Shadow Mode,
ainda é necessário separar principal de acesso e definir limites,
proveniência, TTL, mundo/tick, autoridade e abstenção: ambos os processos
atuais usam o mesmo UID, portanto `SO_PEERCRED` por UID isolado não
diferencia o emissor autorizado.
