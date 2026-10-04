# 008CT — inferência de percurso observado perto da ponte

## Problema observado

O relato da live descreve idas e voltas na margem. Registros nativos
mostraram Nov em x=19,7 seguindo a margem, com destino na outra margem
(x=318,3). A escolha local de um passo, com horizonte de três metros,
consegue evitar água mas não estabelece uma sequência de travessia.
A sequência observada já estava longe da ponte; não demonstra que
havia um corredor próximo disponível naquele momento.

## Mudança

Quando a frente está bloqueada, uma busca local observa conexões físicas
numa janela de 64 x 64 m centrada em Nov. A malha usa células de dois
metros e no máximo 1089 nós. Cada conexão é verificada em subpassos
com a mesma altura, classificação de superfície e cápsula de colisão
usadas na caminhada.

A busca não contém coordenadas da ponte ou do rio. Constrói uma sequência
até o ponto alcançável da janela mais próximo do destino; se o destino
fica fora da janela, o resultado é um percurso parcial. A seleção entre
caminhos da mesma extensão começa pelos desvios laterais para antecipar
obstáculos, em vez de avançar até encostar neles.

O cálculo continua em pequenos trechos entre quadros, com orçamento
alvo de 6 ms verificado entre nós e limite de 12 nós por trecho. Esse
orçamento não é um limite rígido para o custo de uma consulta física.
Durante a busca Nov aguarda; isso é registrado como percepção em andamento,
sem inventar colisão, chegada ou reutilização de RAM. Cada passo do
percurso pronto volta a ser verificado fisicamente. Bloqueios invalidam
o percurso. Troca de identidade do destino cancela o cálculo anterior.

Quando não encontra percurso, há limite de nova busca: deslocamento
de pelo menos 12 m ou intervalo de cinco segundos. A navegação local
anterior continua disponível. A regra do destino próximo comprovadamente
livre, da 008CS, continua prioritária.

## Verificação

- Ponte do projeto, rampas de altura e corrimãos físicos: início
  (18,-8), destino (62,-8). Chegou ao outro lado; distância 109,53 m;
  zero colisões e zero posições classificadas como água.
- Duas buscas parciais. Na execução final, maior trecho medido de 7 ms;
  custos acumulados de busca 351 e 456 ms, distribuídos entre chamadas.
- Abertura deslocada em um obstáculo genérico: percurso encontrado
  usando exclusivamente o resultado das consultas, sem posição fixa.
- Planejamento não gera tentativas ou visitas fictícias enquanto parado.
- 15 testes Godot de publicação e 72 testes Python passaram.

Os testes anteriores de antecipação foram adaptados para a etapa de
observação distribuída: o corpo deve permanecer seguro durante o cálculo
e começar o desvio ao concluir a busca. Não exigir movimento imediato
quando a percepção ainda está estabelecendo o percurso.

## Limites

É inferência espacial de apresentação baseada na física observada.
Não é prova de novo aprendizado causal da Memoria.ia, nem escreve
World State. Os passos realmente executados continuam registrados e
alimentam a RAM; uma decisão já estabelecida pela percepção não ganha
crédito causal de memória.

Não há mapa global persistente. Uma ponte fora da janela não é conhecida
por essa busca, e não há garantia de saída para qualquer rio, destino
inacessível ou obstáculo maior que a janela. Ainda precisamos verificar
o comportamento na live após aplicar. O teste da ponte usa piso base
plano e o perfil de altura da ponte; não cobre todo relevo cognitivo.

## Aplicação

```bash
cd /home/etbra/live.infinita && git pull --ff-only && sudo bash deploy/apply-observed-crossing-008ct-root.sh
```

Atualiza renderer nativo e Web com backup/rollback. Sucesso: 008CT_OK.
Log: /home/etbra/008ct-renderer-rollout.log.
Depois de aplicar, recarregar a fonte da live e verificar o primeiro
NOV_OBSERVED_ROUTE e a chegada ao outro lado nos episódios nativos.
