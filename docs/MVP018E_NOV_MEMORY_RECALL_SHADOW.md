# MVP-018E — Consulta local de Nov à Memoria.ia V2 (Shadow Mode)

## Situação e contrato

O espelho nativo BDR do MVP-018D confirmou **paridade do snapshot de 102 episódios**
em sua execução inicial; não representa todos os episódios que chegaram depois.
O backend operacional permanece **SQLite incremental**. A prova BDR e esta
consulta de experiências são experimentos distintos. O BDR não é habilitado
nem lido pelo Nov neste estágio.

O consumidor do MVP-018E é um **one-shot manual desligado por padrão**. Ele
faz cópia consistente via API de backup online do SQLite WAL, em pasta 0700
pertencente somente ao usuário de serviço, e abre essa **cópia** com o
`IncrementalExternalEpisodeStore` real da versão Memoria.ia V2
`2b6334e8d6026c6bae620297de3f2fa658427596`. A reidratação do EvidenceCore
revalida cada registro e sua relação. A fonte original nunca é aberta para
escrita; não há chamada à API de ingestão, nem rede central.

## Consulta associativa inicial

Cada experiência confirmada mantém endereço de episódio, proveniência
`live.infinita:npc_episode_v1`, índice de tempo lógico e payload tipado.
No primeiro ensaio, a consulta é formada pelos endereços presentes na última
experiência confirmada de Nov (necessidade, região, período, clima, alvo e
estratégia, quando existirem). O próprio episódio consultado é excluído do
resultado: repetir a última observação não conta como recuperação anterior.

O conjunto de endereços é comparado por interseção com experiências anteriores.
A ordenação é primeiro pela quantidade de endereços coincidentes e, em empate,
pela proximidade temporal. O resultado de pesquisa vazio permanece vazio
(`historical_matches=0`), sem criar lembranças, regras fixas de decisão,
narrativa ou conteúdo de LLM. Opcionalmente, o operador pode consultar uma
necessidade específica, associada ao período/clima atual do mundo.

Essa é a **primeira camada de recuperação tipada e determinística**; não é uma
afirmação de que a Memoria.ia já produz inferência semântica multimodal ou
que o Nov já toma decisões a partir de lembranças.

## Fronteiras operacionais

- Lê o `world_id` autoritativo de `world.json` e verifica a identidade
  registrada no checkpoint privado de ingestão.
- Verifica a última observação confirmada pelo checkpoint dentro do snapshot;
  falha fechado se a identidade/sha divergir.
- Reidrata o EvidenceCore real e confere as relações e payloads de origem
  junto com os hashes canônicos da V2.
- A consulta de teste escreve apenas arquivos temporários privados de
  snapshot sob `memoria-local`, removidos ao fim; nada é escrito no banco
  original, checkpoint, World State ou ledger do Nov.
- O comando imprime só contagens, tick e quantidade de endereços coincidentes.
  Não imprime payload, chaves, identidades de episódios ou segredos.
- Um consumidor de código pode pedir explicitamente
  `include_evidence=True` para obter experiências e identidade de prova
  **somente em memória do processo**. Essa opção não existe no CLI.
- Nenhuma ação, proposta, seleção, alteração do mundo ou serviço/timer é
  ativado; a autoridade permanece no Single Writer.
- O script não é executado automaticamente durante a live e não toca no
  Godot, narrador ou BDR.
- Se checkpoint avançou durante a cópia, o snapshot continua válido, mas
  não representa necessariamente a memória mais recente.

## Teste na VM — autorização do operador

Depois de merge e CI, executar como `etbra`:

```bash
cd ~/live.infinita && bash deploy/mvp018e-nov-recall-shadow.sh
```

Consulta opcional por necessidade:

```bash
cd ~/live.infinita && bash deploy/mvp018e-nov-recall-shadow.sh hunger
```

O próprio wrapper solicita sudo e abre o código público antes de trocar
a identidade; ele **não** muda permissões de `/home/etbra`.
Procurar `MVP018E_NOV_RECALL_SHADOW_OK` e
`MVP018E_NOV_RECALL_NO_CUTOVER`. O resultado é um ensaio observacional,
não o acionamento automático da memória pelo Nov.

## Gates para o passo seguinte

1. Confirmar repetibilidade da recuperação e a concordância dos episódios
   com as relações reais do EvidenceCore sob alterações de contexto.
2. Fazer um consumidor dedicado de contexto cognitivo de Nov com IDs de
   evidência e snapshots versionados; publicar apenas diagnósticos na
   trilha de Shadow Mode, **nunca** resultado de LLM como evidência.
3. Avaliar impacto em previsões antes de habilitar influência sobre
   decisões. Qualquer mudança de autoridade ou backend exigirá gate,
   rollback e aprovação separada.

Referências: issue #88, PR #87 (espelho), PR #90 (auditoria corrigida).


## Extensão: contexto verificado para Shadow Mode

A camada `nov_memory_context_shadow.py` aceita o resultado privado de
`recall_once(include_evidence=True)` **somente como entrada em processo**,
conferindo ID de evidência, digest, proveniência, mundo, tempo lógico,
endereços coincidentes e identidade do frame cognitivo.

`CognitiveShadowRecorder` possui um parâmetro novo, opcional:
`memory_recall_provider`. O provider **não é ligado** em
`autonomous_runtime_main.py` nem em qualquer serviço de produção. Ele só
pode ser injetado explicitamente numa execução isolada de Shadow Mode.

O `ShadowToken` conserva IDs completos somente em memória. O arquivo
`memoria-v2-shadow.jsonl` recebe apenas contagens e indicadores
redigidos/sem segredo; não grava IDs, hashes ou payloads de observação.
O contexto é diagnóstico, sem `used_to_rank`, previsão de ação ou
autoridade sobre propostas, plano, Single Writer ou World State.

Falhas de validação causam abstenção do observador: o wrapper
`ShadowWorldTickRunner` prossegue com o tick autoritativo, sem consumir
lembranças não verificadas. Não há leitura de BDR nem sincronização central.

Gate: executar as provas isoladas e a integração com o EvidenceCore real na
CI. Antes de conectar o provider em produção, obter resultado de recuperação
de origem no ensaio manual e medir o custo da cópia SQLite/WAL e da reconstrução
V2; **não** reconstruir o grafo a cada tick. Um futuro cache somente de leitura
terá de ser versionado pelo checkpoint e invalidado por atualização da memória.
