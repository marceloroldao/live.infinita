# Animais físicos — 008DS

A instalação inicial foi revertida automaticamente. Use a correção 008DS1 descrita em `PHYSICAL_WILDLIFE_REPAIR_008DS1.md`, que adiciona os colliders do terreno real e corrige a cápsula em encostas.

Primeiro habitat: três coelhos de baixa complexidade gráfica, uma pequena poça e uma área de alimento. O renderer nativo do servidor é o único simulador autorizado. Navegadores recebem a projeção dessa mesma população e não geram animais nem executam suas necessidades.

## Comportamento e limites

Fome e sede aumentam durante o tempo lógico ativo. Os agentes procuram os recursos, reduzem a necessidade quando chegam, descansam e fogem de Nov a menos de 9 m somente quando um raio físico confirma sua visão. Comer e beber completados são contados; não basta selecionar o destino. Esse comportamento é programado, não aprendizagem dos animais.

Cápsulas reais colidem com obstáculos. Antes de avançar, consultam suporte físico, inclinação e diferença de altura. Até oito direções locais são tentadas; não há busca global de caminhos. Os agentes permanecem num raio de 20 m do habitat. O terreno e os objetos não são alterados por eles.

O habitat é escolhido uma vez em chão sólido próximo de Nov e conservado no checkpoint. Não reaparece em outro lugar para acompanhar Nov. Quando ele está a mais de 42 m do habitat, a simulação dos animais fica suspensa, pois só há física confiável nos setores carregados. Não há simulação fora da região nem recuperação de horas de fisiologia após desligamento. Isso é uma população piloto local, não fauna distribuída em todo o mapa.

A poça e a área de alimento são recursos explícitos visíveis, ainda sem esgotamento, regeneração, chuva, ecossistema ou reprodução. Não são inferências da Memoria.ia. Os modelos são gerados por código, com pernas animadas e cabeça abaixada ao consumir.

## Autoridade, persistência e visão

O serviço do renderer recebe caminhos explícitos por um drop-in. Sem esses caminhos, um renderer nativo de desenvolvimento não cria uma população paralela. O modo `--offline-tour` também desativa a autoridade.

Checkpoint: `/var/lib/live-infinita/wildlife/state.json`, arquivo 0600 em diretório 0700, envelope com SHA-256 e substituição atômica. Guarda mundo, identidades, posições, habitat, necessidades, fase comportamental e contadores. Corrupção ou outro mundo interrompe a população em vez de recriá-la silenciosamente.

A projeção de exibição é publicada somente depois do checkpoint em `/var/www/live-infinita-godot/wildlife/state.json`, 0644, a cada aproximadamente 0,5 s. Continua com heartbeat quando o relógio pausa, sem avançar os animais. O Web lê essa projeção, rejeita estados antigos, recuo de sequência/tempo e posições fora do habitat. A exibição Web usa poses do servidor a dois hertz; o vídeo nativo tem movimento contínuo. Não há extrapolação de animais ocultos para decisões de Nov.

Essas posições globais são um canal de renderização para a audiência, não observações de Nov. Cada coelho é cadastrado no sensor 008DR; consumidores de Nov recebem somente `visible_entities` confirmadas por alcance, cone e oclusão. As identidades e a espécie são rótulos do cadastro, não reconhecimento visual aprendido.

Não há caça, busca dirigida a animais, memória de avistamentos, previsão de presença, captura ou alegação de melhoria de aprendizagem nesta etapa. O próximo passo é registrar encontros observados e buscas delimitadas, sem misturar a projeção global com as experiências do agente.

## Validação e instalação

O teste `godot_wildlife_008ds_smoke.gd` usa física real: nascimento em solo válido, consumo com chegada, oclusão de ameaça, fuga, parede sólida, chão ausente, pausa, suspensão fora do habitat, retomada do checkpoint, permissões, corrupção, réplica do servidor e rejeição de estados inválidos. 33 testes Godot headless passaram. A suíte de regressão inclui percepção, câmera, caminhada, colisões, ponte/água, terreno, jornadas, recuperação, céu e clima.

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-physical-wildlife-008ds-root.sh
```

Sucesso: `008DS_OK`. O instalador exige checkout limpo, exporta com testes, guarda backup e configura somente o renderer para a nova população. Valida população nativa persistida, permissões e publicação HTTPS antes de concluir. Em falha, restaura renderer, drop-in e páginas; conserva checkpoint para diagnóstico. Não reinstala runtime nem serviços climáticos e não escreve na Memoria.ia.

A inspeção visual em OpenGL com Mesa llvmpipe mostrou os três coelhos, olhos, orelhas, caudas e pernas articuladas. Quadro de evidência: `physical-wildlife-008ds.png`.
