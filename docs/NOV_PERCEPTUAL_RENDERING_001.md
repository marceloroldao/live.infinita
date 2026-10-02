# NOV Perceptual Rendering 001

## Decisão

A Live.infinita não deve apresentar o mundo como um mapa quase aéreo.

A câmera principal deve representar o mundo próximo da percepção de NOV:
visão em terceira pessoa próxima, sobre o ombro ou quase na altura dos olhos,
com horizonte baixo o suficiente para que árvores, pedras, relevo, água e
vegetação tenham escala percebida de dentro do ambiente.

NOV é um ser de tecnologia primitiva, equivalente a um estágio de vida próximo
aos tempos das cavernas. A experiência visual deve reforçar que ele habita e
atravessa o ambiente; ele não observa o mundo de cima como um operador.

## Princípio de renderização

O mundo persistente pode ser grande, mas o renderer não deve desenhar o mundo
inteiro.

Regra:

    World State + Memoria.ia + Environmental State
                        |
                        v
                  posição de NOV
                        |
                        v
               volume perceptível local
                        |
                        v
                   renderer

Somente a área potencialmente visível por NOV recebe geometria visual detalhada.
Regiões distantes permanecem no estado do mundo e na cognição, mas não precisam
estar materializadas no frame atual.

## Consequências

1. Câmera
   - abandonar enquadramento quase aéreo como câmera principal;
   - aproximar a câmera da altura de NOV;
   - priorizar sensação de caminhar dentro do terreno;
   - manter uma câmera de diagnóstico separada, se necessária, sem usá-la na live.

2. Vegetação
   - permitir densidade local muito maior;
   - árvores, arbustos, gramíneas, pedras e cobertura do solo devem aparecer em
     função das regras ambientais;
   - densidade visual deve ser alta perto de NOV e progressivamente simplificada
     com distância.

3. Culling
   - frustum culling e distância de visibilidade passam a ser parte central do
     orçamento;
   - objetos atrás de NOV ou muito distantes não devem consumir custo de
     detalhamento;
   - o renderer deve reconstruir ou reciclar lotes locais conforme NOV se move.

4. LOD
   - primeiro plano: maior densidade e leitura ecológica;
   - meio-termo: MultiMesh e geometrias simplificadas;
   - fundo: silhuetas, maciços, floresta agregada e atmosfera;
   - fora da percepção: estado lógico somente, sem obrigação de render.

5. Ambiente e cognição
   - cognição continua definindo a estrutura do mundo;
   - Environmental Rules define o que é plausível naquele local;
   - renderer materializa apenas a parte percebida por NOV;
   - a câmera não altera a realidade do mundo, apenas qual parte dela é
     visualmente realizada.

## Regra ecológica

Não usar densidade fixa de vegetação global.

A densidade visual local deve ser função de:

- environmental_state.vegetation_density;
- environmental_state.tree_suitability;
- soil_moisture;
- ecological_zone;
- rock_exposure;
- snow_cover;
- proximidade de água;
- distância em relação a NOV.

Assim, uma floresta pode ficar realmente fechada perto de NOV sem exigir que
milhares de árvores sejam renderizadas em todo o mapa.

## Próxima direção técnica

A partir da 008bf, a evolução visual deve priorizar:

    câmera perceptual de NOV
        -> raio visual local
        -> vegetação ambiental local densa
        -> LOD por distância
        -> culling agressivo fora do campo perceptível

A vista aérea permanece apenas como ferramenta de desenvolvimento/diagnóstico,
não como linguagem visual principal da Live.infinita.
