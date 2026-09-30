# Visual 001 — publicação atômica do preview Web

A floresta do PR #107 está publicada no renderer nativo; o preview
`https://live.etbra.com.br/godot/` ainda apresenta build antigo. Este
rollout é **exclusivamente Web**, não usa `deploy/update.sh` e não
reinicia World State, Godot nativo, áudio ou API.

## Contrato operacional

O operador (etbra, pelo próprio terminal) executa:

```bash
cd ~/live.infinita && bash deploy/visual-forest-web-rollout.sh
```

O wrapper exige checkout `main` limpo, faz fast-forward até
`origin/main`, executa testes de contrato e autentica `sudo -v`.
O root script fixa SHA completo e recusa alterações de checkout ou
live externa ativa. Os arquivos do projeto são extraídos do objeto
Git daquele SHA para snapshot descartável em `/var/tmp`; o comando
não toca na pasta `/opt/live.infinita/apps/renderer-godot/.godot`
usada pelo renderer nativo.

Godot 4.7.2 primeiro importa os assets do snapshot em prioridade baixa,
depois exporta Web para diretório isolado. O pacote precisa conter
`index.html`, `index.js`, `index.pck` e `index.wasm` e passar
o gate de erros de GDScript. O export é conferido antes de qualquer
troca do website. O `build.json` inclui `source_commit` completo
e `scenario=forest-stage-001`.

A publicação copia **sem modificar** a subpasta `nov-preview/`,
inclusive seu `build.json`, para a candidata. A candidata é preparada
com proprietário `www-data` e modos 0755/0644, no mesmo filesystem
do site. `nginx -t` deve passar; a pasta anterior é renomeada para
`/var/backups/live-infinita/forest-web-001.*/site` e a candidata
é promovida em seguida. Existe um intervalo curto entre os dois
renames. Uma falha depois de guardar a pasta anterior tenta restaurar
essa versão e valida o hash de `build.json`.

O resultado é verificado através do nginx local sob hostname real:
`/godot/build.json` deve conter o SHA esperado e os quatro arquivos
essenciais precisam responder HTTP 200/206. A identidade da prévia do
Nov deve permanecer igual. PIDs dos cinco serviços nativos são
comparados ao estado inicial; nenhum é reiniciado pelo script.

O arquivo de saída operacional é
`~/forest-web-rollout.log` (0600). Marcadores de sucesso:
`FOREST_WEB_SNAPSHOT_OK`, `FOREST_WEB_ASSETS_IMPORTED`,
`FOREST_WEB_EXPORT_OK`, `FOREST_WEB_CANDIDATE_READY`,
`FOREST_WEB_ATOMIC_PUBLISH_OK`,
`FOREST_WEB_NATIVE_WORLD_AUDIO_UNCHANGED` e
`FOREST_WEB_NOV_PREVIEW_PRESERVED`.

A página atualizada será
`https://live.etbra.com.br/godot/`; em celulares com versão antiga
em cache, usar aba anônima ou recarregamento completo. A seção
Simulador do gerenciamento usa o mesmo `/godot/`, mas continua
uma **prévia Web independente**: não recebe o stream UDP H.264 nativo
do renderer e pode exibir seu próprio estado visual do mundo.

## Limites

Passar no gate significa build/publicação Web com integridade e
manutenção dos serviços. Não significa que a prévia Web acompanhe
perfeitamente cada frame da captura nativa, nem que os assets 3D da
`forest_preview.tscn` estejam integrados ao `main.tscn`.
O broadcast atual permanece em 2D, com cenário de floresta melhorado;
a composição 3D segue protótipo isolado. Performance deve ser medida
antes de elevar a densidade dos elementos visuais.
