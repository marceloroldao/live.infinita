# MVP-018N — ciclo de vida do preparador contínuo: preflight sem instalação

## Resultado anterior

O MVP-018M executou 60 ciclos em 121 s com 94 amostras, 60 prontas
(63,83%), zero regressão de tick e zero etapas >250 ms. O pior `step`
foi 4,168 ms. O outlier anterior de 760,384 ms não se repetiu e **não
teve causa identificada**. O relatório comprovou `world_mutated=false`,
`selection_authority=false` e `main_runtime_wired=false`.

## Impedimento de empacotamento encontrado

O template anterior de `live-infinita-nov-memory-prepare.service` referia-se
a `/opt/live.infinita/apps/world-runtime/nov_memory_continuous.py`; esse
arquivo não existe na VM atual. O checkout publicado reside em
`/home/etbra/live.infinita`, enquanto `/opt/live.infinita` abriga o
ambiente Python. **Não utilizar o home do operador como raiz de execução
de um daemon**, nem declarar a unidade instalável a partir do template
anterior.

A unidade agora é um template de pacote plano, parametrizado por:
`@NOV_RELEASE_ROOT@` (diretório público versionado),
`@PINNED_CORE_ROOT@` (núcleo Memoria.ia V2 fixado) e
`@VENV_PYTHON@` (interpretador existente). Antes de qualquer futura
instalação, o release terá que ser copiado de forma imutável para
`/opt/live-infinita-nov-preparer/releases/<commit completo>`, com
arquivos regulares 0644, diretório não gravável por grupo/outros e
propriedade e integridade aprovadas pelo operador. A unidade final
deve referir-se somente a esse pacote e ao core fixado, nunca ao
checkout mutável do operador.

## Salvaguardas e saúde

A unidade permanece **não instalada/desligada**. Inclui dependência da
Memoria.ia local, memória máxima 384 MiB, prioridade CPU/IO reduzida,
limite de três tentativas de início por dez minutos, usuário
`liveinfinita`, `NoNewPrivileges`, `ProtectHome`, filesystem
estrito, raiz do mundo e raiz da memória explicitamente somente leitura,
`PrivateTmp` e rede negada.

O observador não cria socket, porta ou arquivo de estado compartilhado.
No modo contínuo, emite heartbeat redigido no journal somente a cada
15 ciclos (cerca de 30 s). Se não houver nenhuma leitura pronta durante
120 s, encerra com erro para o supervisor aplicar a política limitada
de reinício. O watchdog **não fica ativo nos canaries finitos**, que
continuam imprimindo cada ciclo. Status, contagens e tempos são a única
telemetria; nunca IDs, endereços, outcomes, evidências ou payloads.

## Teste sem root e sem tocar na memória privada

```bash
cd ~/live.infinita && git pull --ff-only && bash deploy/mvp018n-nov-lifecycle-preflight.sh
```

O preflight usa somente Python e código público, copia módulos para
`/tmp` com checagem binária, valida esquema e permissões do pacote,
renderiza um arquivo de unidade temporário, compila Python e chama
`systemd-analyze verify`. Exige que os dois serviços preexistentes
estejam ativos e que o preparador continue `not-found`. O arquivo
temporário é removido no final. Marcadores esperados:
`MVP018N_BUNDLE_OK`, `MVP018N_RENDERED_UNIT_OK`,
`MVP018N_SYSTEMD_TEMPLATE_OK`,
`MVP018N_NOT_INSTALLED_OR_STARTED`.

Esse teste comprova layout, sintaxe, caminhos e contrato público da
unidade; não executa o processo dentro do sandbox de systemd, não
instala unidade, não testa permissões sob o serviço persistente e não
substitui os gates de runtime. No próximo estágio, instalação opcional
exigirá rollback explícito, validação de UID, versão e recursos sob
systemd, período de observação, e aprovação do operador.

## Fronteira entre processos

O preparador e o mundo atualmente usam o mesmo UID. SO_PEERCRED sozinho
não identifica univocamente o processo permitido sob esse UID, e
arquivos da memória original são privados. Nenhum IPC foi introduzido.
Qualquer entrega ao Shadow Mode exigirá contrato separado de identidade
e capacidade, autorização de par, tamanho/tempo de vida da mensagem,
mundo/tick/versão, abstenção e **nenhum payload bruto em logs**.

O cache continua histórico, não afirma `live_caught_up`; o Nov continua
tomando decisões pelo mecanismo atual. O service unit não será ativado
automaticamente por merge de PR.
