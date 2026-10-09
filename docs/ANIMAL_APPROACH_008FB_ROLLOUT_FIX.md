# 008FB — correção da validação do rollout

A aplicação de 3fb5932 terminou em AssertionError na primeira checagem nativa e executou rollback. A versão anterior voltou a funcionar às 19:32:25 UTC de 09/10/2026. Estado e memórias continuam disponíveis. A nova ação não está ativa nesta verificação.

O instalador usava timestamp inteiro e afirmava imediatamente a presença do campo approach ao encontrar uma publicação recente. Isso permitia tratar como nova uma publicação da versão anterior no mesmo segundo do reinício. A checagem agora espera até receber o formato novo com a opção ativa e timestamp com precisão fracionária. Estado antigo pode aguardar dentro do orçamento, sem disparar uma assertiva imediata.

O rollback agora para o renderer antes de remover/restaurar os scripts. O registro da tentativa contém erro de preload do módulo novo enquanto a restauração estava em curso; a cópia isolada do projeto de produção com os quatro arquivos novos iniciou sem esse erro. A ordem de restauração anterior expunha o processo iniciado a arquivos sendo trocados. Não há evidência de que o módulo estivesse faltando na fonte ou na lista de instalação.

Quatro testes executam a checagem Python extraída do instalador: publicação anterior seguida pela nova, publicação anterior até o fim do orçamento, timestamp anterior mesmo com a opção ativa e ordem de parada no rollback. Todos passaram. O código de aproximação e a física não foram modificados nesta correção; as 102 regressões anteriores continuam como evidência da implementação. A cópia do projeto de produção iniciou com WORLD_MAP_PREVIEW_READY e sem erros de script. Não houve erros de script na janela auditada após a restauração.

Os logs e o resumo estão em ANIMAL_APPROACH_008FB/. Os instaladores corrigidos foram copiados para /home/etbra e precisam ser executados novamente pelo usuário; nenhum sudo foi executado pelo agente.
