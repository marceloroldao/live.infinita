# 008EJ — custo local independente do destino

A 008EI registrava e recuperava contornos reais, mas não alterava decisões por preferência de padrões na coleta observada. A inspeção dos 51 registros mostrou que o avaliador ainda dividia o custo local pela distância até o destino final. Além de colocar muitos escores abaixo do limiar mínimo de 0,2, isso fazia o mesmo desvio parecer mais barato quando o destino estava distante.

## Mudança

O perfil `capsule044-height18-lookahead3-contour64-localexit-v3` divide a distância física do contorno por uma escala fixa de 3 m, correspondente ao alcance de antecipação deste perfil. A distância ao destino continua registrada como telemetria. Jornadas históricas continuam com a regra anterior. O núcleo armazena e recupera fatos; o aplicativo calcula o custo e a preferência.

Permanecem o mínimo de duas amostras por lado, a janela recente de 32 por lado, a margem de 20%, a abstenção em empates e as verificações físicas. A penalidade de erro permanece 20 unidades: equivale a 60 m adicionais por fração de erro na escala nova. O custo individual continua limitado a 100 unidades (300 m no novo perfil). Esses valores são escolhas de política, não parâmetros aprendidos automaticamente pelo núcleo.

Resultados, checkpoint e recall usam arquivos `008ej.json`. Os registros v1/v2 são preservados, mas separados da coleta v3. A ponte filtra perfil antes de validar. O transporte continua v2 porque os campos físicos não mudaram. O coletor começa uma série própria, sem converter nem reingerir fatos antigos.

## Verificação

44 regressões Godot e 13 testes da ponte Python passaram. Sintaxe dos instaladores e validação das unidades systemd passaram (avisos de CPUAccounting em unidades XFS do sistema são alheios a esta mudança).

O teste `godot_local_cost_008ej_smoke.gd` troca distâncias finais de 10 e 1000 m mantendo contornos de 3 e 6 m: escores e escolha permanecem idênticos. Também verifica diferença de 3 versus 4 m com destino distante, abstenção em custos iguais e mudança de preferência após colisões físicas. A ponte passa com perfis antigos coexistindo e rejeita registros inválidos do atual.

Reanálise somente em RAM dos 51 fatos da live: nenhuma recomendação pela regra anterior; uma pela escala nova, na assinatura `local-clear-v1:255:253`, lado +1. As outras 27 assinaturas continuam sem recomendação por falta de evidência suficiente ou margem. O contexto original foi preservado na análise; apenas o marcador de perfil foi alterado na cópia transitória para exercitar a regra nova. Nenhum movimento da live foi alterado nem evento gravado no núcleo de produção por esse teste.

No núcleo SQLite real fixado em `dfd87c995b50c49b45a9d5dd4c43cce456983d4f`, quatro resultados nativos v3 foram armazenados e recuperados após reabrir o núcleo e apagar o cache. Um envelope legado sintético, restrito ao teste, foi ignorado. Percepção: 234,5723 m / 70,4 s; RAM e núcleo recuperado: 106,6055 m / 32 s, sem colisões ou resgates. Esse cenário já apresentava vantagem antes; a mudança mantém esse resultado e corrige a dependência artificial do destino. Não demonstra vantagem adicional nem aprendizado na live.

A assinatura local ainda pode juntar obstáculos ocultos diferentes. Precisamos observar decisões alteradas e comparar custos em condições equivalentes após aplicar.

## Aplicação

Execute `sudo bash /home/etbra/apply-local-pattern-cost-008ej-root.sh`. O instalador tem backup e rollback, pausa a ponte, executa as regressões e verifica perfil v3 e escala pública de 3 m. Preserva memórias, animais e históricos. Não foi executado pelo Codex; a live continua na 008EI até aplicar. Use este instalador para o checkout atual.

Evidências: `LOCAL_COST_SOURCE_008EJ.json`, `LOCAL_COST_SHADOW_008EJ.json`, `LOCAL_COST_SMOKE_008EJ.txt`, `LOCAL_COST_BRIDGE_TESTS_008EJ.txt`, `LOCAL_COST_NATIVE_{RESULT,COLD,CORE}_008EJ.*` e `LOCAL_COST_REGRESSIONS_008EJ.{json,txt}`.
