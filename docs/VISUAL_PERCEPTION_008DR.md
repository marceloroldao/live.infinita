# Percepção física de Nov — 008DR

Primeira etapa para animais e caça: um sensor independente da câmera da transmissão. Não adiciona animais à live nem altera os destinos de caminhada. A interface está pronta para os agentes animais se registrarem na etapa seguinte.

## Funcionamento

`nov_visual_perception.gd` recebe alvos cadastrados explicitamente e mantém suas referências/posições internamente. O consumidor recebe somente avistamentos que passaram por distância, campo de visão e uma consulta real ao espaço físico.

Os olhos ficam 1,55 m acima dos pés de Nov. O cone horizontal é de 120°, vertical de 80°. Alcance diurno de 24 m e noturno de 12 m, interpolado pela iluminação do relógio persistido. Esses limites são regras do sensor, não valores aprendidos pela memória.

A consulta parte dos olhos, não da câmera atrás de Nov. Usa colliders sólidos da camada física 1, incluindo terreno, árvores e obstáculos já empregados na navegação. Um obstáculo impede o avistamento; um impacto no próprio collider do alvo confirma visibilidade. Um ponto de referência do alvo é testado por scan: oclusão parcial de outras partes do corpo não é resolvida nesta versão.

Trata-se de percepção geométrica da simulação, não reconhecimento por pixels ou identificação aprendida de espécies. IDs de instância e o campo `kind` vêm do registro de agentes; não significam que Nov aprendeu a reconhecer indivíduos ou espécies visualmente.

## Limites e evidência

- Até 128 alvos registrados, com referências fracas e remoção de objetos destruídos.
- Até 16 raios por scan, quatro scans por segundo. Rotação entre candidatos evita deixar alguns permanentemente sem consulta quando o orçamento é excedido.
- Distância e campo de visão eliminam candidatos antes da consulta física. Esse filtro interno não entrega posições ou IDs de alvos ocultos ao consumidor.
- Registro de saída inclui mundo, observador, tempo lógico, instante monotônico local, origem dos olhos, direção, alcance e somente entidades avistadas.
- Uma lista vazia não afirma que não há animais no mundo ou em toda a região. `absence_claim=false`; buscas completas e seu esforço ainda precisam ser definidos na etapa de busca.
- Recuperação de posição, relógio não sincronizado, feed desatualizado e divergência entre mundo/relógio limpam a observação corrente. Recuo de tempo lógico não reutiliza avistamentos antigos.

O preview nativo e o Web usam o mesmo sensor em `_physics_process`. A direção é a do corpo de Nov. A câmera continua com seu próprio enquadramento e estabilização. Os dados ficam disponíveis via `latest()` e sinal `observation_ready`; não são gravados automaticamente na Memoria.ia nesta etapa. A percepção não consulta o previsor climático global nem copia suas memórias para inferir a presença de animais.

## Validação

32 testes Godot headless aprovados, incluindo o novo teste com consultas físicas reais. O novo teste cobre alcance, alvos atrás/ao lado/acima, mundo diferente, altura dos olhos, paredes, tronco cilíndrico, retirada do obstáculo, redução noturna, alvo invisível/destruído, retorno no próprio collider, rejeição de recuo temporal, isolamento da saída, orçamento de raios, rodízio e limite de registros. Também exercita o hook do preview, cadência de quatro hertz, recuperação e feed/mundo inválidos.

As regressões incluem caminhada, câmera, colisões, terreno, ponte/água, recuperação, jornadas, dia/noite, céu e vento/nuvens. Não há novo comportamento animal ou alegação de aprendizagem visual.

## Instalação

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-visual-perception-008dr-root.sh
```

Sucesso: `008DR_OK`. Log: `/home/etbra/008dr-perception-rollout.log`. O instalador publica o export Web e atualiza somente o sensor e o preview do renderer nativo, com backup/rollback. Os serviços e dados do experimento climático continuam separados e não são reinstalados. Recarregar a live após instalar.

Próxima etapa: uma espécie com poucos animais, movimento próprio e necessidades físicas de água/alimento. Depois, encontros e buscas delimitadas produzirão experiências observadas para o teste de previsão de localização.
