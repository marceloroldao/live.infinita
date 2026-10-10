# 008FN — mudanças de direção e perda/retomada da visão

O ambiente físico agora faz o animal distante mudar de direção aos 2 s e novamente aos 4 s. Um obstáculo físico bloqueia temporariamente a linha de visão. Esses eventos não são informados ao controlador: Nov recebe somente observações do sensor real, com a orientação estabilizada do corpo e a cadência de varredura de 008FL.

A velocidade dos animais é 1 m/s e a de Nov é 4 m/s. Os animais usam corpos com colisão e movimentos prescritos; ainda não possuem ecologia ou uma política autônoma de fuga. O obstáculo é um estímulo controlado do teste, não uma alteração cognitiva do terreno público.

## Experimento

Dois núcleos independentes recebem quatro experiências iniciais sem a obstrução temporária, já com mudanças de direção. Depois, cada caso realiza quatro pares de aproximações com novos identificadores de animais. A escolha baseada em fatos recuperados é comparada à escolha do animal visível mais próximo. Os dois braços começam nas mesmas condições. Apenas os resultados do braço com memória entram no núcleo.

| Obstrução programada | Com fatos recuperados | Por proximidade | O que o sensor confirmou |
|---|---:|---:|---|
| 0,6 s | 4/4 aproximações | 0/4 aproximações | Alvo fora da visão aos 3,0 s; novamente observado aos 3,6 s |
| 2,0 s | 0/4 aproximações | 0/4 aproximações | Primeira tentativa termina por perda de contato aos 4,3 s, antes da liberação do obstáculo |

No caso curto, os quatro resultados com memória foram confirmados com observação física recente, no máximo 300 ms antes do término. Os registros mostram duas mudanças de direção e revisões do alvo observado. Não foi usada a posição futura para produzir a aproximação.

No caso longo, o primeiro fracasso dispara reavaliação baseada em falha. As três escolhas seguintes passam pelo guard, com reservas encerradas por resultados reais, mas continuam sem alcançar o animal. A memória não resolve essa obstrução neste experimento. O resultado é `contact_lost`; ele não afirma que o animal deixou de existir nem registra captura ou sucesso fictício.

A escolha com fatos recuperados e a retomada do contato têm mecanismos distintos. O consumidor experimental usa o custo histórico para escolher o contexto. O controlador existente acompanha novas posições observadas e tolera uma breve perda de visão. Esta etapa valida essa combinação; não implementa previsão aprendida do movimento.

## Evidência

- 24 trajetos físicos: oito aquisições e oito pares de comparação.
- 16 fatos confirmados e recuperados em 16 reaberturas do núcleo SQLite real, com remoção do cache e sem POST na recuperação.
- Coletor nativo, distâncias medidas e contatos verificados contra os movimentos reais.
- Quatro retomadas de visão auditadas, com sucesso confirmado por observação recente.
- Contraprova longa sem retomada antes do encerramento da primeira tentativa.
- 46 testes Python de regressão aprovados.
- Logs, observações completas, checkpoints selados e relatórios em `evidence/`.
- `TURNING_VISIBILITY_008FN.json`: resultados físicos e recuperação.
- `SENSOR_AUDIT_008FN.json`: transições reais do sensor, sem inferir ausência do animal.

O núcleo mantém e recupera os fatos estruturais; o seletor experimental implementa a decisão. Os testes são planos, diurnos e prescritos. Não cobrem animais com decisão autônoma, terreno carregado dinamicamente, câmera renderizada completa, rede ou caça.

A live permanece em coleta (`decision_use=false`). Nenhum serviço foi alterado ou reiniciado. A próxima evolução deve tratar a busca após a perda prolongada de contato usando o último ponto realmente observado, mantendo hipóteses separadas de novas observações físicas.

Reprodução sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_turning_visibility_008fn.py --output-dir /home/etbra/008fn-repeat
```
