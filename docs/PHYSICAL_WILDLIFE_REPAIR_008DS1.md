# Correção de suporte físico — 008DS1

A primeira instalação 008DS chegou ao renderer, mas não publicou animais no prazo. O instalador restaurou automaticamente a 008DR (`cf0d973`); renderer e runtime continuaram ativos. Os testes anteriores usavam um piso artificial sólido e não detectaram que o terreno real tinha somente mesh visual e consultas de altura para a caminhada de Nov.

## Correção

Cada terreno residente agora possui um collider formado pelos mesmos triângulos e alturas consolidadas do mesh. A orientação das faces é ajustada e ambos os lados participam da consulta. Camada 2: suporte de animais e oclusão visual. O corpo de Nov mantém máscara 1 e sua caminhada por altura já validada. O sensor de visão inclui as camadas 1 e 2, passando a considerar também o relevo como oclusor real.

Os animais usam máscaras 1+2 para movimento, camada 2 para suporte e visão de ameaça 1+2. A cápsula conserva 0,76 m de altura, com centro 0,43 m acima do chão e margem pequena. Os visuais são compensados em 5 cm para manter as patas próximas do solo. Isso evita a cápsula começar intersectando o terreno inclinado. A busca vertical de suporte admite diferenças locais de relevo sem atravessar chão: o resultado continua sendo um impacto físico. O habitat e os movimentos também respeitam a exclusão de rio/lago já usada pela vegetação.

Não cria chão artificial plano, não reposiciona animais para seguir Nov e não muda vértices já consolidados.

## Evidência

- Novo teste instancia o preview real sem piso artificial, compara altura visual/física, verifica normais e nascimento dos três animais, e exige deslocamento real.
- Teste isolado com pacote real de World State, sequência 401098: três coelhos nasceram e se moveram no terreno inferido inclinado. Após três segundos lógicos, um chegou à água e reduziu sua sede. Nenhuma escrita na Memoria.ia ou nos diretórios de produção ocorreu nessa reprodução.
- A suíte completa tem 34 testes Godot. Após a correção final de cápsula, os dois testes de fauna são repetidos; a reprodução do pacote real confirma movimento e consumo em encosta.

## Instalação

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-physical-wildlife-008ds1-root.sh
```

Sucesso: `008DS1_OK`. Log: `/home/etbra/008ds1-wildlife-rollout.log`. O instalador inclui o sensor de visão corrigido, espera até 60 segundos pela publicação inicial e mantém backup/rollback. O comando antigo 008DS encaminha para essa versão. População, recurso climático e aprendizagem não são recriados nem misturados.
