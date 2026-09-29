# MVP-018K — Preparação assíncrona da memória local de Nov

## Contrato implementado

`OwnerAsyncDualLanePreparation` prepara a recuperação primária e a
suplementar em uma **thread explícita do processo proprietário da Memoria.ia**.
A chamada `submit(frame)` só coloca o frame na fila de capacidade um:
requisições anteriores pendentes são coalescidas; somente a última geração
pode publicar um resultado. O consumidor `peek(frame)` executa somente em
RAM. Não acessa arquivos, SQLite, rede, checkpoint nem aguarda a thread.

O caminho frio (validar SQLite/WAL, checkpoint, mundo e proveniência via
EvidenceCore V2 pinado; congelar dois contextos) é executado fora do tick.
O resultado só é publicado quando a versão da fonte não mudou durante
a preparação. A thread verifica periodicamente a versão da fonte: quando
detecta alteração, invalida o pacote anterior e aguarda um novo frame.
Não afirma atualização instantânea: existe intervalo de observação entre
checagens. O pacote representa **histórico verificado**, não o estado
corrente de toda a memória.

A leitura só entrega dois `MemoryShadowContext` separados se todos os
gates passarem: identidade do mundo, observador Nov, frame não anterior,
atraso de no máximo 20 ticks, idade máxima de 6 segundos e consulta atual
equivalente à que gerou o pacote. Contextos com outro mundo, região,
período, clima, ou tick regressivo/atrasado recebem status de abstenção.
A validação por `freeze_memory_context` é repetida para o frame leitor
(identidades, épocas e proveniência), sem nova leitura da fonte.

Os limites são explícitos e configuráveis dentro de faixa restrita:
idade 1–30 s, atraso 0–120 ticks, sondagem de versão a cada 0,1–5 s.
Nenhum caso expirado, falho, não preparado ou de versão alterada entrega
evidências. `close()` apaga o pacote e encerra a thread (se a preparação
já estiver executando, ela pode concluir antes da saída).

## Bridge opcional para o Shadow Mode

`CognitiveShadowRecorder` agora aceita um
`prepared_memory_provider(frame)` **explicitamente injetado**, alternativo
ao antigo `memory_recall_provider`. Um não pode coexistir com o outro.
Quando o preparador retorna `ready`, os contextos são mantidos em slots
distintos, com frame e proveniência verificados. Em ausência de pacote,
o observador se abstém sem impedir o tick. Só são persistidos contagens
redigidas e `memory_preparation.status`: nenhuma chave, ID de evidência,
vetor de outcome ou payload entra em `memoria-v2-shadow.jsonl`.

**O provider permanece DESLIGADO em
`autonomous_runtime_main.py` e não há daemon/timer ou porta IPC nova.**
Essa API foi testada em um observador isolado. Nem a thread preparadora
nem o core V2 são instanciados no serviço do mundo neste MVP. A ligação
entre processos e permissões será uma decisão separada, após teste real.

## Executar o gate real (usuário etbra; pede senha sudo)

```bash
cd ~/live.infinita && bash deploy/mvp018g-nov-memory-diagnostics.sh
```

No processo independente, o script cria um preparador adicional,
submete um frame retrospectivo, aguarda até cinco segundos **somente no
diagnóstico**, e mede a latência de vinte `peek` não bloqueantes.
O relatório de propriedade privada `~/nov-memory-diagnostics.log` (0600)
inclui `async_preparation`, resumo de duas vias e flags
`source_rebuild_off_tick=true`, `main_runtime_wired=false`.
Nenhuma observação/ID/segredo sai da raiz privada da Memoria.ia.

O frame diagnóstico é retrospectivo, não a posição corrente do Nov.
O relatório não comprova utilidade de ação, sincronização total, latência
sob toda carga possível ou serviço autônomo continuamente implantado.

## Restrições e gates seguintes

- Não faz proposta, escolha de estratégia, World State, sync central, BDR
  cutover ou restart.
- O leitor nunca utiliza `VersionedNovRecallCache.__call__`: este pode
  reconstruir o EvidenceCore ao mudar a versão e deve ficar fora do tick.
- Medir latência de `submit`, de leituras `peek` e de reconstrução a
  partir de dados reais antes de criar um processo duradouro.
- Para integração live futura: contrato IPC proprietário/isolado,
  permissões de usuário e ciclo de vida separados; não transferir
  payload/IDs em relatórios públicos nem assumir que o snapshot está
  atualizado quando chegam novos ACKs.
