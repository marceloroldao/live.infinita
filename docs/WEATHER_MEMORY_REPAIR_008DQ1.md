# Recuperação do conector — 008DQ1

## Instalação anterior

O rollout de 008DQ com fonte `ea28cc0` não concluiu. O status do experimento indicou `memory_api_or_contract_unavailable`, e o instalador fez rollback. O serviço de controle voltou ao executável de 008DP; timer ativo, avaliação do controle continuando e dados confirmados preservados. Na primeira verificação pós-rollout havia 16 avaliações e nenhum alvo perdido.

O journal marca início da tentativa com memória em 2026-10-07 03:42:34 UTC e término com falha em 03:42:39 UTC. O conector novo limitava tanto POST como GET a cinco segundos. Essa duração é compatível com timeout, mas o diagnóstico genérico da versão anterior não identifica a etapa nem prova a causa exata. A API local e as outras pontes de memória estavam ativas, com últimas execuções bem-sucedidas.

## Ajuste

- POST de observação passa a usar 30 segundos; GET de recuperação, 15 segundos, conforme os prazos das pontes já existentes.
- Unidade recebe limite total de 65 segundos para acomodar as duas chamadas e persistência.
- Falhas registram etapa, código seguro e horário. Distingue timeout, transporte, HTTP e validação do contrato, sem imprimir chave, corpo da resposta ou texto bruto de exceções.
- Respostas HTTP com erro são fechadas antes de propagar o código seguro.
- O instalador imprime esse diagnóstico antes de decidir rollback.

A janela de emissão continua de dez segundos lógicos após a observação inicial. Se a API responder depois da janela, a previsão não será emitida retroativamente. O controle continua sendo publicado antes das operações de memória. Um serviço lento pode perder uma janela de observação; essa perda é registrada, sem interpolar resultados. O ajuste não muda o previsor, os campos físicos, as regras de pontuação nem o núcleo da Memoria.ia.

Checkpoints anteriores sem o novo campo de diagnóstico continuam válidos. Aumentar a espera não prova que a API funcionará em produção; a próxima instalação fornecerá o resultado e, se necessário, a causa específica.

## Validação e instalação

17 testes do experimento/conector aprovados, incluindo prazo maior que o limite antigo, classificação segura de timeout/HTTP, preservação do controle durante falha e compatibilidade com checkpoint antigo. Mais oito testes do controle e oito da física: 33 no total. Sintaxe do instalador, unidade systemd e diff verificados.

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-weather-memory-008dq1-root.sh
```

Sucesso esperado: `008DQ1_OK`. Log: `/home/etbra/008dq1-weather-memory-rollout.log`. O instalador mantém o rollback da versão anterior e preserva previsões, controle e memórias confirmadas.

## Confirmação de produção

Rollout retornou `008DQ1_OK` com fonte `9f7ab53`. Timer, serviço de controle/experimento e API local ativos. Entrega HTTPS recente confirmada: 30 registros recuperados, 2 pares avaliados, 0 alvos perdidos pelo experimento. Nenhuma falha de API atual; o contador histórico preserva a falha da instalação anterior. A última previsão avaliada foi emitida antes do alvo, usando três IDs recuperados cujos resultados já existiam no horário inicial. A influência sobre a física continua desligada. Registro integral em `WEATHER_MEMORY_PRODUCTION_008DQ1.json`.
