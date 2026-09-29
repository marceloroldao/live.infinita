# MVP-018L — piloto de preparação contínua com frame real do Nov

## Motivo

MVP-018K mediu em 354 episódios V2: envio ao worker 0,122 ms,
20 leituras preparadas com mediana 0,153 ms e máximo 5,221 ms.
A validação fria foi 260,31 ms. A consulta era **retrospectiva**;
ainda não comprova reação a movimento, novo ACK nem ciclo de vida contínuo.

O mundo é mantido como `world.json` cold-backed. O observador Nov está em
`cold-store/manifest.json` e numa região em
`cold-store/regions/<sha256(region_id)>.json`. Ler apenas `world.json`
produziria uma localização presumida, sem integridade de entidade.

## Novo contrato

`nov_memory_live_frame_pilot.py` lê o mundo, manifesto e o arquivo da região
por limites de bytes. Exige modo `region_file_store`, exatamente um Nov,
região do objeto igual à do manifesto e entidade com origem local. Releitura
binária de cada arquivo deve corresponder ao valor anterior; qualquer
modificação intermediária produz abstenção, não contexto misturado.
Os endereços do frame são criados pelo `build_nov_cognitive_frame` original,
sem sintetizar uma região da última lembrança. Não usa
`FileRegionColdStore()` ou `ColdAuthoritativeWorldEngine()`, pois seus
construtores podem criar diretórios ou acionar fluxos do escritor.

`OwnerLiveFramePilot` executa **somente 20 ciclos de um segundo** num
processo proprietário independente: lê frame, faz `submit` ao preparador
assíncrono, aguarda fora do tick, lê um frame novo e consulta `peek` sem
acesso a SQLite. Resume ticks distintos, transições de região/ambiente,
leituras disponíveis e estados de abstenção; não revela o frame em si.
A thread paralela verifica versão da fonte e invalida resultados quando
detecta mudança de mundo/SQLite/WAL/checkpoint. Cada pacote tem TTL de
até seis segundos e lag máximo de 20 ticks; não afirma `live_caught_up`.
O piloto encerra e limpa memória da thread ao concluir.

O relato redigido expõe somente contagens e estados enumerados. Não há
endereço real, ID, hash, outcome, plano, payload, escrita de banco,
World State ou rede. A rota suplementar continua sem autoridade de
classificação ou escolha de ações. Não existe IPC para o processo do mundo.

## Execução operator-only, após CI e checkout na VM

```bash
cd ~/live.infinita && bash deploy/mvp018l-nov-live-frame-pilot.sh
```

O script exige usuário `etbra`, prepara somente fontes Python públicas em
`/tmp` e as roda via `sudo -u liveinfinita` com o núcleo Memoria.ia V2
pinado. Os arquivos 0700 da memória nunca são copiados para o home.
O resultado fica em `~/nov-live-frame-pilot.log` (0600), marcador
`MVP018L_PILOT_OK` ou `MVP018L_PILOT_BLOCKED`. Não precisa de instalação,
start, restart ou enable de unidades systemd, não toca no serviço de mundo.

## Gates para um serviço permanente

1. Identidade do frame e revalidação de mundo/manifesto/região sob escritas
   concorrentes; casos instáveis precisam abster, não assumir posição.
2. Pelo menos uma leitura pronta, estado de defasagem/expiração correto,
   transições de tick, nenhuma falha de serviço autoritativo durante ensaio.
3. Verificação de ACK do núcleo V2 ao longo de tempo suficiente; a janela de
   20 s pode não conter nenhum ACK de novo episódio. Se não houver, não
   alegar que atualização em tempo real foi demonstrada.
4. Definir contrato seguro entre processos com usuário, grupo, permissão de
   socket/diretório, limitação de payload e separação de autoridade. Nenhuma
   evidência sensível pode ser persistida no log público do runtime.
5. Só após esses gates criar e ativar um serviço proprietário persistente,
   com restart/backoff e health; sem V2 pesado no tick autoritativo.
