# 008EI — crédito por contorno local executado

A verificação da 008EH na live encontrou decisões de contorno, mas nenhum resultado elegível para padrões: o coletor esperava o final da caminhada e descartava jornadas com múltiplos contatos. A 008EI mede cada contato separadamente, mantendo os resultados já concluídos quando Nov encontra outro obstáculo ou a caminhada termina depois.

## Regra de crédito

Cada contato recebe identidade própria (sessão, objetivo e número do contato). O custo é a distância realmente percorrida desde sua primeira ação física registrada. A percepção pode propor a saída, mas o registro `contour_completed / executed_exit` exige movimento executado pelo corpo com `move_and_collide`, sem colisão, e avanço de pelo menos 0,75 m na normal do contato. O evento registra `completion_basis` e `exit_progress_m`. A chegada física elegível ao objetivo também pode concluir o último contato, com base `goal_reached`.

Colisão física executada registra `blocked / physical_collision`; recuperação por aprisionamento registra `stuck_recovery` apenas para o contato ainda ativo, antes do teletransporte. Rejeição preventiva pela física não vira erro aprendido. Mudança de mundo, troca de objetivo ou novo contato antes de confirmar a saída excluem a amostra incompleta e contam o motivo em `patterns.exclusions`. Resultados concluídos recebem crédito uma vez.

O perfil `capsule044-height18-lookahead3-contour64-localexit-v2` e os documentos v2 separam estes custos locais dos antigos custos da jornada inteira. Arquivos antigos e histórico do núcleo são preservados. A ponte usa arquivos `*-008ei.json`, recibos reais e recuperação verificada. O aplicativo calcula a preferência de lado; o núcleo armazena e recupera as observações. Não há busca global de rota neste modo.

## Validação antes de instalar

- 43 testes de regressão do Godot aprovados; 11 testes da ponte Python aprovados, incluindo rejeição de saída insuficiente e fundamento incompatível de falha.
- Teste físico com duas paredes e aberturas opostas: chegada em 244 ticks (24,4 segundos simulados), 81,3919 m, nenhuma colisão, resgate ou planejamento global.
- Foram registrados três contatos, com custos locais de 11, 16 e 4 m e avanços de saída de 0,9859, 0,9652 e 0,9987 m. Dois objetos podem produzir mais de um contato; a identidade é do contato de navegação, não do objeto.
- Comparação isolada com o coletor nativo e o núcleo SQLite real fixado em `dfd87c995b50c49b45a9d5dd4c43cce456983d4f`: quatro resultados físicos armazenados e recuperados após reabrir o núcleo e apagar o cache. Sem nova ingestão na recuperação. No cenário reservado, percepção: 234,5723 m / 70,4 s; RAM e núcleo recuperado: 106,6055 m / 32 s. Todos sem colisão ou resgate.
- Sintaxe dos instaladores e unidades systemd verificada. Avisos de CPUAccounting em unidades XFS do sistema são alheios a estas unidades.

Os testes demonstram o mecanismo e vantagem neste cenário controlado. A 008EI ainda precisa ser aplicada e observada na live para comprovar ganho em produção. A assinatura local continua limitada: aberturas ocultas diferentes podem compartilhar a mesma assinatura, como demonstrado na 008EG. Saída local confirmada não significa sucesso de toda a caminhada.

## Aplicação

Execute `sudo bash /home/etbra/apply-local-contour-feedback-008ei-root.sh`. O instalador exige checkout limpo, cria backup, pausa a ponte durante a atualização, exporta com os testes, atualiza renderer e ponte, reinicia o renderer e verifica estado recente e versão pública. Possui rollback de código, unidades e arquivos públicos; não apaga memórias, animais ou histórico. Não foi executado remotamente pelo Codex.

Após aplicar, verificar `008EI_OK` em `/home/etbra/008ei-local-contour-feedback-rollout.log`, eventos `NOV_PATTERN_OUTCOME`, contadores/exclusões no estado de aprendizado, confirmações da ponte e decisões com `observation_ids`. Para avaliar vantagem na live, comparar custos e falhas em condições equivalentes, separando percepção, exploração, RAM e núcleo recuperado.

## Evidências

`LOCAL_CONTOUR_MULTI_RESULT_008EI.json`, `LOCAL_CONTOUR_OUTCOMES_008EI.json`, `LOCAL_CONTOUR_MULTI_008EI.txt`, `LOCAL_CONTOUR_UNIT_008EI.txt`, `LOCAL_CONTOUR_BRIDGE_TESTS_008EI.txt`, `LOCAL_CONTOUR_REGRESSIONS_008EI.json` e `LOCAL_CONTOUR_REGRESSIONS_008EI.txt` contêm as verificações. `NATIVE_PATTERNS_RESULT_008EI.json`, `NATIVE_PATTERNS_COLD_008EI.txt` e `NATIVE_PATTERNS_CORE_008EI.txt` preservam a comparação real. O runner reutilizado mantém o identificador de cenário `native-pattern-008eh`; o perfil e os resultados dentro das evidências são v2.
