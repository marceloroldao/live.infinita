# World Map 001 — Vale de Nov (preview isolado)

## Objetivo

Protótipo de um mapa explorável de 1.024 × 1.024 metros, composto por
256 setores lógicos de 64 × 64 metros. O manifesto
`apps/renderer-godot/world_map_001.json` mantém a planta e pontos de
interesse; a cena `world_map_preview.tscn` gera relevos e decorações
determinísticas com o catálogo Quaternius CC0 já incluído no projeto.

O roteiro visual passa por abrigo, bosque antigo, travessia do rio,
aldeia e mirante. O corte cênico adiciona leito rebaixado com água,
ponte de madeira, trilhas conectando o percurso, cabanas modulares
na aldeia e marcos nos pontos de interesse. A água não é uma simulação
hidráulica e os objetos ainda não têm colisão ou ações. O marcador
do Nov é apenas um guia da câmera; não é a entidade autoritativa.
As regiões são uma proposta visual, não regiões persistidas no runtime.

## Custos e limites

A prévia materializa até 3×3 setores, 9 malhas de relevo e até
54 instâncias decorativas do catálogo. Trilha, água, ponte, cabanas
e marcos são geometria adicional somente nos setores ativos. O restante
não possui nós ativos. A renderização não usa sombras. CPU/FPS precisam
ser medidos antes da ligação à captura nativa.

A dimensão do mundo não altera os tetos existentes do Spatial
Resolver (HOT 96 / WARM 192 entidades), mas estes são limites de
estado, não prova de custo de renderização ou de busca em disco.

## Fronteira de segurança

A cena não usa WebSocket, não escreve em banco, não muda World State
nem Memoria.ia. Não é importada por `main.tscn`; transmissão e
prévia Web atuais permanecem em 2D até uma etapa separada e aprovada.

## Validação isolada

Após importar os modelos em uma cópia independente do projeto:

```bash
python -m unittest -v tests.test_world_map_001
godot --headless --editor --quit --path /tmp/COPIA_ISOLADA
godot --headless --path /tmp/COPIA_ISOLADA res://world_map_preview.tscn --quit-after 3
```

O marcador esperado é `WORLD_MAP_PREVIEW_READY`, com até 9 setores e
limite de 54 decorações do catálogo. Os casos `--preview-cell=8,7` e
`--preview-cell=11,9` verificam rio/ponte e aldeia sem mover a live.
O import no checkout usado pelo renderer nativo não é permitido.
Nenhum deploy está incluído neste corte.

## Evolução

1. Captura visual isolada, aferição de FPS e memória em CPU.
2. Integração real da pose de Nov e geometria de regiões HOT/WARM,
   mantendo a memória como estado e não como depósito de modelos.
3. Travessia física, casas modulares CC0 e pontos de interesse reais.
4. Publicação Web/nativa em rollout independente com rollback.

Referências de assets: Quaternius Stylized Nature MegaKit (CC0) e
Medieval Village MegaKit (CC0). Terrain3D (MIT) fica como opção
futura se o servidor puder suportar sua estratégia de renderização.
