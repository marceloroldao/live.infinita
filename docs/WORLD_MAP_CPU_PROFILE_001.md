# Visual 005 — perfil CPU do Vale de Nov

## Objetivo

Medir a prévia 3D do Vale de Nov na VM atual, sem GPU dedicada, enquanto
ela acompanha a pose real de Nov pelo WebSocket read-only. Os testes foram
executados em Xvfb com Mesa llvmpipe, prioridade `nice 19`, sem restart
ou cutover do renderer de produção.

O renderer operacional atual permanece em 720x1280, captura 15 FPS e
Godot alvo 20 FPS. O perfil abaixo é apenas para a cena 3D experimental.

## Diagnóstico medido

| Corte | Resolução | Geometria | FPS médio | RSS pico |
| --- | --- | --- | ---: | ---: |
| base | 720x1280 | 9 setores, até 54 glTF | 7,62 | 557256 KiB |
| decor reduzida | 720x1280 | 9 setores, até 27 glTF | 8,46 | 378388 KiB |
| sem glTF | 720x1280 | 9 setores, sem decoração de catálogo | 14,54 | 273852 KiB |
| 360p vertical | 360x640 | 9 setores, até 27 glTF | 13,21 | 365676 KiB |
| 9 detalhes | 360x640 | até 9 glTF | 18,43 | 339804 KiB |
| proxies MultiMesh | 360x640 | até 9 glTF + 45 proxies | 16,80 | 376600 KiB |
| LOD central | 320x568 | 1 glTF + até 45 proxies | 18,17 | 343284 KiB |

Os números são amostras curtas na VM em operação e não são um SLA.
A carga do host e as mudanças de região de Nov variam entre amostras.

## Perfil escolhido para continuação

`--server-low-spec` mantém até 9 setores visuais em memória, mas só o
setor onde a projeção de Nov está localizada recebe 1 instância detalhada
Quaternius. Os vizinhos usam árvores proxy determinísticas: troncos e
copas low-poly agrupados em MultiMesh, sem shading. O teto de proxies é
45 (5 por setor).

Mudanças de célula usam uma fila de streaming de 1 setor por frame.
Isso evita construir todos os setores novos no mesmo frame. A troca do
único detalhe também segue o setor focal.

A resolução interna recomendada para a próxima prévia nativa isolada é
320x568, formato 9:16. Escalar isso para 720x1280 deverá ser feito fora
da cena, no pipeline de captura, e ainda não está ligado à produção.

Exemplo isolado:

```bash
godot --resolution 320x568 --path /tmp/SNAPSHOT/apps/renderer-godot \
  res://world_map_preview.tscn -- \
  --follow-nov --server-low-spec --benchmark-seconds=10 --benchmark-fps=20
```

## Gate

O perfil superou em média a captura de 15 FPS na amostra de 320x568,
mas ainda foram observados frames com delta máximo de 150 ms durante
transições. Portanto este corte **não autoriza** substituir o renderer
de produção. O próximo gate deve validar visualmente a prévia, medir uma
janela maior e provar o upscale/captura antes de qualquer rollout.

Nos benchmarks, o PID do `live-infinita-renderer.service` permaneceu
262582 e `NRestarts=0` antes/depois das execuções registradas.
