# 008EM — identidade e encerramento de contatos de navegação

A medição 008EL encontrou muitos contatos excluídos por novo contato antes de uma saída confirmada. A inspeção dos episódios nativos mostrou mudanças de contato ao longo da margem do rio, incluindo passos opostos ao rumo anterior e quadros inativos sem proposta de saída. O código reinicia o quadro quando o lado observado termina; essa seleção ocorre antes do movimento físico. Isso é um reenquadramento da navegação, não comprovação de ter superado um objeto.

## Correções reproduzidas

O coletor removia uma tentativa excluída de `pending`, mas não a marcava como encerrada. Um callback posterior do mesmo contato podia reabri-la, excluir seu sucessor e criar crédito novo. Além disso, o laço de registro de falhas não exigia correspondência entre o número de contato do callback e o contato pendente.

O teste isolado contra o código anterior reproduziu dois erros: uma ação atrasada substituiu o contato mais novo, e uma colisão do contato já excluído gerou novo registro de falha. Com a correção, ambos passaram sem erro. Esse teste comprova o defeito do componente; não estabelece que todos os eventos excluídos da live resultaram desse defeito.

Uma exclusão agora encerra a identidade. O índice de encerrados permanece limitado a 64 contatos, e o maior número de contato do objetivo atual impede reabrir identidades anteriores mesmo após sua saída do índice. Um callback só conclui ou penaliza o contato cujo número coincide com seu quadro ou proposta de saída. Objetivos e mundos continuam sujeitos às verificações anteriores.

## Motivo de reenquadramento

O quadro expõe `turn_pending`, `forced_turns` e `reset_event`, contendo número do contato e motivo. Reinícios indicam `observed_side_end`, `goal_changed`, `near_goal_clear_corridor`, `trial_error_disabled` ou `route_plan_reset`, conforme o caminho executado. `clear_exit_proposed` continua sendo apenas proposta: sem avanço físico confirmado, um contato seguinte mantém a exclusão `new_contact_before_executed_exit`.

O coletor usa o motivo do quadro quando ele identifica precisamente o contato anterior. Assim, o diagnóstico distingue a censura por fim de um lado observado de outros reinícios. Nenhum reenquadramento é convertido em sucesso ou penalidade. Não houve mudança de movimento, física, preferência, margem ou escala. O perfil v3 e os arquivos `008ej.json` permanecem, preservando os fatos acumulados.

## Validação

46 regressões Godot passaram. A reprodução do código anterior teve dois erros esperados e a versão corrigida teve zero. Sintaxe do instalador e export, igualdade da cópia executável e unidades systemd verificadas; avisos de CPUAccounting em unidades XFS do sistema são alheios à atualização.

O teste de ciclo de vida cobre exclusão explícita, não reabertura, proteção do sucessor, callback inativo sem correspondência, colisão real correspondente, idempotência, limite de memória e proteção após descarte de identidades antigas. Também verifica que fim de lado não produz proposta de saída bem-sucedida.

A comparação nativa com o núcleo SQLite real mantém o cenário reservado: percepção 234,5723 m / 70,4 s; RAM e núcleo recuperado 106,6055 m / 32 s, sem colisão, resgate ou busca global. A recuperação após reabrir o núcleo e apagar o cache passou, preservando isolamento de perfil. Este resultado não demonstra ganho adicional desta correção nem vantagem na live.

## Aplicação

Execute `sudo bash /home/etbra/apply-contact-lifecycle-008em-root.sh`. O instalador cria backup e rollback, inclui o módulo de experiência com os novos motivos, mantém os dados v3, pausa a ponte durante a atualização e verifica a versão pública. Não foi executado remotamente pelo Codex.

Após aplicar, repetir a medição 008EL e observar os motivos de exclusão. A frequência de censura real por reenquadramento pode continuar alta; esta correção melhora identidade e atribuição, sem inventar conclusões. Uma alteração futura na estratégia de contorno exige teste físico próprio.
