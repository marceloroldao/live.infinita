# 008FO — busca limitada pelo último ponto observado

Foi implementado `nov_animal_contact_search.gd`, consumidor experimental de observações do sensor de visão. Após um resultado real `contact_lost`, ele pode produzir uma intenção de busca derivada do último ponto efetivamente observado. Não acessa os animais ou seu registro físico, nem recebe velocidades ou posições futuras.

A intenção é explicitamente uma hipótese (`contains_prediction=true`), não uma observação. O destino passa pela validação normal de terreno e o movimento usa o controlador nativo com colisões e desvio. A busca tem limites de cinco segundos e 12 m percorridos. Um ponto inicial distante demais, evidência antiga ou futura, terreno rejeitado, relógio regressivo e mudança de mundo são rejeitados ou encerram a busca.

A busca só termina como `reacquired` ao receber uma nova observação do mesmo animal, no mesmo mundo, com até 300 ms de idade lógica e 500 ms de idade de recepção. Alcançar o destino hipotético sem uma observação não confirma reencontro. Reencontro também não confirma aproximação ou captura.

## Comparação física

O teste conserva as mudanças de direção e a obstrução física de 008FN. Ambos os braços começam procurando o mesmo animal observado, para isolar o efeito da nova busca. Não é uma comparação de seleção baseada na memória.

| Obstrução | Com busca | Controle que encerra ao perder contato | Tempo adicional de busca | Caminhada adicional |
|---|---:|---:|---:|---:|
| 2 s | 2/2 reencontros | 0/2 reencontros | 0,5 s por ensaio | 1,8 m por ensaio |
| 3 s | 2/2 reencontros | 0/2 reencontros | 1,7 s por ensaio | 5,8 m por ensaio |

Em todos os oito trajetos, a tentativa inicial termina como `contact_lost`. Nos quatro trajetos com busca, ela prossegue separadamente e reencontra o alvo por observação física recente. O histórico original não é reescrito para transformar o fracasso em sucesso.

O coletor de contexto mantém o resultado medido da aproximação inicial. Quatro desses fatos de perda de contato foram confirmados e recuperados em quatro reaberturas do núcleo SQLite, removendo o cache e sem POST na recuperação. Os resultados da busca são diagnósticos de execução (`learning_eligible=false`), separados dos fatos do núcleo. Nenhum reencontro foi inserido como aproximação bem-sucedida.

## Verificações

- Oito trajetos físicos pareados e quatro reencontros confirmados.
- Distância adicional conferida contra o deslocamento real, separada da distância do histórico inicial.
- Observação do reencontro mais recente que a usada para iniciar a hipótese.
- 18 contratos Godot sintéticos: evidência fresca, mundo, tempo, terreno, orçamento, duplicação e limite de lançamentos.
- O ponto hipotético sozinho não confirma reencontro; observação de fonte inválida ou de outro mundo não confirma reencontro.
- 46 testes Python de regressão aprovados.
- Logs, observações, históricos selados e relatórios preservados em `evidence/`.

## Limites de execução

O componente ainda não tem chamada na live. Pode executar uma busca por identificador de aproximação, com no máximo 32 lançamentos por processo, sem remover identificadores para permitir repetição. O estado da busca e essa proteção são em RAM; persistência após reinício ainda não foi implementada. Esse limite local não substitui o guard durável de 008FK, que deverá ser conectado antes de habilitar esse consumidor na produção.

As cenas são planas e diurnas, com movimentos e obstruções prescritos, sem ecologia, caça ou câmera renderizada completa. A estratégia de ir até o último ponto observado é uma regra implementada no consumidor; não demonstra estratégia de busca aprendida pela Memoria.ia ou previsão da trajetória futura.

O núcleo armazena e recupera os fatos estruturais. A live permanece em coleta (`decision_use=false`); nenhum serviço foi modificado ou reiniciado. A próxima etapa é persistir a intenção e o resultado da busca, incluindo interrupções, para conectar a recuperação ao ciclo público com o guard durável.

Reprodução sem sudo:

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/run_contact_search_008fo.py --output-dir /home/etbra/008fo-repeat
```
