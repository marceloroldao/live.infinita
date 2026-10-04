# 008CQ — RAM, promoção real e recuperação persistente

Teste isolado na VM, com o navegador de produção e o mesmo obstáculo
físico em U. Nenhum dado do experimento entrou na memória da live.

## Protocolo

1. Dois controles sem memória, com navegador novo, início (-100,0),
   destino (-94,0), terreno plano e três paredes fixas.
2. Seis percursos com RAM mantida entre tentativas. Apenas os resultados
   físicos registrados pelo gravador de episódios alimentam a RAM.
3. Validar cada promoção e suas três decisões distintas: mesma sessão,
   passo concluído, destino selecionado realmente alcançado, nenhuma
   colisão e escolha diferente da alternativa sem RAM.
4. Executar o sincronizador de promoção de produção contra a API real
   do core em FastAPI TestClient e SQLite temporário.
5. Reabrir o banco, exportar o recall pela API e executar dois percursos
   com navegadores novos e RAM vazia, usando só os registros recuperados.
6. Reproduzir os dois controles novamente, verificando igualdade exata.

Não foram injetados passos ideais nem gravado o percurso completo como
atalho. A memória persistente recebeu apenas as seis promoções naturais.

## Resultado

| Condição | Distância | Tempo simulado | Decisões | Colisões |
|---|---:|---:|---:|---:|
| Sem memória | 57.62 m | 17.3 s | 58 | 0 |
| RAM, percurso 1 | 65.79 m | 19.7 s | 66 | 0 |
| RAM, percurso 2 | 60.51 m | 18.1 s | 60 | 0 |
| RAM, percurso 3 | 61.18 m | 18.3 s | 61 | 0 |
| RAM, percurso 4 | 56.37 m | 16.9 s | 56 | 0 |
| RAM, percurso 5 | 53.06 m | 15.9 s | 53 | 0 |
| RAM, percurso 6 | 53.06 m | 15.9 s | 53 | 0 |
| Memoria.ia após reiniciar navegador | 42.13 m | 12.5 s | 41 | 0 |

Todas as tentativas chegaram ao destino. Os dois controles coincidiram
e os dois percursos após recuperação persistente também coincidiram.

Seis promoções tiveram três reutilizações causais concluídas verificadas,
seis confirmações da API e seis registros recuperados depois de reabrir
SQLite. O sincronizador repetido não gerou novas confirmações.

Após reiniciar o navegador, cinco escolhas por percurso foram alteradas
causalmente pela Memoria.ia. Os IDs selecionados pertencem aos registros
efetivamente confirmados e recuperados. Distância reduzida em aproximadamente
26,9%, tempo simulado em 27,7% e decisões de 58 para 41.

O contador de reutilizações para promoção satura após três confirmações
por experiência. Por isso o sexto percurso registra zero novas confirmações
para promoção, embora tenha cinco escolhas causais de RAM verificadas.
Não confundir esse contador com ausência de uso da RAM.

## Interpretação

O ciclo RAM → três reutilizações → Memoria.ia → recuperação após reinício
funcionou com experiências geradas pelo próprio movimento físico.

A RAM piorou os primeiros percursos: completar um passo com sucesso
não assegura que ele encurta o percurso inteiro. Ela reforça passos locais;
não calcula o caminho ótimo. A melhoria final não autoriza descartar os
resultados iniciais nem prometer melhora monotônica.

É um único obstáculo sintético determinístico. Tempo simulado é número
de ticks multiplicado por 0,1 s, com velocidade configurada em 4 m/s,
e não desempenho da VM ou tempo de parede. A API foi testada com o core
real em banco temporário, sem depender da rede externa. O resultado não
é uma comparação controlada na live nem prova de generalização para
rios, elevações e outros terrenos.

Próxima prioridade: avaliar se passos reutilizados reduzem progresso
total ou geram voltas antes de reforçar sua preferência. Primeiro testar
em obstáculos adicionais e em rotas que mudam de condição.

## Reproduzir

Projeto Godot isolado precisa estar importado e conter os mesmos scripts
da navegação. O runner rejeita o projeto fonte e o projeto de produção
em /opt/live.infinita, e confere os hashes dos módulos do navegador.

```bash
cd /home/etbra/live.infinita
/opt/live.infinita/.venv/bin/python tools/benchmark_navigation_promotion_008cq.py --godot-project /home/etbra/008bz-godot-test --report /home/etbra/navigation-promotion-result.json
```

70 testes Python passaram. O experimento Godot/API executou duas vezes
por rodada de validação; os controles e resultados após reinício foram
reproduzidos. O JSON NAVIGATION_PROMOTION_RESULT_008CQ.json guarda
métricas, hashes, seis promoções e as 18 ações que sustentaram o critério.

Não exige instalar atualização ou reiniciar serviços da live.
