# 008FC — Histórico persistente de aproximações

Nov conserva os resultados da aproximação física de coelhos avistados entre reinícios. O controlador continua usando apenas observações do sensor visual e a locomoção com colisões existente. Não adiciona captura nem modifica a estratégia com base nos resultados nesta etapa.

## Registro
Arquivo privado adjacente ao checkpoint de busca, com sufixo `.approach`, envelope SHA-256, escrita por arquivo temporário e troca atômica, permissão 0600, máximo de 512 tentativas. Os dados públicos apresentam os últimos 16 resultados e contadores de armazenamento, interrupções e elegibilidade.

Cada conclusão registra identificador, mundo, animal observado, tempo lógico inicial/final, distância física acumulada, distância observada inicial/final, resultado, revisão e censura. Apenas resultados com movimento efetivamente medido e encerramento por aproximação, perda de contato, falta de progresso ou orçamento esgotado são elegíveis para avaliação posterior.

Antes de mover, salva uma intenção pendente. Se o processo termina antes de concluir, a próxima inicialização registra `renderer_restart` uma única vez, censurado, sem distância ou horário final inventados. Pausa, recuperação da navegação, mudança de mundo, destino rejeitado e regressão do relógio também não contam como aprendizagem. O intervalo entre tentativas é restaurado; relógio ainda anterior ao último resultado aguarda sincronização. Checkpoint inválido desativa a aproximação.

Este arquivo é histórico local durável, separado do núcleo Memoria.ia. `core_ingestion=false` e `learned_hunting=false` continuam explícitos nos dados técnicos. Para demonstrar aprendizagem da caça ainda falta integrar os fatos ao núcleo, comparar decisões com e sem recuperação e medir melhoria em situações repetidas e alteradas.

## Evidência
`ANIMAL_APPROACH_HISTORY_008FC/live_008fb_approach_events.json` preserva os quatro eventos do journal de produção: duas aproximações concluídas, com 17,5174 m e 4,8000 m percorridos. Não foram importadas no novo checkpoint porque a versão anterior não media todos os campos novos.

O teste 008FC reutiliza o movimento físico do teste 008FB: cerca de 3,6 m, sem colisão, com avistamento confirmado por raios. Verifica recarga fria do resultado, intervalo preservado, deduplicação, censura de reinício, checksum inválido, rejeição de captura e retenção de 512 registros. As intenções usadas para testar reinício/retenção são fixtures censuradas; não são fatos reais de caça e não são ingeridas no núcleo.

## Aplicação
Instalador: `deploy/apply-animal-approach-history-008fc-root.sh`.
Executar pelo usuário:
`sudo bash /home/etbra/apply-animal-approach-history-008fc-root.sh`

Mantém a chave reversível 008FB e as quatro melhorias de navegação. Faz backup de código e publicação; em falha para o renderer antes de restaurar arquivos. Não apaga memória nem o novo histórico durante rollback. A prontidão exige publicação posterior ao reinício e histórico configurado como persistente e disponível. Aplicação confirmada na produção em 09/10/2026: fonte 4e16afc, renderer iniciado às 19:14:42 de São Paulo, sem erros de script ou reinícios automáticos. Publicação recente confirma armazenamento configurado como persistente e disponível. Ainda não há tentativas novas neste histórico; persistência de uma tentativa real em produção aguarda um novo encontro.

## Validação concluída
52 regressões com aproximação ativada e 52 desativada: 104/104 passaram. Seis testes do instalador 008FC e quatro da prontidão 008FB passaram. Sintaxe dos dois scripts de shell e verificação de whitespace sem erros. O teste físico mediu 3,5999987 m e zero colisões, preservando o resultado após recarga fria. Evidências e código são versionados juntos.
