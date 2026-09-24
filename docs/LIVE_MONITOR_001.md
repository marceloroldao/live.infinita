# Live Monitor 001

## Objetivo

Separar o **Programa** (imagem limpa transmitida ao público) do **Monitor** (preview + telemetria do operador).

## Acesso

`/monitor/`

O monitor usa a mesma chave de operador já usada em `/manage/`. A chave é mantida somente em memória na aba do navegador e não é gravada em `localStorage` ou `sessionStorage`.

## O que o Monitor mostra

- preview 9:16 do Godot em modo `capture=1`;
- áudio do programa sob ação explícita do operador;
- Runtime online/offline;
- replay íntegro/falha;
- relay de áudio online/offline;
- TikTok configurado/não configurado;
- OpenAI configurada/não configurada;
- sequência, versão, entidades e período do World State;
- narrativa atual;
- contadores de eventos de audiência, atores e propostas.

## Estados mestre

- `PRONTO`: Runtime, replay e relay de áudio respondem corretamente;
- `DEGRADADO`: Runtime responde, mas algum componente essencial falha;
- `OFFLINE`: Runtime não responde;
- `BLOQUEADO`: chave de operador ainda não validada.

O monitor **não declara `LIVE`** nesta versão porque ainda não existe telemetria autoritativa do Broadcaster/RTMP confirmando que a plataforma está recebendo a saída. Esse estado será adicionado quando o Broadcaster ganhar health próprio.

## Segurança e invariantes

- o Monitor é somente leitura;
- não chama `/api/simulate` nem `/api/world/reset`;
- não pode iniciar ou parar o Broadcaster;
- não contém stream key;
- o preview usa a mesma cena de apresentação, mas não é dependência do pipeline de transmissão;
- fechar o navegador não interrompe Runtime, Godot nativo, áudio ou Broadcaster.

## Próxima evolução

Adicionar health autoritativo do Broadcaster com FPS, bitrate, uptime, frames enviados, reconnects e estado da saída RTMP/RTMPS. Só então o Monitor poderá diferenciar `PRONTO` de `LIVE` com segurança.
