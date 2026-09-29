# MVP-018C — Memoria.ia local para Nov, sem conexão central

## Runtime efetivamente usado

É **a implementação real** `memoria_resolutiva.evidence_core.EvidenceCore`, do repositório `marceloroldao/memoria.ia`, tag publicada `v2.0.0-rc2`, commit fixo `e38f27b639bec1cfcb83694c1418a4d01f250ffd` (código somente leitura sob `/opt/live-infinita-memoria-rc2/src`). Nada de simular um engine de memória com regras locais.

O backend do `ProductEvidenceService.save()` da RC2 serializa todo o grafo em cada operação. O primeiro ensaio sobre apenas 16 experiências de Nov consumiu **66 MiB** nesse formato SQLite; por isso **não** o utilizamos como checkpoint periódico da Live. Mantemos a lógica relacional do EvidenceCore genuíno, mas a Live fornece um adaptador de persistência incremental SQLite por episódio (uma linha por observação tipada, mais checkpoint na mesma transação). A Memoria.ia é reconstruída fielmente a partir dessas observações originais na abertura.

Não representa a stack completa BDR/nativo, um servidor REST Memoria.ia, ou a inferência estrutural multimodal total. Essas possibilidades ficam para próximos gates comparativos. Nenhuma segunda stack Docker, LLM ou GPU é iniciada na VM.

## Fluxo de vida

```text
Nov / World State / Single Writer ──escreve──> npc-episodes.jsonl (original)
                                               │ leitura incremental limitada
                                               ▼
                                    worker Memoria.ia local RC2
                                               │
                                EvidenceCore real + replay observado
                                               │ transação SQLite única
                                               ▼
                 /var/lib/live-infinita/memoria-local/memoria-local.sqlite3
                               (observações tipadas + cursor)
```

Entradas são exclusivamente `npc_episode_v1` de Nov, origem `need_outcome`, plano/proposta/revisão coerentes, com `record_key` e `content_sha256` verificados. Nunca entram texto inventado da narração, role `user/assistant`, previsões do Shadow Mode ou texto livre do source.

Cada episódio gera no núcleo relações explícitas do episódio para Nov, destino, necessidade e estratégia quando presentes. Namespace é `live:<world_id>`; origem `live.infinita:<world_id>`; o `logical_tick` é o epoch. O `source_text` técnico da relação é JSON canônico do envelope original tipado, **não uma frase de linguagem natural gerada**.

## Durabilidade e isolamento

- O SQLite local tem `journal_mode=WAL`, `synchronous=FULL` e transação única para persistir lote e cursor. Offset em bytes nunca avança sem os próprios episódios duráveis; sem ACK remoto.
- O worker usa `flock`, lê até 256 KiB / 8 episódios por ciclo, verifica dev/inode e SHA-256 dos últimos 4 KiB antes do cursor. Recusa conflito, fonte substituída/truncada, origem mista e banco com contagem divergente do checkpoint. Duplicatas idênticas são idempotentes.
- Um processo isolado por systemd usa `PrivateNetwork=true`, `ProtectSystem=strict`, `CPUQuota=25%` (de um núcleo), `MemoryMax=512M`, `Nice=10` e intervalo de aproximadamente dois minutos. Não possui porta HTTP, chave da central nem acesso de escrita ao World State.
- Nov, renderer, API e áudio **não** são reiniciados pela instalação do trabalhador local. O banco derivado não é uma fonte de autoridade: se ele falhar, Nov permanece vivo e o original fica intacto.
- O log `MVP018C_LOCAL_MEMORIA_DEPLOY_OK` indica persistência *local* no backend, nunca sincronização central.

## Operação

Na `main` da VM, o operador executa uma vez `bash deploy/mvp018c-local-memoria.sh`. O script valida commit e testes contra a RC2 real, instala worker e timer, cria um lote de teste e verifica todos os PIDs de produção. Rollback desativa/recupera apenas as unidades locais; dados derivados são preservados para auditoria.

```bash
systemctl status live-infinita-local-memoria.timer
journalctl -u live-infinita-local-memoria.service -n 40 --no-pager
sudo -u liveinfinita env PYTHONPATH=/opt/live-infinita-memoria-rc2/src:/opt/live.infinita /opt/live.infinita/.venv/bin/python /opt/live.infinita/apps/world-runtime/local_memoria_worker.py --status
```

## Próximos testes

1. Medir crescimento do SQLite, tempo de reconstrução do EvidenceCore e impacto de CPU em 100, 1000 e 10.000 episódios. Ajustar `limit` e timer de acordo com o resultado.
2. Explicitar APIs read-only de relações/recall para Nov e painel do Manager, sem LLM.
3. Integrar V2 estrutural/multimodal por portas de eventos reais; não converter episódios em conversação artificial.
4. Adicionar receptor/recibo remoto apenas após contrato versionado, autenticação do dispositivo e consentimento operacional.
