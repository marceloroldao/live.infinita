# 008CH — experiências cronológicas da navegação física

A 008CG foi confirmada instalada em produção em 4 de outubro de 2026, commit
738b959. O renderer registrou uma escolha que difere da avaliação sem Memoria:
NOV_NAVIGATION_INFERENCE source=memoria.ia
observation=structural-event:7acd630b47dbbac9cc8909147a99c24f5890301d
decisions=1 anticipations=172.
Este resultado demonstra influência em uma escolha de navegação da apresentação;
não demonstra generalização semântica ou sincronização com a posição oficial.

## Comportamento

O renderer nativo registra ações concluídas somente no ramo de navegação ao vivo.
Navegadores espectadores, passeio offline e exploração manual não são fontes
para a ingestão. Cada ação conserva:

- sessão e número da decisão;
- início, objetivo projetado, passagem escolhida e posição fisicamente resolvida;
- candidatos percebidos, segurança imediata, visão até 3 m e razão de bloqueio;
- opção escolhida pela avaliação sem Memoria, quando existe;
- origem da decisão e observação da Memoria que efetivamente alterou a escolha;
- identidade do mundo recebida no feed, sequência e posição oficial nos dois extremos;
- tempo monotônico, duração, distância restante, colisão, superfície e resultado.

Resultados: step_reached, goal_reached, blocked, interrupted e no_passage_sensed.
Perceber ausência de passagem não se transforma em uma tentativa física fracassada.
Uma chegada ao alvo atual não é atribuída a um objetivo antigo que já mudou.
Uma troca de mundo descarta a ação incompleta; ações concluídas conservam o mundo
original. A identidade vem do feed no momento da ação, em vez de ser inferida
do arquivo oficial durante a ingestão.

O objetivo é explicitamente projected_runtime_observer_position. Não há alegação
de que o renderer conhece a necessidade semântica ou o plano que originou esse alvo.

## Persistência e ingestão

nov_navigation_episodes.gd salva atomicamente
user://nov-navigation-episodes-008ch.json em janelas de 30 s ou até 128 ações.
Retém até 16 episódios e menos de 1,9 MB, indicando dropped_episodes.
Uma interrupção do processo pode perder a janela ainda não salva e a ação parcial.
O limite de retenção pode remover episódios antes da ingestão em uma indisponibilidade
prolongada; esta versão não promete histórico completo. Remoções são informadas
na saída da ingestão como source_retention_dropped (inclui remoções já ingeridas).

nov_navigation_episode_sync.py lê uma cópia consistente, valida identidade,
limites, ordem temporal monotônica, coordenadas e origem causal. Envia até dois
episódios por execução do serviço existente para a API estrutural local autenticada.
Os IDs dependem da sessão, sequência e conteúdo. O checkpoint só avança após
confirmação de armazenamento ou duplicata com ID correto e backend durável.
Reenviar após uma resposta perdida conserva exatamente o mesmo ID.

Episódios ficam em uma hierarquia separada live:navigation:nov:episodes.
A autoridade continua observed-renderer-physical-results, world_write_authority=false.
A publicação de recall da 008CG mantém o contrato de resumos anterior; os novos
episódios não são automaticamente convertidos em novas regras de seleção.
Não há exposição das experiências completas nem de credenciais no navegador.

## Instalação

Execute na VM:

    sudo bash /home/etbra/live.infinita/deploy/apply-navigation-episodes-008ch-root.sh

O script valida Python, exporta Godot numa cópia isolada, instala os módulos do
renderer e a ingestão, reinicia o renderer e promove a cena em /godot/.
Preserva backups e rollback para arquivos, serviço e publicação.
A confirmação 008CH_OK indica instalação concluída; a primeira ingestão precisa
de movimento ao vivo e da janela de gravação. O checkpoint fica em
/var/lib/live-infinita/memoria-local/navigation-episodes.checkpoint.json.
O journal do serviço mostra episodes.acked e episodes.confirmed após a ingestão.
Reconhecimento durável já feito não é desfeito por rollback.

## Validação

31 testes Python de navegação, incluindo resposta perdida, ACK inválido,
repetição após reinício, mutação de identidade, contexto de outro mundo,
sequência regressiva e limites de entrada.
Nove testes Godot de física, câmera, apresentação, antecipação e episódios.
O teste de episódios usa movimento real com CharacterBody3D, verifica chegada,
gravação e recarga, limitação de percepção sem passagem e retenção.
Integração isolada com a API FastAPI real da Memoria local e SQLite: episódio
com 128 ações, ACK durável, duplicata idempotente e leitura após reabrir o banco.
O JSON produzido pelo Godot também passou pelo validador Python.

## Próxima etapa

Transformar a posição física em observação autenticada para o runtime, com
projeção de coordenadas identificada e validação de sessão/ordem. O escritor
oficial deve decidir como aplicar deslocamentos e reconhecer chegadas.
Hoje a posição oficial continua independente dos desvios físicos do renderer.
Essa integração exige mudanças no contrato de execução, não apenas escrever
diretamente world.json a partir de um espectador.
