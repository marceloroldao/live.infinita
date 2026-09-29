# MVP-018I — Recuperação híbrida observacional, fora do tick autoritativo

## Por que

O último relatório real MVP-018H (224 episódios, consulta retrospectiva)
mediu cinco recuperações: o baseline por coincidência/recência cobriu dois
perfis observados de trajetória (2 coincidências completas, 3 parciais);
o diversificado cobriu cinco perfis (1 completa, 4 parciais). Diversificar sem
limitar a perda de coincidência não demonstra melhor recuperação.

No mesmo snapshot, existem 7 vetores de endereços, 9 vetores de resultados e
11 perfis endereço+resultado; 223 transições adjacentes, 16 tipos de transição
dirigida e 66 transições sem mudança de endereços. São contagens de experiências
confirmadas, não uma classificação de sucesso ou inferência de causalidade.

## Contrato de recuperação

`select_hybrid` usa o **índice tipado validado pelo EvidenceCore da Memoria.ia
V2**, exclusivamente em RAM do usuário de serviço. Mantém cinco slots:

1. Os dois primeiros, quando disponíveis, são as recordações com maior
   coincidência e recência do baseline. Os episódios-semente são excluídos.
2. Cada slot restante pode ser preenchido por um perfil observado distinto
   (vetor exato de seis endereços + satisfação, risco observado, duração,
   preempções e replanejamentos tipados). Porém, um substituto deve ter
   **exatamente a mesma quantidade de coincidências de endereço** que a
   recordação que ocuparia aquele slot no baseline.
3. Se nenhum perfil novo existir naquela faixa, o slot mantém a próxima
   observação por recência. Não inventa diversidade ou respostas.

Isso preserva a sequência exata das quantidades de coincidências do baseline,
incluindo as completas, enquanto permite novas trajetórias de mesma relevância
estrutural. Não introduz pesos arbitrários, thresholds de bom/ruim,
interpretações semânticas, predicados nem votos de ação.

## Limite operacional

`OwnerHybridRecallWorker.refresh(frame)` só é executado quando **um processo
separado do mundo** o chama explicitamente. Ele reaproveita
`VersionedNovRecallCache`, validando mundo, identidade do checkpoint,
assinatura de arquivo SQLite/WAL, 2.048 registros/8 MiB e TTL de 180 s.
Qualquer mudança durante a consulta invalida o resultado; nenhuma versão
antiga vira nova evidência silenciosamente. O resultado privado é passado
pelo `freeze_memory_context`, que revalida identidade, época e proveniência.

**Não há thread, timer, daemon ou injeção automática do provider no
`autonomous_runtime_main.py`.** Neste MVP o processo independente é o
diagnóstico manual, que lê uma cópia online, monta o cache e imprime apenas
estatísticas. O próximo gate deve medir com histórico real se as lembranças
híbridas ampliam perfis sem diminuir coincidência, latência ou estabilidade.
Um sidecar recorrente com entrega ao Shadow Mode requer PR e gate próprios;
nenhuma cópia/reconstrução será executada no tick autoritativo de 500 ms.

## Executar, sem mudar a live

```bash
cd ~/live.infinita && bash deploy/mvp018g-nov-memory-diagnostics.sh
```

A saída redigida permanece em `~/nov-memory-diagnostics.log` (0600), com
`hybrid_recall_comparison`, `trajectory_recall_comparison`, tempos e
contagens. Não contém nomes de endereços reais, valores dos resultados,
payloads, chaves ou IDs privados. O código público é preparado em /tmp e
removido; arquivos da memória ficam sob `/var/lib/live-infinita/memoria-local`
com usuário `liveinfinita`, sem passar para o home do operador.

Nenhuma ação escolhida, alteração de World State, escrita de SQLite original,
sincronização central, ativação BDR ou restarts é executada. A memória local é
observada, não autoritativa. O comparativo é retrospectivo — não afirma medir
o estado instantâneo ou a utilidade da política do Nov em tempo real.

## Gates

- Testes puros: âncoras, equivalência exata do vetor de relevância, resultados
  nulos, seed excluído, memória vazia, ausência de alternativas e privacidade.
- Teste real com núcleo V2 pinado: dois caminhos sobre o mesmo índice validado
  e resultado congelado por `freeze_memory_context`.
- CI integral e pull limpo na VM, sem reiniciar serviços.
- Relatório real MVP-018I: comparar quantidade de perfis, cinco slots e tempos
  antes de qualquer aproximação ao processo cognitivo de produção.
