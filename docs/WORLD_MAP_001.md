# World Map 001 — Vale de Nov (preview isolado)

## Objetivo

Protótipo de um mapa explorável de 1.024 × 1.024 metros, composto por
256 setores lógicos de 64 × 64 metros. O manifesto
`apps/renderer-godot/world_map_001.json` mantém a planta e pontos de
interesse; a cena `world_map_preview.tscn` gera relevos e decorações
determinísticas com o catálogo Quaternius CC0 já incluído no projeto.

O roteiro visual passa por abrigo, bosque antigo, travessia do rio,
aldeia e mirante. O segundo corte adiciona água superficial no leito
rebaixado, ponte visual no setor 8,7, trilhas locais, cabanas modulares,
praça e marcos com letreiros. A água não tem simulação hidráulica; casas,
ponte e caminhos ainda são geometria sem colisão ou ações. Em modo
offline o marcador de Nov percorre a rota demonstrativa; em modo live ele
segue `delivery.observer`, resolvido pelo SpatialSession a partir da posição
autoritativa de `nov`. Entidades HOT/WARM são apenas marcadores visuais.
As regiões do mapa continuam sendo apresentação e não criam verdade paralela.

## Custos e limites

A prévia materializa até 3×3 setores, 9 malhas de relevo e no máximo
54 instâncias de decoração Quaternius. Trilha, água, casas, ponte e marcos
são geometria modular adicional somente nos setores ativos. Descarta
setores fora do raio, usa modelos do catálogo local e iluminação sem sombras. O resto do
território não possui nós ativos. O smoke headless ficou perto de 200 MB
de RSS; uma execução X11 isolada via Xvfb/llvmpipe, já com feed live, mediu
aproximadamente 440 MB de RSS e 28% de CPU no ponto amostrado.

A dimensão do mundo não altera os tetos existentes do Spatial Resolver.
O overlay replica explicitamente os limites HOT 96 / WARM 192 e usa
`MultiMesh` para os marcadores, sem materializar a memória fria no Godot.

## Fronteira de segurança

A cena usa `/ws` exclusivamente como entrada. `world_map_live_feed.gd`
não envia `interest_update`, intents ou qualquer outro pacote; também não
escreve em banco, World State ou Memoria.ia. O servidor continua sendo a
autoridade e entrega uma fatia espacial bounded. O mapa permanece fora de
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
HOT/WARM. O import no checkout usado pelo renderer nativo não é permitido.
O rollout Web usa `/godot/world-map-preview/` e troca atômica independente.

## Evolução

1. Concluído: captura visual isolada e aferição inicial de CPU/RAM.
2. Concluído: pose autoritativa de Nov e overlay HOT/WARM somente leitura.
3. Próximo: alinhar as regiões persistentes ao mapa e adicionar travessia
   física/colisões sem dar autoridade ao renderer.
4. Depois: promover o mapa para a captura nativa por rollout independente.

Referências de assets: Quaternius Stylized Nature MegaKit (CC0) e
Medieval Village MegaKit (CC0). Terrain3D (MIT) fica como opção
futura se o servidor puder suportar sua estratégia de renderização.
