# MVP-018D — BDR espelho privado da Memoria.ia local (sem migração ativa)

O `resolutive-DB` nativo v1.2.0-rc4 é usado para **comparação de persistência**
com a Memoria.ia V2. Não se troca o backend em produção neste MVP. O serviço
local mantém `sqlite-incremental`, Nov continua com seu Single Writer e o
Godot não é reiniciado.

## Procedimento operacional

O operador, quando a revisão/CI for concluída, poderá executar **um comando**:

```bash
cd ~/live.infinita && bash deploy/mvp018d-bdr-shadow-mirror.sh
```

O script primeiro verifica os serviços e bloqueia execução durante transmissão
ativa. Clona dois commits públicos imutáveis em diretório temporário:

- Memoria.ia V2: `4f40da7876ecece3ce30f743d1b7a8382213aaf1`;
- BDR v1.2.0-rc4: `317882a00f041fc1568ff986af8016b09453f21a`.

Compila a ABI C atômica com um único trabalho, em baixa prioridade. Caso o
Ubuntu não tenha `cmake`, baixa uma ferramenta temporária via pip para
`/tmp`; **não instala pacote persistente pelo apt**. O código e a biblioteca
não contêm dados privados e são acessíveis somente durante essa execução.

Após aprovação explícita via `sudo`, apenas o usuário de serviço
`liveinfinita` abre o SQLite e o checkpoint privados. O código da Memoria.ia
usa backup online do SQLite, incluindo WAL, sem parar o escritor. Cria
`/var/lib/live-infinita/memoria-local/bdr-mirrors/<run>` com permissão
0700; o snapshot e o relatório ficam privados.

O espelho valida chaves, payloads, SHA-256, todas as relações EvidenceCore,
recuperação após fechar/reabrir, sequência durável e idempotência. Verifica
também que o último episódio confirmado pelo checkpoint inicial consta do
snapshot. Se o checkpoint avançar durante a cópia, o relatório indica
explicitamente que ele não representa uma posição congelada para cutover.

## Critérios e limites

- Até 100.000 registros e 256 MiB de origem SQLite+WAL+SHM; exige 512 MiB
  livres antes de copiar. Resultados maiores devem ser planejados à parte.
- Nenhum segredo ou episódio é impresso. O relatório contém apenas contagens,
  hashes de conjunto, tempo, tamanho, durabilidade e flags de autoridade.
- Original SQLite, WAL, checkpoint e o ledger autoritativo não são alterados
  por este ensaio. Nenhuma API recebe escrita, nenhum serviço reinicia.
- Em falha, não há `report.json` válido. Os arquivos privados parciais ficam
  disponíveis somente para diagnóstico — não use como espelho aprovado.
- A biblioteca BDR é apenas usada na execução da comparação. Não é instalada
  no `memoria-local.service` e não habilita modo BDR na V2.

Depois da execução, procurar `MVP018D_BDR_MIRROR_OK`; o resultado positivo
significa **equivalência do snapshot**, nunca mudança da memória operacional.
Para uma migração real ainda serão necessários congelar somente o worker
local, conciliar cauda/checkpoint, backup íntegro, rollback e aprovação do
operador. Isso não está implementado neste script.
