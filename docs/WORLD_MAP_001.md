# World Map 001 — Vale de Nov (preview isolado)

## Objetivo

Protótipo de um mapa explorável de 2.048 × 2.048 metros, composto por
1.024 setores lógicos de 64 × 64 metros. O manifesto
`apps/renderer-godot/world_map_001.json` mantém a planta e pontos de
interesse; a cena `world_map_preview.tscn` gera relevos e decorações
determinísticas com o catálogo Quaternius CC0 já incluído no projeto.

O roteiro visual preserva abrigo, bosque antigo, travessia do rio,
aldeia e mirante nas mesmas coordenadas físicas e acrescenta seis destinos
distantes: mirante da cachoeira, torre do norte, círculo de pedras, caverna
leste, pradaria sul e ruínas antigas. A ponte continua em x=32/z=-32; com a
malha 32×32 ela passa ao setor 16,15 sem mudar de lugar no mundo. A água não tem simulação hidráulica.
As casas agora recebem um collider simples nas paredes e a ponte dois
colliders laterais; árvores, pedras e plantas continuam sem corpos físicos
para preservar o orçamento. Em modo offline o marcador de Nov percorre a rota demonstrativa. Em modo
live ele segue `delivery.observer`, resolvido pelo SpatialSession a partir da
posição autoritativa de `nov`. O HUD expõe **EXPLORAR LOCAL**: esse modo
desacopla temporariamente o explorador visual da pose live, ativa controles
touch e usa um `CharacterBody3D` somente local. **VOLTAR AO NOV** restaura
a última pose autoritativa recebida. Entidades HOT/WARM são apenas marcadores visuais.
As regiões do mapa continuam sendo apresentação e não criam verdade paralela.

## Custos e limites

A prévia materializa até 3×3 setores, 9 malhas de relevo e no máximo
54 instâncias de decoração Quaternius. Trilha, água, casas, ponte e marcos
são geometria modular adicional somente nos setores ativos. Descarta
setores fora do raio, usa modelos do catálogo local e iluminação sem sombras. O resto do
território não possui nós ativos. O smoke headless ficou perto de 200 MB
de RSS; uma execução X11 isolada via Xvfb/llvmpipe, já com feed live, mediu
aproximadamente 440 MB de RSS e 28% de CPU no ponto amostrado.

A expansão 16×16 → 32×32 quadruplica apenas o espaço lógico (256 → 1.024
setores). O renderer continua materializando no máximo 3×3 setores, portanto
o teto visual permanece 9 setores / 54 decorações. Os segmentos de trilha
agora são descartados por bounding box antes da tesselação quando não cruzam
o setor ativo.

A dimensão do mundo não altera os tetos existentes do Spatial Resolver.
O overlay replica explicitamente os limites HOT 96 / WARM 192 e usa
`MultiMesh` para os marcadores, sem materializar a memória fria no Godot.
O SpatialSession entrega no máximo 16 descritores de região local
(região atual + vizinhas candidatas); o Godot os projeta como anéis de
48 segmentos. Colliders também são locais: máximo lógico de 3 por setor.

## Fronteira de segurança

A cena usa `/ws` exclusivamente como entrada. `world_map_live_feed.gd`
não envia `interest_update`, intents ou qualquer outro pacote; também não
escreve em banco, World State ou Memoria.ia. O servidor continua sendo a
autoridade e entrega uma fatia espacial bounded. O explorador local também
não envia comandos: água fora da ponte, limite do mapa, degrau máximo e
obstáculos são resolvidos somente no Godot. O mapa permanece fora de
`main.tscn`, portanto a transmissão nativa atual não é substituída.

## Validação isolada

Após importar os modelos em uma cópia independente do projeto:

```bash
python -m unittest -v tests.test_world_map_001
godot --headless --editor --quit --path /tmp/COPIA_ISOLADA
godot --headless --path /tmp/COPIA_ISOLADA res://world_map_preview.tscn --quit-after 3
```

O marcador offline esperado é `WORLD_MAP_PREVIEW_READY`, com 9 setores e
limite de 54 decorações. Com o runtime disponível deve aparecer também
`WORLD_MAP_LIVE_BOUND`, incluindo região, sequence, célula e contagens
HOT/WARM/regiões. O smoke de regiões/colisão confirmou 3 anéis persistentes,
2 corpos estáticos na ponte e 9 corpos estáticos ao materializar os 9 setores
da aldeia. O smoke de travessabilidade confirma água bloqueada fora da ponte,
ponte atravessável, casa bloqueada, modo live imune a input local, exploração
local física e retorno exato à pose autoritativa. O import no checkout usado
pelo renderer nativo não é permitido.
O rollout Web usa `/godot/world-map-preview/` e troca atômica independente.

## Evolução

1. Concluído: captura visual isolada e aferição inicial de CPU/RAM.
2. Concluído: pose autoritativa de Nov e overlay HOT/WARM somente leitura.
3. Concluído neste corte: regiões persistentes locais projetadas no mapa e
   primeira camada bounded de colisão em ponte/casas.
4. Concluído neste corte: locomoção física local, contrato de
   travessabilidade e controles touch separados da autoridade do NOV.
5. Concluído: expansão para 2.048 × 2.048 m / 1.024 setores e seis novos
   destinos, mantendo streaming 3×3 e coordenadas centrais compatíveis.
6. Próximo: enriquecer os novos destinos com eventos/ações locais sem criar
   autoridade paralela ao World State.
7. Depois: promover o mapa para a captura nativa por rollout independente.

Referências de assets: Quaternius Stylized Nature MegaKit (CC0) e
Medieval Village MegaKit (CC0). Terrain3D (MIT) fica como opção
futura se o servidor puder suportar sua estratégia de renderização.
