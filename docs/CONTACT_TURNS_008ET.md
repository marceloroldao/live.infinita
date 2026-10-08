# 008ET — manter o contato físico ao mudar de direção

## Problema e correção

Na captura 008ES, 148 explorações foram excluídas por observed_side_end.
O contorno antigo encerra seu quadro ao selecionar uma mudança de direção;
o próximo quadro recebe outro serial. O coletor corretamente exclui o contato
anterior, que ainda não teve saída física confirmada. A investigação não
comprova que todos os 148 casos da live tenham a mesma geometria.

A política optativa 008ET conserva serial, contexto, lado inicial, origem e
normal de saída durante a mudança local de direção. Mantém uma direção
transitória de escape baseada exclusivamente em candidatos fisicamente
verificados. Quando necessário, permite continuar um recuo que antes era
eliminado pela normal original do objetivo.

Mudar de direção não registra sucesso ou erro. A conclusão ainda exige
movimento executado, sem colisão, com progresso real de saída de pelo menos
0,75 m, ou chegada física válida ao objetivo. As falhas físicas e exclusões
por mudança de mundo/objetivo continuam sob o contrato anterior.
Não há coordenadas de passagem, teleporte ou busca global de rota.

## Comparação com a política anterior

Dezesseis percursos reais, oito pares de geometria/início/destino iguais,
cápsula 0,44 m × 1,8 m, sondagem local e callbacks do coletor nativo.
Velocidade 4 m/s, dt 0,1 s, limite de 2.500 chamadas por percurso.
A adaptação 008ER por custo estava ligada; a nova propriedade do contorno foi
explicitamente ligada/desligada por braço no teste.

| Cenário | Política anterior | Continuidade 008ET |
| --- | --- | --- |
| Parede simples | Chegou: 70,000 m | Chegou: 70,000 m |
| Canto | Não chegou no limite | Chegou: 124,216 m |
| Passagem em U | Não chegou no limite | Chegou: 191,906 m |
| Canto mais profundo | Não chegou no limite | Chegou: 124,216 m |
| U mais profundo | Não chegou no limite | Chegou: 258,227 m |
| U espelhado | Não chegou no limite | Chegou: 191,906 m |
| Exploração em canto | Não chegou no limite | Chegou: 124,216 m |
| Exploração em U | Não chegou no limite | Chegou: 191,906 m |

Os sete braços antigos incompletos percorreram cerca de 833,400 m até o
limite. Isso é custo de uma tentativa interrompida, não comprimento de uma
rota concluída; não foi calculada porcentagem de economia de aprendizado.
Todos os braços tiveram zero colisões e zero buscas globais.
A nova política chegou nos oito casos, sem acionamento do watchdog.

Nos dois casos de exploração, ambos os braços receberam exatamente a mesma
experiência anterior: o único fato físico produzido pela parede simples.
Esse fato real provocou a exploração do outro lado. Não foram fabricadas
recompensas ou carregados fatos sintéticos. A política antiga excluiu contatos;
a nova registrou uma exploração concluída em cada caso. O observador 008EL
revalidou o log integral sem contatos inválidos, conflitos ou resultados órfãos.

Esses resultados demonstram uma correção de navegação e de continuidade da
tentativa. Não demonstram vantagem causal de uma preferência aprendida pela
Memoria.ia. Os fatos do teste não foram enviados ao núcleo da live.

## Validação e evidências

48 testes Godot passaram com a flag ligada e os mesmos 48 com ela desligada.
O teste antigo de descarte por reset foi mantido e agora seleciona explicitamente
a política antiga. O teste novo verifica retenção do contato, recuo, ausência de
crédito artificial e limpeza do estado ao mudar o contexto.

Uma primeira hipótese, que mantinha apenas a tangente à normal original,
concluiu o canto mas não saiu do U; foi rejeitada. Seus resultados estão
arquivados como rejected-tangent-only, sem alegação de sucesso.

CONTACT_TURNS_008ET/ contém summary.json, physical.json.gz (ações reais
integrais), physical.log, outcome-observer.json, resultados das regressões e
o protótipo rejeitado. O JSON comprimido pode ser aberto com gzip da biblioteca
padrão Python.

Para repetir sem root:
`bash /home/etbra/measure-contact-turns-008et.sh`.
O executável cria projeto e dados de usuário temporários, exige saída sem erros
Godot e arquiva resultados em /home/etbra/008et-contact-turn-proof.

## Instalação preparada, ainda não aplicada

`sudo bash /home/etbra/apply-contact-turns-008et-root.sh`

O instalador exporta e verifica o projeto, guarda código/site/configuração,
liga LIVE_INFINITA_NAVIGATION_CONTACT_TURNS=1, reinicia o renderer e exige
confirmação recente da nova configuração nativa. Em caso de falha, restaura
código/site/configuração. Os bancos, encontros, animais e histórico de memória
são preservados. A flag 008ER por custo permanece na configuração anterior.
O manifesto web anuncia capacidade; o estado nativo confirma ativação efetiva.

Para desligar a política nova após instalação:
`sudo bash /home/etbra/set-contact-turns-008et-root.sh off`.
Isso conserva os fatos acumulados e retoma o reset antigo; não apaga experiência.

Próxima verificação em produção: confirmar build/configuração e comparar
explorações concluídas, excluídas e falhas físicas em capturas limitadas.
Não assumir que a correção eliminou todos os encerramentos da live.
