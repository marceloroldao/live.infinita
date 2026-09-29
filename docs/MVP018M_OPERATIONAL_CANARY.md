# MVP-018M — observabilidade e canary operacional estendido do Nov

## Evidência de entrada

O canary independente anterior (`MVP018L_OWNER_CANARY_OK`) executou seis
ciclos, oito chamadas ao monitor, cinco leituras prontas, três abstenções
e dois envios, mantendo cinco lembranças primárias e três suplementares
quando disponível. Este resultado comprova o caminho observado de memória,
**não** estabilidade de um serviço permanente nem utilidade da decisão.

## Implementação

O monitor proprietário `nov_memory_continuous.py` mantém agora contadores
redigidos que correspondem a **cada chamada de `step`**, inclusive as
chamadas adicionais do canary enquanto aguarda a thread:
`status_counts`, `samples`, `ready_reads`, `abstentions`,
`longest_not_ready_streak`, `frame_tick_advances` e
`frame_tick_regressions`. Só rótulos conhecidos são publicados; exceções,
endereços, IDs, hash, conteúdo do mundo e resultados observados não entram
no log.

O resumo contém ainda `ready_fraction`, `elapsed_seconds`,
`peak_rss_kib` do processo (inclui a thread), e mediana/máximo de
`step` em milissegundos. A latência de `step` mede o observador
independente, **não** a reconstrução paralela V2 ou o tick autoritativo.
O canary ainda pode executar `wait_ready` somente no processo de ensaio.

`nov_memory_operational_gate.py` analisa **somente o relatório redigido**
gravado em 0600. Valida esquema, um único marcador de conclusão,
contabilidade, ausência de autoridade, origem histórica e limites de
recurso. Produz apenas motivos enumerados em caso de bloqueio.

## Gate manual de cerca de dois minutos

```bash
cd ~/live.infinita && git pull --ff-only && bash deploy/mvp018m-nov-extended-canary.sh
```

O script executa 60 ciclos a cada 2 s, prepara só código Python público
em diretório temporário, pede `sudo` no terminal do operador e roda a
Memoria.ia V2 pinada como `liveinfinita`. O relatório fica em
`~/nov-memory-extended-canary.log` (0600), com marcadores finais
`MVP018L_OWNER_CANARY_OK` e `MVP018M_OPERATIONAL_GATE_OK`. A conexão
Desktop Commander não é necessária. Nenhum dado privado sai da raiz 0700.

A política inicial de aprovação operacional exige:
- 60 ciclos e pelo menos 60 amostras contadas consistentemente;
- no mínimo 12 leituras prontas, taxa de prontidão de ao menos 30%,
  e no máximo 20 amostras seguidas sem contexto pronto;
- dois envios e cinco avanços de tick ou mais, sem regressão;
- pico RSS até 384 MiB e cada `step` até 250 ms;
- `world_mutated=false`, `selection_authority=false`, sem BDR,
  sync central, alegação de `live_caught_up` ou ligação ao runtime.

Esses limites são **margens de segurança operacional preliminares**:
não rotulam experiências como boas/ruins e não medem aprendizado
cognitivo. Uma execução que bloqueie preserva o mundo e fornece motivos
curtos para investigação, sem alterar thresholds silenciosamente.

## Serviço permanente e IPC

O template `deploy/live-infinita-nov-memory-prepare.service` permanece
**somente no repositório**. Este estágio não instala, habilita, inicia,
reinicia nem conecta essa unidade; não altera
`autonomous_runtime_main.py`, políticas de seleção ou arquivos da
memória original. O canary lê a entidade Nov sob lock de leitura
compartilhado e não bloqueante; se o escritor está ativo, registra
`frame_unavailable` e se abstém.

O serviço permanente requer etapa separada de instalação, rollback e
observação em janela maior. A futura entrega entre processos deverá ter
um contrato de socket Unix ou outro IPC local com identidade do par,
permissões de diretório, limite de mensagem, mundo, tick, versão de fonte,
TTL e abstenção. Como o mundo e o proprietário hoje compartilham o UID
`liveinfinita`, `SO_PEERCRED` isolado não diferencia processos desse
mesmo usuário. É necessário definir separação de identidade ou controles
adicionais antes de chamar esse IPC de autenticado. Não introduzimos
socket ou payload privado nesta etapa.
