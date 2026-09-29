# MVP-018D — Espelho nativo BDR da Memoria.ia local (somente leitura)

O trabalho de engine e validação fica no repositório **Memoria.ia**, PRs
[#378](https://github.com/marceloroldao/memoria.ia/pull/378) e
[#379](https://github.com/marceloroldao/memoria.ia/pull/379). A Live guarda
somente o instalador/validador operacional, sem duplicar a lógica do banco.

## Sem mudança de backend

A instância local continua em SQLite incremental no endpoint
\`127.0.0.1:8788\`. O comando cria uma nova pasta de espelho privado;
não altera a API, a chave local, o checkpoint, o ledger do mundo, o
systemd, o Godot ou o processo autônomo. O mirror consulta a fonte SQLite
pelo modo \`ro\` e usa o backup online consistente, incluindo o WAL.
Só escreve os arquivos BDR no destino, executando como \`liveinfinita\`.

Pinos imutáveis:
- Memoria.ia: \`cf699e2daf8f91a97f05892abd58890f11c4acbe\` (espelho validado).
- Resolutive-DB v1.2.0-rc4:
  \`317882a00f041fc1568ff986af8016b09453f21a\`.
- Lib nativa compilada na VM com \`g++\`; extrai apenas o pacote de
  cabeçalhos \`zlib1g-dev\` em \`/tmp\` por \`apt-get download\` e \`dpkg-deb -x\`.
  Não instala pacotes nem altera o ambiente global.

Primeiro testa a biblioteca ABI v2 e o espelho completo com observações
sintéticas e SQLite WAL temporário **antes de sudo**. Em seguida, o operador
autoriza a cópia somente do código auxiliar para
\`/opt/live-infinita-bdr-mirror/<SHA>\` e a execução uma única vez.

## Como executar depois de merge e CI

Como usuário \`etbra\`:

\`\`\`bash
cd ~/live.infinita && bash deploy/mvp018d-bdr-read-only-mirror.sh
\`\`\`

A saída de sucesso:
- \`MVP018D_REAL_NATIVE_SCRATCH_PREFLIGHT_OK\`
- \`V2_BDR_READ_ONLY_MIRROR_OK\`
- \`MVP018D_MIRROR_REPORT_VERIFIED\`
- \`MVP018D_BDR_READ_ONLY_MIRROR_OK output=...\`
- \`MVP018D_NO_CUTOVER\`

O relatório privado fica em
\`/var/lib/live-infinita/memoria-local/bdr-mirror-runs/<execução>/report.json\`.
Ele contém somente contagem, hashes, tempo, tamanhos e confirmação de replay;
não imprime observações ou credenciais. A fonte original pode continuar
recebendo episódios durante a captura. Por isso, a contagem do relatório
representa **o snapshot capturado**, não uma sincronização contínua.

**Este comando não ativa o BDR em produção.** O SQLite permanece sendo o
destino do sincronizador, e o BDR um espelho derivado para auditoria.
Não há geração de uma cópia nova caso a mesma pasta de código já exista;
uma segunda execução exige procedimento explícito de revalidação. Em falha
não apagar a pasta de espelho: manter os arquivos para diagnóstico, sem
apontar os serviços existentes para eles.

## Gate antes de uma futura troca

É necessário comparar a fonte inteira e as relações reais, medir espaço,
validar durabilidade/reabertura com o banco em crescimento e preparar
reconciliação do delta posterior ao snapshot e rollback do adaptador.
A autoridade do World State jamais migra para o armazenamento cognitivo.
