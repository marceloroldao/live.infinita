# 008DI1 — publicação com permissão antes da troca

Após instalar 008DI, uma execução excedeu dez segundos. A consulta HTTP feita durante a falha retornou 403; a execução seguinte restabeleceu o endpoint. O publicador anterior trocava o arquivo com a permissão privada do temporário e só depois aplicava chmod.

O novo publicador define 0644 antes de trocar o arquivo visível. Interrupção antes da troca preserva o anterior; após a troca, o novo já possui permissão de leitura. O limite do serviço passa a trinta segundos para tolerar carga da VM. O timer continua com intervalo nominal de cinco segundos após cada conclusão.

Instale: sudo bash /home/etbra/live.infinita/deploy/apply-panel-permissions-008di1-root.sh

Esta correção atualiza apenas o publicador e sua unidade systemd; não reinicia o renderer nem altera a memória. A versão web permanece 8a6dcb2.
