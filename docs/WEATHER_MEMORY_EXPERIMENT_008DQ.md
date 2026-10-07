# Previsões pareadas com memórias recuperadas — 008DQ

008DQ mantém o controle prospectivo de 008DP e acrescenta uma previsão de 60 segundos baseada em transições físicas recuperadas pela API estrutural da Memoria.ia local. O núcleo v2 continua congelado. A inferência por analogia é calculada pela aplicação, usando registros que a Memoria.ia armazenou e devolveu; não é um novo algoritmo implementado no núcleo.

## Observações e memória

A fonte é o canal global de dados físicos já entregue à live. Esta etapa não implementa visão meteorológica local, decisões de caminhada de Nov nem forças sobre o personagem.

Cada transição arquivada contém somente duas observações físicas confirmadas: a observação inicial do controle e a observação que realmente chegou 60–65 segundos lógicos depois. Há mundo, duração de tick, horários, valores, símbolos de contexto quantizado e digest do payload. Previsões, erros estimados e texto do narrador não entram nessa trilha. O evento é idempotente e a posição de ingestão só avança após ACK durável validado. No máximo uma transição é submetida por execução.

A recuperação usa `/api/v1/structural/observations/recent?limit=64`, filtra a hierarquia meteorológica do mundo atual e verifica conteúdo, identidade e digest. O cache privado retém até 384 registros realmente recuperados. Um ACK de gravação não basta para tornar um registro disponível ao previsor: ele precisa retornar pela API de leitura. O cache pode conservar registros recuperados em execuções anteriores, mesmo que já tenham saído da janela recente; não representa uma nova leitura integral do banco a cada previsão.

## Previsão e comparação

São exigidas pelo menos três transições recuperadas cujo resultado já existia no horário lógico inicial da nova tentativa. Dados posteriores a esse horário são excluídos. A aplicação escolhe as três transições mais próximas por temperatura, umidade, cobertura, vento e fase do ciclo diário; combina suas variações observadas, normalizadas pelo tempo real, e limita os valores aos intervalos físicos. Não consulta o integrador físico nem suas fórmulas de evolução futura.

A previsão guarda os IDs das três memórias, pesos, horários finais observados, valores previstos e momento de emissão. A emissão é permitida somente nos primeiros 10 segundos lógicos da tentativa, sempre antes do alvo. Uma instalação no meio de uma tentativa pode esperar a próxima janela; não fabrica previsões retroativas.

O controle e a previsão com memória usam a mesma observação inicial, o mesmo alvo e a mesma observação futura. Só tentativas com previsão de memória antecipada e resultado válido entram nas médias pareadas. Os erros do controle nessas médias são recalculados exclusivamente no mesmo conjunto de pares, e não comparados à média de todas as tentativas históricas de 008DP. Há contagens separadas de indisponibilidade, falha de API e alvo perdido. Valores de erro permanecem `null` sem pares. Resultados piores e melhores são preservados.

Uma comparação favorável pode mostrar utilidade das transições recuperadas para este previsor. Não isola a vantagem da implementação de armazenamento frente a outro banco, não demonstra cognição geral e não garante generalização a clima novo. São necessários muitos pares, mudanças de contexto e controles adicionais, inclusive RAM, antes dessas conclusões.

## Persistência e falhas

O controle existente continua com seu checkpoint e sua projeção de 008DP. O experimento tem checkpoint separado `/var/lib/live-infinita/weather/memory-experiment.json` (0600), com checksum, até 384 memórias e 128 pares de auditoria. Contagens e somas cumulativas sobrevivem ao descarte de registros antigos. Reiniciar não duplica avaliações; uma interrupção depois de gravar no núcleo e antes do checkpoint é resolvida por replay idempotente.

A publicação do controle ocorre antes das operações de memória. Falha de API ou corrupção do checkpoint do experimento não impede que novas execuções mantenham o controle; corrupção é rejeitada, sem apagar o último status de memória válido. O serviço usa a credencial local já configurada sem expô-la. Rede permitida somente em localhost, com tempos de requisição limitados.

Status do experimento: `/godot/navigation-memory/weather-memory.json`. Durante o teste, `inference_influence=false`: nenhum resultado modifica vento, nuvens, terreno ou WorldState. O visual permanece na versão 008DO e não exige exportar Godot novamente.

## Validação

13 testes específicos: influência causal dos registros recuperados sobre a previsão; ablação sem memória; exclusão de futuro/outro mundo; corrupção de conteúdo/ID/digest; deduplicação; limite do cache; normalização de prazo e limite vetorial; previsão anterior ao resultado; ganho e perda contra controle; falha de API; prazo de emissão vencido; janela perdida; preservação de status diante de corrupção; núcleo real congelado com gravação, ACK, recuperação, reinício e crash/replay sem duplicar eventos ou avaliação. Mais 16 regressões do controle e da física passaram: 29 testes no total.

`tests/weather_memory_live_shadow_008dq.py` usa dados reais públicos da live, três transições históricas previamente medidas e o núcleo real em um banco temporário isolado, sem credencial de produção. Emite e persiste uma previsão antes do resultado futuro e compara-a à tentativa real do controle. Esse teste verifica o protocolo em dados reais; uma única tentativa não demonstra melhoria geral. Os registros da execução ficam em `WEATHER_MEMORY_LIVE_SHADOW_008DQ.json` e `WEATHER_MEMORY_LIVE_SHADOW_LOG_008DQ.txt`.

## Instalação

Pré-requisitos: 008DO e 008DP instaladas, timers ativos e configuração da API local disponível.

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-weather-memory-008dq-root.sh
```

Sucesso: `008DQ_OK`. Log: `/home/etbra/008dq-weather-memory-rollout.log`.

O instalador troca o executável do serviço de controle pelo wrapper que mantém os dois experimentos. Usa o mesmo timer para impedir dois escritores concorrentes do controle, preservando checkpoint, previsões e contagens de 008DP. Guarda a unidade e módulo anteriores para rollback. Os registros reais já confirmados no núcleo não são apagados no rollback.

Após instalar: confirmar ingestão/recuperação, os primeiros pares e suas diferenças de erro. A próxima etapa poderá expor os resultados ao painel/narrador e testar contexto novo. Influência do previsor sobre a física exigirá um protocolo separado para não confundir previsão com resultado produzido por ela própria.

### Resultado da amostra real em banco isolado

Erro vetorial do vento: controle 0.143563 m/s, memória 0.206276 m/s (pior). Erro da cobertura de nuvens: controle 0.005612, memória 0.000609 (melhor). Erro de temperatura: controle 0.022602 °C, memória 0.108591 °C (pior). Previsão persistida antes do alvo; os IDs usados vieram da API do núcleo congelado em banco temporário. Esta amostra registra resultados mistos, sem justificar conclusão de melhoria geral. O serviço 008DQ ainda precisa ser instalado em produção.
