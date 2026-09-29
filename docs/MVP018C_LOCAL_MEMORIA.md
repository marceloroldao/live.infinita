# MVP-018C — Memoria.ia local de Nov (RC2 real, sem nuvem)

## Princípio

Na Live Infinita, Nov vive no **World State** (Single Writer) e seus resultados originais estão em `npc-episodes.jsonl`. A Memoria.ia local é um **espelho relacional durável e derivado**, não um substituto do ledger nem uma LLM. Nenhum processo desta integração escreve no mundo, pede ao narrador para inventar fatos ou depende da Memoria.ia central.

## Runtime adotado e validado

- Fonte real `marceloroldao/memoria.ia`, tag `v2.0.0-rc2`, commit imutável `e38f27b639bec1cfcb83694c1418a4d01f250ffd`; não é uma reimplementação chamada Memoria.ia.
- Classe real `memoria_resolutiva.product_evidence.ProductEvidenceService` com `EvidenceCore` e backend SQLite explícito (`allow_fallback=False`). Banco local em `/var/lib/live-infinita/memoria-local/evidence/`; serviço Python é um worker separado, sem porta de rede.
- SQLite é deliberado nesta fase para evitar compilar o BDR nativo ou carregar uma segunda stack Docker no servidor com 2 vCPUs; BDR nativo e memória estrutural podem ser integrados depois com gate de equivalência e performance.
- Fonte RC2 instalada sob `/opt/live-infinita-memoria-rc2/src`, somente leitura, `commit.txt` inspecionado antes do worker.

## Ingestão e semântica

Fonte exclusiva: `npc_episode_v1` do ator `nov`, com `source.kind=need_outcome`, `plan_id/proposal_id/revision` coerentes. Envelope V1 do MVP-018B usa `record_key`, `content_sha256`, proveniência e campos de resultado reais. Não converte experiência em mensagem `user`/`assistant`.

Para cada episódio, o núcleo Memoria.ia recebe relações tipadas do nó do episódio para Nov, destino, necessidade e estratégia presentes. A fonte canônica do próprio episódio é preservada em `source_text` apenas como serialização técnica de observação estruturada, não como texto gerado ou mensagem de chat. `provenance=live.infinita:npc_episode_v1`, `origin=live.infinita:<world_id>`, `namespace=live:<world_id>`, `epoch=logical_tick`.

## Durabilidade

- Um processo com `flock` faz até oito episódios por chamada, lendo no máximo 256 KiB da fonte. `PrivateNetwork=true`, memória limitada a 512 MiB e CPU limitada a 25% de uma vCPU; timer a cada aproximadamente dois minutos.
- Cada lote é persistido com `ProductEvidenceService.save()` do pacote real. Só depois o worker publica `checkpoint.json` local de forma atômica com `fsync`, contendo identidade dev/inode do ledger, offset em bytes, hash dos últimos 4 KiB antes do offset, contagem de relações e recibo da própria Memoria.ia.
- Um reinício entre persistência e checkpoint pode repetir lote. Relações já existentes de mesmo ID e conteúdo são reconhecidas, sem duplicação. Mesmo ID com conteúdo diferente falha fechado.
- Truncamento, troca do ledger, hash da âncora divergente, checkpoint ausente para um banco já preenchido, proveniência mista/corrompida ou ausência de recibo interrompem o worker. O ledger original nunca é reescrito.
- `checkpoint.json` é **recibo LOCAL da Memoria.ia**, não ACK de servidor. Sem autenticação central, sem HTTP externo, sem envio, sem sincronização de cache ou decisão autônoma a partir dessa projeção.

## Operação

Deploy é manual, via `bash deploy/mvp018c-local-memoria.sh` no checkout `main` como `etbra`. Valida a fonte RC2, testes com implementação real, backups e instalação do worker e timer, e roda um lote de smoke; verifica os PIDs de Nov, API, renderer e áudio sem reiniciá-los. Se o deploy falhar, faz rollback das unidades/worker e conserva o banco derivado para diagnóstico/reconciliação.

Estado: `sudo -u liveinfinita env PYTHONPATH=/opt/live-infinita-memoria-rc2/src:/opt/live.infinita /opt/live.infinita/.venv/bin/python /opt/live.infinita/apps/world-runtime/local_memoria_worker.py --status`.

Logs: `journalctl -u live-infinita-local-memoria.service -n 40 --no-pager`; timer: `systemctl list-timers live-infinita-local-memoria.timer`.

## Próximos gates

1. Confirmar replay frio do banco local e recuperar episódios com consulta relacional efetiva, sem LLM.
2. Medir tempo, crescimento do SQLite e CPU da projeção em 100/1000 episódios; ajustar ritmo antes de espelhar todo o histórico.
3. Expor no Manager observabilidade de memória local (estado, tamanho, último tick, fonte) por leitura limitada.
4. Somente depois conectar a memória local à central usando o contrato de observação e recibo autenticado, mantendo o world authoritative.
