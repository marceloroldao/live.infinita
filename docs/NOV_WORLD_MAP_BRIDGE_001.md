# Visual 004 — Nov real no Vale de Nov (read-only, opt-in)

## Origem comprovada

O endpoint já existente `/ws` entrega `world_state` com
`delivery.mode=local_world_slice`,
`delivery.observer_entity_id=nov`, `delivery.observer={x,y}`,
`world.world_id`, `world.sequence` e
`world.interest.current_region_id`. A região atual vem do
World State/cold store. Não é necessário ler a Memoria.ia diretamente
nem acrescentar endpoint, serviço ou rota de escrita.

## Projeção explícita de demonstração

`nov_map_projection_001.json` liga apenas o mundo
`nov-live-autonomous-001` às três regiões existentes:
`shelter`, `clearing` e `deep_forest`, com âncoras conhecidas
`(930,390)`, `(640,360)` e `(350,340)`. As células
`[2,7]`, `[7,7]` e `[5,7]` são **somente apresentação**.
O fator 0,35 m/ unidade lógica não é uma conversão física medida.
Mudanças de região podem deslocar a câmera visualmente; esse mapa
não é a nova topologia autoritativa nem altera o caminho de Nov.

Pacotes com outro `world_id`, observador diferente, região não
mapeada, sequência repetida/retrógrada, números inválidos ou posição
muito afastada da âncora são ignorados. A única saída é a posição
visual 2D para x/z do Godot. Não há mensagens de saída da conexão,
mudança em arquivos, banco, evento ou World State.

## Operação

O tour original continua padrão. Para acompanhar Nov na prévia
**isolada**, depois da importação do projeto em snapshot:

```bash
godot --headless --path /tmp/SNAPSHOT/apps/renderer-godot \
    res://world_map_preview.tscn -- --follow-nov
```

O modo opt-in conecta-se ao `ws://127.0.0.1:8080/ws` na VM
(ou mesmo host `wss` em export Web). A prévia recebe apenas
`world_state`; quando falta dado novo por 15 s, o marcador congela
e exibe `pose_desatualizada`. Sem frame válido não executa o
tour automático e não inventa deslocamento. O renderer principal
`main.tscn` não importa o componente.

## Validação

- Testes Python do contrato e do isolamento.
- Smoke Godot puro com frames bons, duplicados, não mapeados e inválidos.
- Smoke Godot contra o WebSocket local por três segundos, com
  `--follow-nov` explícito.
- Log esperado: `NOV_MAP_FOLLOW_READ_ONLY_ENABLED`,
  `NOV_MAP_FOLLOW_ACCEPTED`, `NOV_MAP_FOLLOW_SMOKE_OK`.

Não publicar `/godot/`, não alterar serviço e não mesclar os PRs
empilhados antes do gate de CPU/FPS e inspeção visual humana.
O passo posterior é alinhar uma topologia espacial real do mapa à
origem autoritativa, substituindo as âncoras demonstrativas.
