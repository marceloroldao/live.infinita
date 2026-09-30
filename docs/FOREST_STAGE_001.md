# Forest Stage 001 — cenário visual da Live Infinita

## Escopo entregue

A cena **principal** `main.tscn` continua o broadcast retrato 720×1280
em Node2D. Seu `Diorama` ganhou um corredor florestal em perspectiva,
árvores/copa em camadas, pedras e samambaias com balanço pelo vento já
existente. Tudo é desenhado com orçamento fixo e matemática determinística:
17 árvores decorativas, 19 pedras, 25 pequenas moitas e um corredor
com 23 pontos de cada lado. Os objetos não são entidades persistentes,
não ganham IDs e **não entram na Memoria.ia**. Árvores materializadas
continuam vindo somente do World State. O peso de bioma `forest`
controla a composição; transições para campo/rio/aldeia esmaecem o
elemento novo conforme o misturador visual existente. Dia/noite e
paralaxe da câmera permanecem ativos. Não há downloads, malha glTF
ou nova fonte de estado na renderização 2D.

Uma **prévia separada 3D** é oferecida em `forest_preview.tscn`.
Ela usa o catálogo Standard/CC0 do Quaternius já versionado no
repositório, com até 38 instâncias de árvores, rochas e plantas,
além de trilha simples e iluminação sem sombras. Não é um mundo
simulado: posições são fixas, modelos repetidos vêm de cache
de recursos e a cena não lê WebSocket, servidor ou banco. O contador
`FOREST_PREVIEW_READY` e o letreiro deixam claros modelos
indisponíveis/importação pendente. Não há alteração de
`run/main_scene`, uso de SubViewport ou troca da live para 3D.

## Verificação

```bash
python -m unittest -v tests.test_forest_stage_001 tests.test_quaternius_nature_importer
GODOT=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
"$GODOT" --headless --editor --quit --path apps/renderer-godot
"$GODOT" --headless --path apps/renderer-godot res://forest_preview.tscn --quit-after 3
"$GODOT" --headless --path apps/renderer-godot --script ../../tests/godot_presentation_smoke.gd
```

No servidor, a visualização real do broadcast segue o renderer
Godot nativo existente; a prévia 3D pode ser aberta separadamente
com `"$GODOT" --path apps/renderer-godot res://forest_preview.tscn`
em uma sessão X11 independente (não usar `:99` ocupado pela Live).
A CI executa o parser GDScript, a prévia 3D isolada e o smoke nativo
do cenário principal. Não reiniciar a unidade de produção
automaticamente pelo merge. A publicação do novo 2D requer um
rollout controlado pelo operador para o runtime
`/opt/live.infinita/apps/renderer-godot`, com validação do preview
e rollback. O checkout do GitHub sozinho não modifica a cena da Live.

## Próximo corte — visual 3D conectado

Depois da aprovação humana das capturas, escolher um renderizador 3D
servidor-side ou composição por SubViewport, medir FPS/CPU no
mesmo servidor **sem GPU**, adotar câmeras/biomas contínuos e
materializar só a região próxima ao Nov. Não converter o catálogo em
World State nem armazenar glTF na Memoria.ia. A memória retém eventos
e relações observadas; o renderer continua uma projeção do estado.
