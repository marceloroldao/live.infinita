# MVP-018O — correção de isolamento do snapshot V2 sob systemd

## Resultado real do primeiro ensaio

O journal do canary temporário mostrou **12/12 abstenções**, 10 avanços
de tick, zero leituras prontas e sete estados `blocked`. O monitor teve
mediana 1,382 ms, mas máximo 335,819 ms (> gate de 250 ms). A unidade
temporária, seu processo e o release foram removidos; os três serviços
existentes permaneceram ativos. O relatório público
`MVP018O_CANARY_GATE_BLOCKED` indicou apenas
`readiness_or_accounting`. Não houve instalação permanente.

Inspeção de código apontou incompatibilidade com o sandbox:
`recall_once` cria `nov-recall-*` sob `private_root`, mas a unidade
montava a memória de produção `/var/lib/live-infinita/memoria-local`
como somente leitura. O erro exato foi engolido pela thread e **a
causalidade ainda não foi comprovada pelo journal**. O novo ensaio
mantém a raiz operacional somente leitura e publica exclusivamente
categorias fixas de falha, sem mensagens privadas.

## Correção

A V2 aceita agora um parâmetro opcional `scratch_root` **somente para
snapshot temporário e reidratação local**, não para mover o banco original.
Se informado, o diretório deve ser absoluto, não symlink, proprietário
do UID do processo, modo estrito 0700 e externo a `private_root`.
A cópia SQLite ocorre com backup de conexão `mode=ro`, verifica
integridade e checkpoint contra EvidenceCore da versão pinada; o arquivo
operacional continua intacto. `TemporaryDirectory` apaga a cópia no
final, inclusive após exceção.

A unidade do preparador tem `RuntimeDirectory=live-infinita-nov-preparer`,
`RuntimeDirectoryMode=0700` e seu **único** caminho gravável permitido
é `ReadWritePaths=/run/live-infinita-nov-preparer`. A raiz da memória
e a do mundo continuam explicitamente em `ReadOnlyPaths`, sem
`ReadWritePaths` operacionais. O `ExecStart` injeta o scratch fixo
`--scratch-root /run/live-infinita-nov-preparer`; a CLI recusa outro
caminho. No uso histórico fora do systemd (diagnósticos manuais), o
comportamento anterior continua opcional e inalterado.

O preparo assíncrono continua fora do tick autoritativo. Quando falha,
só enumera `scratch_permission`, `sqlite_validation`,
`typed_validation` ou `unexpected_failure`, nunca uma mensagem de
exceção, ID ou payload. Contextos bloqueados permanecem em abstenção.

## Gates automatizados e de operação

- Testes reais do núcleo V2 pinado executam snapshot/reidratação
  separado com raiz operacional sem permissão de criação de diretórios
  e verificam bytes originais de SQLite e checkpoint, remoção do
  diretório temporário e contagem de observações invariantes.
- Testes rejeitam scratch aninhado, symlink ou permissões públicas;
  renderer exige que /run seja o único destino gravável.
- A VM possui espaço suficiente em /run para o orçamento conservador
  existente de 512 MiB do snapshot; o gate de capacidade continua
  fail-closed se o espaço diminuir.
- O canary systemd continua finito (12 ciclos, ~24 s),
  `Restart=no`, sem seção de instalação, 250 ms máximo por step,
  384 MiB máximo, duas leituras prontas e progresso de tick.

Executar após CI/merge na VM:

```bash
cd ~/live.infinita && bash deploy/mvp018o-nov-systemd-canary.sh
```

O script pede autenticação do operador via sudo no terminal, publica
somente relatório 0600 `~/nov-memory-systemd-canary.log` e faz
rollback automático. No sucesso devem aparecer:
`MVP018O_CANARY_GATE_OK`, `MVP018O_SYSTEMD_FINITE_TRIAL_OK`,
`MVP018O_ROLLBACK_OK` e `MVP018O_NO_PERMANENT_UNIT_OR_CUTOVER`.
Ainda será necessário confirmar o journal real: testes de modo 0500
simulam falta de escrita, mas não substituem mounts systemd nem testes
concomitantes de WAL. Nenhum serviço permanente, IPC ou provider live
está autorizado nesta etapa.
