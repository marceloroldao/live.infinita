# MVP-018F — Índice de recuperação da memória do Nov, versionado e limitado

## Situação

O MVP-018E validou a Memoria.ia V2 real sobre cópia consistente de
`external-episodes.sqlite3` (incluindo WAL) e permitiu consultas tipadas, sem
escrever no SQLite original. O MVP-018F **não muda a fonte autoritativa** nem
liga o provider ao `autonomous_runtime_main.py`.

O problema desta etapa é operacional: copiar SQLite e reidratar todo o
EvidenceCore **a cada tick de Nov** seria inadequado para o servidor.
O novo `VersionedNovRecallCache` mantém **somente em RAM** um índice cujos
registros já foram verificados pela V2 genuína. Consultas posteriores usam
interseção de endereços e tempo sobre essa coleção, sem nova cópia ou
reconstrução da V2 enquanto a versão da fonte não mudar.

## Contrato de validade

A identidade da versão reúne:

- `world_id` autoritativo e hash do checkpoint privado de ingestão;
- device/inode, tamanho e `mtime_ns` do SQLite e do WAL, quando presente;
- TTL máximo de 180 segundos, com atualização forçada mesmo sem alteração
  detectada nos metadados de arquivo.

No primeiro uso ou após mudança de WAL, DB, checkpoint, mundo ou TTL, a
consulta lê **uma** cópia online via `recall_once(include_index=True)`,
que revalida todos os registros com o EvidenceCore real. A opção
`include_index` é exclusiva para processos confiáveis: o CLI do operador
permanece redigido, sem exportar índice, IDs ou payloads.

O índice só é retido se checkpoint e assinatura da fonte permanecerem estáveis
antes/depois da leitura. Qualquer corrida ou inconsistência descarta o cache;
não usa silenciosamente uma versão anterior. Mudança durante a própria
consulta também bloqueia o resultado. Em caso de timeout/falha, o
`ShadowWorldTickRunner` mantém o tick autoritativo, sem contexto novo.

Limites iniciais, ajustáveis apenas para menos no construtor:
**2.048 registros, 8 MiB de índice, 5 lembranças por consulta**. Ultrapassar
o limite implica abstenção (nunca truncamento do EvidenceCore que pudesse
fingir que o histórico está completo). Nenhum cache é persistido em disco:
somente o snapshot temporário privado criado para validar uma nova versão.

## Consulta contextual

A necessidade vem da **última experiência confirmada até o tick**; região,
período e clima vêm dos endereços do frame atual do Nov. O episódio usado como
semente é excluído. A ordenação é coincidência de endereços e recência, não
seleção de ações. Uma memória vazia/sem coincidências retorna um conjunto vazio.

O resultado privado passa por `freeze_memory_context(frame, result)`, que
confere IDs, proveniência, mundo, tempo e autoridade. A trilha de Shadow
registra apenas quantidades e indicadores. Não há texto gerado por LLM,
regras rígidas para decidir um plano, nem alegação de inferência multimodal
ou aprendizado autônomo comprovado a partir destes testes.

## Segurança e autoridade

- Backend operacional: `sqlite-incremental`. O espelho BDR é independente.
- Não existe conexão com Memoria.ia central, novo serviço/timer, restart,
  mudança de configuração ou alteração no Single Writer.
- `autonomous_runtime_main.py` permanece **sem provider instalado**:
  execução em produção só após prova operacional privada, medição de
  latência/RAM e aprovação própria.
- O usuário de serviço detém as observações privadas. Os testes artificiais
  não usam dados pessoais da VM.
- Metadados de arquivo são um **detector de mudanças**, não um hash
  criptográfico de todo o DB. A integridade de cada episódio vem da validação
  canônica da V2 ao reconstruir o índice; o checkpoint é verificado dentro
  do snapshot. A trilha declara `live_caught_up_claim=false`: snapshot
  histórico não equivale a confirmação de que não existem novos episódios.

## Gates

1. Testes artificiais: reutilização sem rebuild; invalidação por WAL,
   checkpoint, troca de DB, TTL e mundo; corrida durante carga/consulta;
   orçamento, privacidade e memória vazia.
2. Teste real pinado na versão V2: uma carga inicial, hit e reconstrução após
   novo ACK durável, com EvidenceCore real e checkpoint imutado pela leitura.
3. Revisão de relatório operacional redigido do MVP-018E e benchmark de custo
   em snapshot da VM, antes de qualquer conexão automática ao tick do Nov.
