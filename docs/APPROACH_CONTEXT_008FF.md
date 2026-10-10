# 008FF — Contexto físico e reavaliação após falha

Experimento isolado que amplia 008FE. Acrescenta contexto observado à experiência e escolhe novas tentativas após uma preferência bem-sucedida falhar. Código da live e do núcleo de produção permanecem na versão anterior.

## Contexto medido
Para cada animal avistado, o corpo Godot executa uma consulta test_move com a cápsula real por quatro metros na direção observada. A consulta não desloca o corpo. Registra perfil da cápsula/varredura, alcance de 4 m, bloqueio à frente e tempo lógico da amostra. O resultado da tentativa preserva os dados reais do controlador 008FC e o número de contatos físicos.

Um evento estrutural independente carrega o resultado e seu contexto; não altera a trilha 008FD em produção. Proveniência, conteúdo e identidade do envelope recuperado são verificados integralmente. Intenções, previsões e resultados censurados não entram nessa experiência.

O seletor agrupa por faixa de distância inicial de 6 m, perfil e bloqueio observado. Não usa identidade do animal, coordenada de obstáculo ou rota armazenada para decidir. Contratos incluem reutilização do padrão com outros identificadores de animais.

## Reavaliação derivada da experiência
Uma falha posterior a um sucesso no mesmo contexto marca a necessidade de reavaliação. A política deixa de usar a média anterior enquanto faltam duas amostras por alternativa após essa mudança. Seleciona o contexto menos amostrado e, em empate, o amostrado há mais tempo. Após a renovação, aplica a pontuação experimental de distância/3 mais penalidade 20 por não concluir aproximação, com margem superior a 20% para trocar a opção mais próxima.

A marca da mudança e a escolha das novas tentativas são derivadas dos fatos recuperados. Cada resultado de aquisição foi gravado, o serviço SQLite reaberto e a experiência recuperada pela API antes da próxima decisão. Não há estado de RAM necessário para conservar a necessidade de reavaliação.

## Comparações físicas
Dois animais estáticos a 16 m e cerca de 22,36 m, cerca baixa com colisão e sensor visual real. Ambos são vistos, mesmo quando o trajeto não permite aproximar. O controle usa o seletor original que escolhe o mais próximo. Uma terceira condição usa apenas a percepção física, escolhendo opção livre na varredura.

| Caso | Resultado |
|---|---|
| Cerca dentro dos 4 m observados | A experiência contextual e a percepção física livre chegam à opção distante. Controle pela distância falha. Não há ganho adicional demonstrado da memória sobre percepção física. |
| Cerca observada muda para a opção distante | Contexto novo não aceita a preferência anterior. Nov escolhe a opção próxima e conclui. Percepção física sozinha também conclui. |
| Cerca além dos 4 m observados | As duas opções parecem livres. Experiência recuperada escolhe a opção distante alcançável; controle mais próximo falha. |
| Cerca não observada muda de opção | A preferência anterior tem uma primeira falha. O resultado recuperado dispara novas tentativas: próxima, distante, próxima. Após estas três tentativas, a escolha final volta à opção próxima alcançável. |

O segundo teste ainda produz duas falhas após a mudança: a primeira tentativa com preferência antiga e uma sondagem da alternativa distante. Não prevê um obstáculo que ainda não foi observado. O resultado é recuperação da escolha após experiência nova; a comparação final coincide com a percepção pela distância e não demonstra ganho adicional naquela decisão.

22 tentativas físicas, 12 resultados de aquisição persistidos, 12 reaberturas com recuperação fria do SQLite real do SDK dfd87c995b50c49b45a9d5dd4c43cce456983d4f, backend sqlite e allow_fallback=false. Os resultados recuperados foram comparados integralmente com as medidas físicas; leitura após reabertura não substitui recuperação por reingestão.

A comparação com a política 008FE descarta o contexto em um adaptador de teste para o seu formato antigo. As medidas vêm da recuperação contextual verificada, mas os identificadores do formato antigo são recalculados apenas para compatibilidade; não foram ingeridos ou recuperados como novos fatos do núcleo.

## Limites e próxima integração
Movimento direto incremental com CharacterBody3D, não a navegação completa de contorno da live. Animais não fogem. Reset de posição ocorre apenas entre episódios do experimento e não conta como movimento medido. A reavaliação é entre tentativas, não uma liberação imediata de um personagem preso no mesmo episódio.

A aquisição inicial alternada foi agendada pelo teste. As três novas tentativas após falha são escolhidas autonomamente pela política a partir do núcleo reaberto. Contexto binário é grosseiro; resultados são de dois cenários determinísticos e parâmetros fixos, sem comprovação estatística geral ou de benefício em produção.

38 contratos Python passaram, incluindo regressões 008FE/008FD; 22 tentativas físicas sem erros de script. Código e evidências são versionados juntos. Nenhuma instalação solicitada nesta etapa.

Próxima etapa: acrescentar coleta de contexto ao renderer de produção com versão compatível de fatos, validar na locomoção completa e instalar a reavaliação reversível após estes checks. Manter diferenças entre avistamento, consulta física, experiência recuperada e sondagem explícitas nos diagnósticos.
