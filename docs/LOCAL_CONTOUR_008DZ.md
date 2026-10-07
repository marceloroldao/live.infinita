# 008DZ — contorno local com direção consistente

## Problema e reprodução
O seletor local por tentativa e erro pode alternar os lados de uma barreira longa, porque avalia aproximação ao destino e visitas a cada passo. Na reprodução com a cápsula e duas paredes, a versão anterior não chegou ao objetivo em 2500 passos de 0,1 s, nos dois estados da abertura; não houve colisão. Isso reproduz um circuito do controlador, não identifica automaticamente a geometria exata de todos os bloqueios da live.

## Política temporária
nov_navigation_contour.gd recebe somente candidatos já aceitos pelo sensor físico local existente. Não recebe o mapa, a posição da ponte, animais ou um grafo de rotas. A função fica ativa somente no modo de tentativa e erro; a busca global continua desativada.

Quando o corredor direto não está livre, estabelece uma direção lateral a partir dos candidatos de percepção. A orientação do contato usa o vetor para o objetivo, como aproximação local; não é uma normal de colisão medida. Mantém candidatos com pelo menos três metros livres à frente que não revertam o lado escolhido nem recuem excessivamente nessa orientação. Os bônus e custos existentes continuam selecionando entre esses candidatos.

Uma visão direta livre obtida apenas por recuo não encerra o contorno: é preciso também avançar pelo menos três metros na orientação do contato ou estar pelo menos 0,75 m mais próximo do destino do que no contato. Perto do objetivo, o corredor completamente verificado conserva o tratamento existente.

Quando não há candidato nessa direção, libera a tentativa de outro sentido a partir de alternativas fisicamente verificadas. Se nenhum corredor longo está livre, o seletor existente ainda pode tentar um passo curto permitido. Não força atravessar água, paredes ou terreno excessivamente alto.

O estado é temporário e pequeno: direção, orientação, origem do contato, distância e contadores. É descartado ao trocar rota ou objetivo, na recuperação e no encerramento do modo. Não é promovido a memória por si só. Os episódios continuam usando apenas movimentos efetivos e a contabilidade anterior de jornada.

## Memória e atribuição
A direção inicial usa os candidatos de percepção sem bônus de RAM ou de Memoria.ia. O mesmo conjunto de alternativas do contorno é usado na escolha real e nas comparações sem memória/sem RAM. A evidência do episódio identifica local_observed_contour e durable_learning=false. Não se atribui uma alteração dessa política à aprendizagem da Memoria.ia.

Os candidatos lembrados ainda precisam passar pelo sensor antes de seleção. Uma passagem invalidada continua sujeita à validação na execução e ao mecanismo existente de revisão. Não se fabricam falhas físicas a partir de rejeições só percebidas.

## Resultados isolados
- Versão anterior: não chegou em 2500 passos nos dois estados da parede.
- Correção: primeira abertura, 315 passos e nenhuma colisão.
- Abertura movida para o lado oposto: 1584 passos e nenhuma colisão. Nesse caso o caminho contornou a extremidade livre da parede; não afirmar que encontrou necessariamente a abertura nova.
- Rio: chegou ao destino passando pela faixa efetivamente caminhável da ponte, sem entrar em água proibida e sem busca global. O navegador não recebeu as coordenadas da ponte.
- Testes de direção inicial independente do bônus de memória, retenção após recuo, liberação com progresso e ausência de movimento forçado quando tudo é recusado.
- Suíte completa: 39 testes Godot passaram; teste dirigido repetido após acrescentar as verificações de política.

São testes físicos isolados. Ainda não foi medido o efeito da 008DZ na live, nem melhoria geral da Memoria.ia. A política não garante solução de todo labirinto: custos, recuperação segura e limite de jornada permanecem necessários.

## Instalação
Requer a 008DY instalada. O instalador exporta e valida Web com os 39 testes, copia apenas o novo auxiliar e nov_navigation_experience.gd ao renderer, reinicia, verifica o estado recente e promove a página. Faz backup e rollback de código e apresentação. Preserva memórias, encontros, animais e histórico das buscas. Uma busca em andamento pode ser encerrada pelo mecanismo de reinício.

```bash
sudo bash /home/etbra/apply-local-contour-008dz-root.sh
```

Recarregue a fonte da live depois. A release v0.1.0 permanece congelada.
