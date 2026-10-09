# 008FB — aproximar-se de coelhos avistados

A live já tinha visão por raios físicos, três coelhos com comportamento de fuga e procura limitada por regiões inferidas de encontros recuperados. Faltava conectar a confirmação visual à aproximação física. Esta etapa acrescenta essa ligação; captura, fome de Nov e aprendizado de estratégias de caça ainda não foram implementados.

## Comportamento

A opção nativa `LIVE_INFINITA_ANIMAL_APPROACH_ENABLED=1`, desligada por padrão, habilita o controlador de aproximação. Ele recebe somente observações do sensor ocular existente: mundo e espécie corretos, posição finita, timestamp válido e confirmação `eye_ray_unobstructed`. Não consulta o registro físico dos animais, seus nós, recursos ou movimentos ocultos.

Um coelho visto entre 6,5 e 24 metros pode gerar uma aproximação de até 20 segundos. O controlador escolhe um destino cinco metros antes da última posição observada, passando pelo resolvedor de terreno existente. O movimento segue a navegação e colisões já usadas por Nov; não há teleporte, rota global ou acesso ao destino verdadeiro de um animal escondido.

Avistamentos expiram em 1,5 segundo, tanto no relógio lógico quanto no tempo real local. A aproximação termina por perda de contato, oito segundos sem progresso, destino rejeitado, limite de tempo, pausa, troca de mundo, retrocesso de relógio ou recuperação de navegação. Nov conserva apenas a última posição observada durante essa tolerância; não extrapola velocidade nem prevê a fuga nesta etapa.

O resultado `approached` requer distância horizontal de até 6,5 metros à posição observada, com confirmação visual de no máximo 300 ms lógicos e 500 ms reais. Trata-se de proximidade ao avistamento recente, não contato físico ou captura. A distância inicial permite parar perto do limiar de fuga existente sem acrescentar perseguição prolongada.

A mesma intenção conserva seu destino enquanto o alvo observado não mudar pelo menos dois metros. Retargeting ocorre no máximo uma vez por segundo, com revisão explícita do objetivo para a navegação não manter um destino antigo. Cada revisão encerra a jornada anterior como interrupção de intenção, sem inventar penalidade física. Há intervalo de 60 segundos entre aproximações na sessão.

Uma confirmação visual encerra a procura anterior pela região e permite tentar a aproximação. Quando termina, a caminhada normal e a busca existente continuam. Buscas por previsão conservam seus limites, alternância e contadores anteriores.

## Painel, resultados e memória

O painel distingue `visible` de `memory` e `last_seen`: mostra “aproximando-se de coelho avistado”. A prévia web aceita apenas a intenção publicada pelo renderer, com formato, origem, espécie e prazo validados; não decide a aproximação.

O arquivo público existente `wildlife/search-intent.json` ganha o campo `approach`, incluindo estado, opção ativa e até 16 resultados da sessão. O checkpoint privado das buscas mantém o esquema anterior e os contadores já gravados. As aproximações são transitórias: reiniciar o renderer não restaura nem confirma uma aproximação interrompida, e o cooldown dessa nova ação não é persistente.

Os eventos `NOV_ANIMAL_APPROACH_START` e `NOV_ANIMAL_APPROACH_END` registram entidade, tempo, motivo e distância percorrida. Não são ingeridos no core nesta etapa e não demonstram aprendizado de caça. O armazenamento e a recuperação dos encontros visuais existentes continuam pelo pipeline anterior. Resultados de aproximação não entram nos contadores de acerto de regiões previstas, e “contact_lost” não afirma ausência do animal no mundo.

A próxima etapa deverá definir evidência física de perseguição/captura e atribuição de custo antes de usar essas tentativas para mudar estratégias.

## Verificação

O contrato testa uma parede física ocultando um alvo registrado no sensor, liberação da linha de visão e movimento incremental de CharacterBody. A aproximação percorreu cerca de 3,6 metros, sem colisão, e só confirmou proximidade após novas observações reais. O teste também cobre perda de contato, rejeição do terreno, opção desligada, observação futura, relógio regredindo, alvo observado mudando de posição, falta de progresso e orçamento.

A integração à cena nativa usa explicitamente uma observação adaptada como fixture de contrato para verificar o encaminhamento à locomação existente; ela não é apresentada como nova observação real nem ingerida na memória. O teste com alvo móvel altera um corpo do cenário controlado; não demonstra caça de coelhos autônomos ou melhoria aprendida.

Foram aprovados 51 testes com a opção ligada e 51 com ela desligada, além de contratos finais da aproximação e das buscas existentes nos dois modos, após reforço da validação de timestamps e do cancelamento público em pausas. As duas rodadas da lista completa do exportador e os logs dos contratos estão em `docs/ANIMAL_APPROACH_008FB/`. A regra de proximidade não prova desempenho de caça na live; o comportamento depende de avistamentos reais, e os animais existentes não são deslocados para forçar uma demonstração.

Reprodução após sincronizar o projeto de teste:

```bash
python3 tools/run_animal_approach_regressions_008fb.py --output-dir /home/etbra/008fb-reproduction
```

## Aplicação e reversão

O instalador exige checkout limpo, cria backup de código/configuração/web, executa exportação e testes, aplica um drop-in próprio e confirma publicação recente com `approach.enabled=true`. Confirma também as quatro opções anteriores de navegação, o bridge e o manifesto público. Erros acionam rollback. Não apaga banco, experiências, estado dos animais ou buscas.

O instalador foi preparado para execução pelo usuário; não foi executado pelo agente:

```bash
sudo bash /home/etbra/apply-animal-approach-008fb-root.sh
```

Para desligar apenas esta ação, mantendo as memórias e a navegação:

```bash
sudo bash /home/etbra/set-animal-approach-008fb-root.sh off
```

Use `on` para religar. O áudio e demais serviços da live não foram alterados nesta etapa.
