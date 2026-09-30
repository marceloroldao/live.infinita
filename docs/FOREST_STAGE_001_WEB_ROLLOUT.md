# Visual 001 — publicação do preview Web florestal

A Live nativa já exibe a floresta; o build público do navegador ainda
tem `source_commit=65c13e9` (28/09/2026). O endereço existente
`https://live.etbra.com.br/godot/` é um export Godot Web independente
e inclui `/godot/nov-preview/`, que não pode ser sobrescrito.

## Operação no celular

Após CI e merge:

```bash
cd ~/live.infinita && bash deploy/visual-forest-web.sh
```

O wrapper, executado por `etbra`, faz `git pull --ff-only`, exige a
`main` rastreada limpa, executa gates visuais e solicita `sudo -v`
no terminal. Não rodar o wrapper inteiro como root.

O script root recebe o SHA completo, verifica que o `diorama.gd`
nativo instalado coincide com a `main`, confirma serviços existentes
e gera uma cópia **apenas dos arquivos públicos do projeto Godot
contidos naquele objeto Git** com `git archive` em
`/var/tmp/live-forest-web-project.*`. Não usa o cache mutável
`/opt/live.infinita/apps/renderer-godot/.godot`, nem altera qualquer
arquivo da cena nativa executando em Xvfb. Importa e exporta a cópia
isolada via Godot 4.7.2, em prioridade CPU/IO reduzida.

O artefato gerado é conferido (`index.html`, `index.js`,
`index.wasm` e `index.pck`). Copia a árvore `nov-preview`
atual e compara seu `index.pck` SHA256 e `build.json` antes de
publicar. Grava `build.json` com SHA completo e
`forest_stage=visual-001`, prepara toda a árvore em um diretório
privado irmão de `/var/www/live-infinita-godot`, sem editar
o site público aos poucos.

A troca usa duas renomeações no mesmo filesystem; pode haver um breve intervalo de 404 entre elas, mas nenhuma atualização parcial do pacote. Salva a versão anterior sob
`/var/www/.live-infinita-godot.backup.*/site` (backup root-only,
**não servido pelo nginx**) e move a nova árvore para o caminho
público no mesmo filesystem. O script verifica, pela rota nginx
local com Host/SNI reais, o `build.json`, tamanho de
`index.pck` e preservação da prévia Nov. Confirma que World State,
API, renderer nativo, áudio, relay e Memoria.ia mantêm exatamente
os mesmos MainPIDs e estado ativo. **Não reinicia, habilita ou recarrega
serviços**; não altera config nginx nem suas rotas existentes.

Se uma verificação falhar após a troca, remove a nova árvore da
rota pública por `mv` e restaura a anterior. Em rollback bloqueado,
guarda ambas no diretório privado para investigação, sem apagá-las.

Marcadores finais esperados: `FOREST001_WEB_IMPORT_OK`,
`FOREST001_WEB_EXPORT_OK`, `FOREST001_WEB_RENAME_SWAP_OK`,
`FOREST001_WEB_PUBLISHED`, `FOREST001_NOV_PREVIEW_PRESERVED`,
`FOREST001_NO_SERVICE_RESTART` e `FOREST001_WEB_BACKUP_PATH`.
Falhas retornam status não zero e nunca são tratadas como sucesso.

## Endereços depois da publicação

- `https://live.etbra.com.br/godot/` — cenário Web principal com floresta.
- `https://live.etbra.com.br/godot/build.json` — versão e momento da publicação.
- `https://live.etbra.com.br/godot/nov-preview/` — prévia Nov original, sem alterações.
- `https://live.etbra.com.br/manage/` → **Simulador → Mundo ao vivo**
  usa o mesmo `/godot/`.

A cena `forest_preview.tscn` com os 38 modelos Quaternius permanece
**prévia 3D isolada**, não é a cena carregada automaticamente no URL
principal. A Live principal continua usando o Godot Node2D e a cena
florestal visual já verificada no renderer nativo.

Importação Web pode reduzir temporariamente os FPS da Live na VM sem
GPU; a prioridade de processo é reduzida, mas o export não constitui
teste de desempenho do browser. Após publicação, observar CPU, FPS e
carregamento no navegador, inclusive Chrome/Edge.
