# 008CL — consulta estável e percurso repetido

## Falha reproduzida

No núcleo Memoria.ia instalado (dfd87c995b50c49b45a9d5dd4c43cce456983d4f), StructuralObservationStore.recent calcula o deslocamento com count e depois chama ordered_from sem limitar a leitura. Novos registros entre essas operações ampliam a resposta. A API aceita limit=100, mas pode retornar 103 registros se três chegarem nesse intervalo; o exportador corretamente recusava o contrato acima de 100.

A reprodução usou a implementação real, API FastAPI e SQLite temporário, inserindo três registros precisamente entre o cálculo e a leitura. Resultado: pedido 100 → resposta 103; pedido 64 → resposta 67.

O cliente agora pede 64, mantendo margem até o limite validado de 100. Se a janela ainda ultrapassar 100, repete uma vez e então falha explicitamente. Não corta a resposta, não relaxa o contrato e preserva o cache anterior em caso de falha. O núcleo instalado não é modificado. A solução definitiva do lado do servidor seria uma janela atômica ou paginação com limite aplicado na leitura.

## Resultado do teste de navegação

Godot com CharacterBody3D, três obstáculos físicos em U, mesmo início e objetivo, delta fixo de 0,1 s, navegação e percepção atuais. Cada rodada cria um navegador novo, sem rotas locais, falhas locais ou RAM previamente preenchidas.

A primeira rodada concluída gerou 23 passos de rota. Eles foram enviados à API real do núcleo em banco temporário; o banco foi reaberto e os 23 registros foram recuperados pela API e pelo exportador. A segunda execução compara memória desligada e ligada usando esse cache. O controle desligado reproduziu exatamente a primeira rodada.

| Medida | Sem memória | Com registros recuperados |
|---|---:|---:|
| Chegou ao objetivo | Sim | Sim |
| Caminho percorrido | 57,62 m | 22,52 m |
| Tempo simulado | 5,8 s | 2,4 s |
| Decisões de navegação | 58 | 22 |
| Decisões diferentes atribuídas à memória | 0 | 7 |
| Colisões | 0 | 0 |

Redução de caminho: aproximadamente 61%; redução de tempo simulado: aproximadamente 59%. A percepção já evitava colisões nas duas rodadas. O ganho foi eficiência do percurso, não redução de colisões.

É um experimento isolado, não uma medição de desempenho da live nem prova de generalização. Os dados de memória foram passos da primeira rota concluída usados como fixture; este teste não valida o critério de três reutilizações causais da promoção RAM. Não foram escritos dados na Memoria.ia de produção nem alterado o World State. Tempos são ticks simulados, não tempo de CPU ou latência da API.

## Reproduzir e instalar

O projeto Godot passado ao benchmark deve ser uma cópia isolada com recursos já importados. Nunca importar o projeto fonte para executar este teste.

Exemplo: `PYTHONDONTWRITEBYTECODE=1 /opt/live.infinita/.venv/bin/python tools/benchmark_navigation_repeat_008cl.py --godot-project /home/etbra/008bz-godot-test --report /home/etbra/008cl-repeat-result.json`.

Resultado registrado: NAVIGATION_REPEAT_RESULT_008CL.json. Validação: 55 testes Python, benchmark físico com controle reproduzido, gravação/ACK/recuperação após reabertura do SQLite e reprodução da corrida na API real.

Instalação apenas da sincronização: `sudo bash /home/etbra/live.infinita/deploy/apply-navigation-recall-stability-008cl-root.sh`. Não reinicia renderer ou Memoria.ia; o instalador existente faz backup/rollback e verifica o serviço. Sucesso: `008CL_OK`.

Próximo teste: instrumentar percursos naturais repetidos da live para medir ganhos com as promoções RAM reais, sem escolher previamente a rota e sem confundir acordo com a percepção com influência da memória.
