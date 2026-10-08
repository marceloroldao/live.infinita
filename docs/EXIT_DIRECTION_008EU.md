# 008EU — escolher uma saída que avance fisicamente

## Evidência observada

Captura limitada de 628 ações reais da sessão nativa 008ET. Treze propostas de
saída estavam visíveis: doze atingiram o progresso físico de 0,75 m durante
o mesmo contato. O contato 791 teve primeiro progresso de -0,829 m; após seis
ações executadas, seu maior progresso ainda era -0,639 m. Em seguida apareceu
outro contato. A saída tinha sido proposta, mas não executada na direção medida.

O coletor não deveria marcar esse caso como sucesso. A mudança corrige a
seleção de candidatos na proposta de saída, não transforma exclusão em recompensa.
A captura não comprova que todas as exclusões da live tenham essa causa.

## Comportamento

Com LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION=1, a proposta clear_exit_proposed
retorna somente candidatos com clear_ahead verdadeiro e deslocamento projetado
de pelo menos 0,75 m na normal original do contato. Se não houver tal candidato,
o contato continua ativo sem proposta de saída.

A percepção continua a validar o passo completo e sua antecipação local;
o corpo ainda executa movimento varrido e o coletor exige o resultado físico.
Uma colisão pode continuar registrando falha física. Validação rejeitada antes
da execução não vira falha. A seleção de saída não grava fatos por si mesma.

Serial, contexto, lado inicial, normal, escala de custo, registros anteriores e
contratos do núcleo são preservados. A continuidade 008ET e a adaptação por
custo 008ER permanecem independentes da flag nova.

## Testes físicos

Oito pares com a mesma geometria/início/destino, comparando 008ET com o controle
de saída desligado e ligado. Ambos os braços usam continuidade 008ET e adaptação
008ER. A cápsula, sondagens e callbacks são reais; zero colisões e zero buscas
globais nos 16 percursos. Todos chegaram ao destino.

| Cenário | 008ET, controle desligado | 008EU, controle ligado |
| --- | ---: | ---: |
| Parede simples | 70,000 m | 70,386 m |
| Canto | 124,216 m | 124,708 m |
| U | 191,906 m | 190,800 m |
| Canto profundo | 124,216 m | 124,708 m |
| U profundo | 258,227 m | 258,393 m |
| U espelhado | 191,906 m | 190,800 m |
| Exploração em canto | 124,216 m | 124,708 m |
| Exploração em U | 191,906 m | 190,800 m |

Nas duas explorações, a experiência anterior é o mesmo fato da parede simples,
produzido fisicamente. Nenhum fato sintético ou resultado desse teste foi enviado
ao núcleo da live. O controle ligado atingiu a direção/progresso de saída já
na primeira ação concluída com proposta em todos os oito casos, com tolerância
numérica de 0,0001 m apenas para a verificação do teste. O coletor de produção
mantém seu limiar físico original, sem afrouxamento.

O custo ficou um pouco maior em alguns percursos e menor em outros.
Não foi demonstrada vantagem causal de memória aprendida ou melhoria líquida
de custo na live. A correção evita um candidato de recuo ser liberado como saída.

## Regressões e reprodução

49 testes Godot passaram com a flag desligada e os mesmos 49 com ela ligada.
A rodada final ligada está registrada em regressions-enabled-final.
Uma verificação adicional cobre a equivalência do controle desligado com lista
vazia de candidatos, após restaurar explicitamente esse caso legado.
A primeira rodada ligada falhou em duas asserções sintéticas antigas: os
candidatos de saída ainda eram pontos da origem mesmo após mover a posição
para (4,1). Os percursos físicos dessas verificações chegaram sem colisões.
As duas entradas agora oferecem um candidato local à posição movida (5,1);
as exigências de chegada, travessia válida e ausência de colisão foram mantidas.
A rodada inicial com falhas foi preservada em initial-regressions-enabled.

O novo teste cobre recuo, lateral, antecipação bloqueada, falta de candidato,
limiar de 0,75 m e reprodução dos candidatos registrados no contato 791.
A reprodução usa percepção arquivada e verifica a seleção; não é uma nova
execução física daquela geometria da live.

Evidência em EXIT_DIRECTION_008EU/: native-episodes.json.gz,
native-counterexample.json, native-summary.json, physical.json.gz,
physical.log, summary.json, exit-projection-checks.json e regressões.

Para repetir sem root:
`bash /home/etbra/measure-exit-direction-008eu.sh`.
Cria projeto/dados temporários e resultados em /home/etbra/008eu-exit-direction-proof.
Os nomes de braço baseline/continuity do executor reaproveitado correspondem
nesta comparação a controle de saída desligado/ligado. As flags de cada quadro
e comparison=exit-direction registram o tratamento efetivamente usado.

## Aplicação preparada

`sudo bash /home/etbra/apply-exit-direction-008eu-root.sh`

O instalador guarda código/site/configuração, valida a exportação, liga somente
a flag nova na configuração do renderer e verifica estado nativo recente.
As flags 008ER/008ET existentes são preservadas. Há restauração em caso de falha;
memória, animais e histórico não são apagados.

Para desligar após aplicação:
`sudo bash /home/etbra/set-exit-direction-008eu-root.sh off`.
Preserva fatos acumulados e retoma a seleção anterior.

A 008EU ainda não foi aplicada durante esta investigação. Depois da aplicação,
verificar a configuração e capturas limitadas de conclusões, exclusões e falhas,
sem assumir que todo new_contact_before_executed_exit tenha sido resolvido.
