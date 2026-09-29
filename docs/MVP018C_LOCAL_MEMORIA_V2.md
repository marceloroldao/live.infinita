# MVP-018C — Memoria.ia V2 local da Live Infinita

## Decisão

A memória de Nov opera **dentro da VM**, com o núcleo real
`marceloroldao/memoria.ia` fixado no commit
`2b6334e8d6026c6bae620297de3f2fa658427596` (V2).
Não é um clone SQL improvisado nem o serviço central. Usa V2 Product
EvidenceCore e o contrato tipado `/api/v1/external/episodes`, sem coerção para
`role=user|assistant` ou texto gerado.

A implantação local é separada do runtime autoritativo:
- Processo independente: `live-infinita-memoria-local.service`, somente
  `127.0.0.1:8788`, 1 worker, prioridade de CPU baixa e limite de memória;
- Runtime de conversação e episódico **Python de referência do próprio V2**,
  persistência SQLite explícita sem fallback para outro backend, sem LLM;
- Código imutável da versão: `/opt/live-infinita-memoria-core/<SHA>/src`;
- Dados próprios: `/var/lib/live-infinita/memoria-local` (permissão 0700);
- Credencial específica e protegida em `/etc/live-infinita/memoria-local.env`
  (0600), nunca a chave do Manager, nem a chave administrativa central;
- Nenhuma porta externa, nenhuma necessidade de Internet para operação normal.

O Godot, API de público, narrador, Single Writer e World State existentes
continuam independentes do serviço de memória. A Memoria.ia local não recebe
autoridade sobre ações, seleção de propostas ou commits do mundo.

## Ingestão local de experiências confirmadas

O serviço auxiliar `live-infinita-memoria-nov-sync.service` lê **somente**
`npc-episodes.jsonl` e `world.json` como observador, usando a projeção tipada
do MVP-018B. Faz no máximo 2 observações por execução. A periodicidade da timer
é de aproximadamente 2 minutos, após boot, com prioridade menor que o renderer.

Para cada episódio:
1. valida a identidade do mundo e a proveniência `npc_episode_v1/need_outcome`;
2. deriva `record_key` e `content_sha256` canônicos, sem texto sintético;
3. envia **somente** ao endpoint fixo de loopback da Memoria.ia local;
4. exige retorno `ack=true`, IDs/digest exatos e referência do episódio
   persistido incrementalmente (`backend=sqlite-incremental`, `state_id`, `sha256`);
5. só então escreve atomicamente e com `fsync` o cursor em
   `nov-ingest.checkpoint.json`.

Após falha/timeout, repete a mesma observação. O core usa idempotência;
a memória não duplica o mesmo episódio. Conflitos de conteúdo são bloqueados.
Mudança de inode, truncamento, alteração de prefixo ou última linha confirmada
bloqueiam o avanço até reconciliação explícita. Não existe cursor central.
O timer não faz replay integral nem varredura do mundo.

**A gravação local é uma observação de uma experiência real**, não prova
independente de que o mundo físico tenha ocorrido, nem autorização para alterar
a simulação.

## Instalação controlada

O código, testes e units são mantidos no repositório Live. O script
`deploy/mvp018c-memoria-local.sh` faz preflight offline em dados temporários e
instala com backup de código anterior. Em caso de erro, desabilita somente os
serviços novos; **nunca apaga memória persistida ou o segredo local**.

**Histórico do bloqueio:** no commit antigo, `ProductEvidenceService.save()`
gravava snapshots completos: 24,41 MiB após 8 episódios e 91,21 MiB após 16.
A versão V2 agora pinada traz `MEMORIA_EXTERNAL_EPISODE_PERSISTENCE=sqlite-incremental`,
que mantém o EvidenceCore real e persiste uma linha canônica por episódio em
SQLite WAL com `synchronous=FULL`. Ensaio isolado: 100/1.000/10.000 episódios
ocuparam 1,93/5,28/16,46 MB, respectivamente, incluindo arquivos WAL; reabrir
e reconstruir 10.000 relações levou 2,27 s. Não é um teste prolongado de produção.

O instalador mantém o gate de até 8 MiB **após 8 observações reais de teste,
antes de qualquer sudo**, agora exigindo explicitamente o modo incremental.
O modo snapshot antigo não pode ser habilitado por acidente.

**Migração do rollback anterior:** a V2 verifica os registros tipados antigos
do último snapshot, migra-os de forma idempotente para o journal incremental
e mantém todos os arquivos antigos. A credencial local de 0600 é reaproveitada.
O checkpoint antigo continua no lugar: nenhum cursor é apagado ou avançado
sem novo recibo incremental. Fonte inconsistente interrompe a instalação.

Depois de merge, CI e liberação operacional, o operador executa como `etbra`:

    cd ~/live.infinita && bash deploy/mvp018c-memoria-local.sh

Valida em loopback:
- `/api/v1/health` HTTP 200;
- `/api/v1/storage/health` com SQLite e runtimes Python;
- `/api/v1/external/episodes` HTTP 401 sem credenciais;
- migração segura dos episódios existentes, journal incremental, recibo e checkpoint próprios;
- timers locais ativos e todos os PIDs de Nov/API/Godot/áudio inalterados.

Para inspecionar (sem revelar credenciais):

    systemctl status live-infinita-memoria-local.service
    systemctl list-timers live-infinita-memoria-nov-sync.timer
    journalctl -u live-infinita-memoria-nov-sync.service -n 30 --no-pager

A ligação ativa entre uma recomendação da memória e decisões de Nov **não**
é entregue neste MVP. Primeiro mediremos qualidade, proveniência, custo e
consistência da memória em shadow/observação; depois, sob policy gate, podemos
avaliar influência limitada. Nenhuma sincronização central está configurada.

## Evolução

1. Relatório de quantidade/latência de episódios e checkpoints locais;
2. Recuperação por semelhança/camadas do V2 e associação entre episódios,
   ambiente e estratégias — sem regras rígidas impostas à memória;
3. Nov pode consultar as trajetórias localmente, inicialmente em Shadow Mode;
4. Outras entidades naturais (vento, água, vegetação) poderão usar namespaces
   próprios, sem misturar autoria com Nov;
5. Integração opcional com Server central **só depois**, via contrato próprio,
   autorização e confirmação durável, sem depender dela em tempo real.
