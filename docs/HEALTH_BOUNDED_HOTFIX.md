# Hotfix — health HTTP com janela limitada

Incidente de 28/09/2026: o endpoint de health consultava sincronicamente o
arquivo de shadow, que ultrapassou 580 MB. Isso ocupou o event loop do Uvicorn
e tornou a API HTTP indisponível durante varreduras longas, apesar do serviço
systemd permanecer ativo.

## Contratos de leitura

`GET /api/health` agrega somente os últimos 262.144 bytes do diário shadow.
Os campos numéricos de `cognitive_gym_v2.shadow_observer` representam uma
**janela recente**, não totais históricos. O payload declara:
`metrics_scope=recent_window`, `max_window_bytes=262144` e
`complete_metrics_path=/api/cognitive/v2/shadow/metrics`.

`GET /api/cognitive/v2/shadow/metrics` mantém a agregação histórica completa,
autenticada pelo operador. A varredura é executada via `asyncio.to_thread`
para não monopolizar o event loop. Esse endpoint pode continuar custoso em
I/O/CPU e deve ser consultado apenas quando necessário. Nunca comparar um
contador recente com totais históricos como se representassem o mesmo universo.

A agregação parcial descarta a primeira linha truncada da janela e ignora
eventual fragmento final, sem inventar métricas. Se o arquivo não existe, o
resumo segue vazio.

## Deploy cirúrgico

`deploy/health-bounded-hotfix.sh` (alias de VM:
`~/deploy-health-hotfix.sh`) valida que o código foi integrado à main,
faz backup dos dois módulos alterados, sincroniza **somente** esses módulos
em `/opt` e reinicia apenas `live-infinita.service`. Não reinicia
`live-infinita-autonomous-world.service` nem modifica as trilhas de dados.
Verifica resposta HTTP em janela, autoridade do shadow, PID autoritativo
inalterado e replay posterior. Execute como etbra, sem sudo no comando externo.

## Limitação

Esta correção resolve o bloqueio causado pela varredura síncrona do shadow no
HTTP. **Não resolve o OOM do processo Single Writer**: seguir a investigação
de retenção de memória e capacidade da VM no incidente GitHub #66.
