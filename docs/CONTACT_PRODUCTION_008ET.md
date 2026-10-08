# 008ET — aplicação e verificação em produção

Instalação concluída pelo usuário. Rollout 008et-20261008T141842Z,
promoção 008ca-20261008T142156Z, build público 18229b6.
Renderer iniciado às 14:21:08 UTC (11:21:08 em São Paulo), ativo com
NRestarts=0 no momento da verificação às 14:32 UTC.

A continuidade de contato está ligada e a adaptação por custo 008ER continua
ativa. Os dois arquivos nativos alterados são idênticos aos do repositório.
Nenhum erro de script/parse/loading foi encontrado no journal desde esse início.
A ponte de padrões terminou com sucesso e seu timer está ativo. Recibos recentes
confirmam gravação e recuperação no núcleo; o cache recuperado contém 512
registros. O início do rollout carregou 512 registros locais anteriores.
Essas janelas podem se sobrepor; não são 1.024 fatos distintos nem representam
o tamanho total do histórico no núcleo.

## Captura inicial

126 eventos, 63 contatos, de 14:21:08 a 14:31:01 UTC. Nenhum contato inválido,
linha inválida, conflito ou resultado órfão no observador 008EL.

- 15 explorações concluídas e nove excluídas antes de saída confirmada.
- Uma preferência recuperada mudou o lado inicial e teve saída concluída.
- Uma preferência da RAM mudou o lado e teve saída concluída.
- Outras 20 conclusões: 16 por percepção, três RAM sem mudar lado e uma
  recuperada sem mudar lado.
- 26 exclusões totais, todas new_contact_before_executed_exit.
- Nenhuma falha física registrada nessa captura; isso não comprova ausência de
  falhas em sessões futuras ou não capturadas.

Não houve observed_side_end nesta captura. A nova política mantém o contato
nessa mudança de direção, mas ainda há exclusões por novo contato iniciado
antes da confirmação de saída. A redução específica dessa razão é coerente
com a implementação; janelas de duração e geometria diferentes não sustentam
uma estimativa causal de economia ou ganho de aprendizado.

A análise descritiva encontrou duas janelas com exploração concluída e,
posteriormente, conclusão de uma preferência aprendida. Horários de conclusão
não comprovam a ordem de início das decisões nem uso causal dessas explorações.

Evidência integral em CONTACT_PRODUCTION_008ET/: rollout.log, checks.json,
status.json, events.log, outcomes.json e windows.json. A captura de eventos é
fixa; o snapshot de status foi obtido depois e pode ter contadores maiores.

Próximo foco: distinguir proposta de saída não executada de saída realmente
percorrida quando um novo contato começa; reproduzir fisicamente antes de
atribuir sucesso, erro ou custo a uma tentativa interrompida. A 008ET foi
verificada, sem aplicar outra mudança de comportamento nesta etapa.
