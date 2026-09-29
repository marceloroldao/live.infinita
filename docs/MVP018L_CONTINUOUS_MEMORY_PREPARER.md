# MVP-018L — Preparador contínuo a partir do Nov observado (canary primeiro)

## Por que o frame mudou

O MVP-018K comprovou 354 episódios validados, preparo assíncrono em outro
processo e leituras em RAM (20 peeks, mediana 0,153 ms; máximo 5,221 ms).
O frame daquele gate era **retrospectivo**: localização baseada no último
episódio confirmado. Não era uma projeção da localização atual do Nov.

A nova `sample_current_nov_frame` lê apenas arquivos existentes da Live:
`world.json`, o manifesto do armazenamento por região e somente o arquivo
da região apontada para `nov`. A leitura usa `world-mutation.lock` com
`LOCK_SH | LOCK_NB`: se o escritor está ativo, **abstém**, sem bloqueá-lo.
Tamanho, esquema, identidade da entidade e região são conferidos; o frame
real tem o tick, estado de mundo e endereços atuais de região, período,
clima e necessidades da entidade. Nenhum motor autoritativo ou construtor
de armazenamento é instanciado. Ainda há uma diferença importante:
`frame_query` usa a necessidade do **último episódio confirmado** e a
região/clima/período do frame observado. Não se deve apresentar a necessidade
histórica como intenção atual ou prova de aprendizagem.

## Ciclo de preparação

`nov_memory_continuous.py` mantém um `OwnerAsyncDualLanePreparation`
explícito no processo do usuário `liveinfinita`. A cada dois segundos
amostra o frame sob lock compartilhado. Requisições ficam em fila de
capacidade um; enquanto uma está pendente não envia outra, salvo timeout
limitado. Atualiza após até quatro segundos de intervalo ou status de
abstenção. Fonte V2, checkpoint, identidade do mundo, TTL 6s, limite de
20 ticks e duas evidências `freeze_memory_context` separadas continuam
verificados pelo preparo assíncrono.

Saída contém apenas status, contagens e vetores numéricos de coincidência;
não imprime região atual, nomes de necessidade, world_id, resultados, hashes,
evidence IDs ou observações. Não publica pacote/IPC e não modifica o mundo,
memória original, checkpoint ou processo de seleção de ações.

## Primeiro gate: seis amostras reais em processo isolado

```bash
cd ~/live.infinita && bash deploy/mvp018l-nov-continuous-gate.sh
```

O script requer autenticação `sudo` diretamente no terminal do operador,
antes de iniciar a captura de saída. Depois executa apenas código **público**
copiado para diretório temporário, como `liveinfinita`, com a versão
pinada da Memoria.ia V2. A captura redigida fica em
`~/nov-memory-continuous.log` (0600). Saída esperada:
`MVP018L_OWNER_STATUS`, `MVP018L_OWNER_CANARY_OK`,
`MVP018L_NO_SERVICE_INSTALL_OR_CUTOVER`. Se o mundo estiver em
mutação no instante de alguma amostra, pode haver abstenção;
o gate exige ao menos uma leitura pronta para declarar OK.

Não instala um serviço, não reinicia nada, não expõe dados da raiz privada.
A duração inclui seis amostras de intervalo 1s, além da carga inicial.

## Unidade opcional, ainda DESLIGADA

`deploy/live-infinita-nov-memory-prepare.service` é somente um template
para um estágio futuro. Usuário/grupo `liveinfinita`, sem rede,
`ProtectSystem=strict`, somente a raiz privada para scratch da V2,
mundo/cold-store em leitura, prioridade de CPU/IO reduzida e limites de RAM.
**Este PR não copia a unidade para /etc, não habilita, não inicia e não altera
autonomous_runtime_main.py.** Antes disso é necessário validar o canary e
desenhar uma fronteira IPC com autenticação de par, timestamps, versão do
snapshot, expiração e projeção pública sem evidência privada.

## Limitações observacionais

- `LOCK_SH` garante consistência local da leitura; não torna o snapshot
  contemporâneo em todos os consumidores ou prova que novas observações da
  Memoria.ia já foram confirmadas.
- O `OwnerAsyncDualLanePreparation` é histórico e valida versão por
  sondagem, não por transação distribuída com o mundo. O processo autônomo
  não o consome.
- A variabilidade do caminho frio e das pontas de latência ainda deve ser
  medida na canary real; estes testes não demonstram utilidade cognitiva
  nem ação escolhida.
- Nenhum BDR cutover, sync central, seleção de rota ou migração é feito.
