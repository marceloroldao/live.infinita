# 008EC — Diagnóstico das condições de reuso de navegação

Na coleta inicial da live após 008EA, oito tentativas encerraram: cinco chegadas, dois resgates e uma troca de intenção de busca. Nenhum passo concluído nessas tentativas registrou mudança causal de escolha pela RAM ou pela Memoria.ia de navegação. A troca de intenção não equivale a uma falha física. A fotografia posterior, com seus horários e contadores, está em NAVIGATION_MEMORY_REUSE_OBSERVATION_008EC.json.

Na fotografia posterior houve 11 tentativas encerradas (sete chegadas e quatro interrupções) e seis passos concluídos com escolha alterada pela RAM; não houve passo causal atribuído à Memoria.ia de navegação. Os seis passos ocorreram na tentativa de identidade final :10, encerrada por stuck_recovery depois de 79,152 s e 215,801 m, ainda a 372,291 m do objetivo. Isso confirma uso efetivo da RAM em alguns contextos da sessão, sem provar que melhorou o resultado. A observação inicial de zero reuso era válida somente para sua janela menor.

O código atual endereça recomendações por destino absoluto arredondado e posição absoluta arredondada. A RAM tem limite de 512 registros de sucesso e validade de dez minutos. Assim, encontrar uma recomendação exige correspondência exata da chave; a capacidade também pode impedir revisitar o início de um percurso longo.

Teste isolado de componentes, usando registros sintéticos de conclusão:

| Sequência repetida | Destino | Acertos de consulta na segunda passagem |
|---|---|---:|
| 128 passos | Mesmo destino | 128 de 128 |
| 128 passos | Destino mudou um metro | 0 de 128 |
| 800 passos | Mesmo destino | 0 de 800 |

No caso longo, cada novo sucesso insere um registro e expulsa o mais antigo. Ao repetir desde o início, as inserções da segunda passagem expulsam os registros restantes antes de consultá-los: comportamento de substituição contínua do cache. Consultas não contam como reuso causal nem geram promoção.

Também foi executado o seletor atual com tentativa e erro habilitada: uma recomendação retida no mesmo contexto alterou a escolha; outro destino não recebeu essa recomendação; concordância com percepção foi identificada separadamente. Uma escolha alterada pode ser melhor ou pior: o teste não mede vantagem de percurso.

Escopo e limites: não há deslocamento físico neste novo teste. Os registros sintéticos são fixtures locais, não entram em produção, no núcleo Memoria.ia ou em aprendizado persistente. O resultado confirma restrições do componente, não prova que elas causaram todos os zeros de reuso na live. A fotografia de produção é uma observação separada. As 176 promoções históricas observadas não representam 176 promoções novas nesta sessão.

Execução: Godot headless com projeto isolado e `tests/godot_memory_reuse_workload_008ec_smoke.gd -- --offline-tour`. O resultado dirigido foi zero falhas e está salvo nos arquivos DIRECTED e RESULT. Nenhum script de produção foi modificado; não é necessário instalador.

Próximo experimento: manter origem, destino e obstáculos controlados em percursos físicos repetidos, comparar percepção, RAM e recuperação real da Memoria.ia, incluindo falhas e duração. Testar generalização por trechos/contexto local exige novas regras de correspondência e revalidação física; aumentar o limite isoladamente não resolve a mudança de destino. Não alterar pesos para fabricar vantagem.
