# Forest Web 001 — publicação segura da floresta em /godot/

O renderer nativo já está com a floresta (merge #107 e rollout #108,
HTTP /api/health 200). O navegador continua com o build anterior
(65c13e9, 28/09). O plano é atualizar **somente a publicação estática
Web**, sem executar o instalador geral, sem alterar o projeto nativo
em /opt, sem limpar sua pasta .godot e sem reiniciar qualquer serviço.

O comando do operador, após o merge e CI:

```bash
cd ~/live.infinita && bash deploy/visual-forest-web.sh
```

O wrapper roda Git e os testes como etbra e solicita a senha sudo no
próprio terminal. O root script exige main atual e checkout rastreado
limpo, broadcaster externo inativo e todos os serviços importantes
ativos. Guarda os PIDs desses serviços; um reinício involuntário bloqueia
a publicação.

A montagem Web é derivada de um `git archive` do commit exato em
`/var/tmp`, nunca do diretório de produção. Importação dos glTF e
export Web são executados sob prioridade `nice 19`, com timeout,
depois validados quanto a erros de script, HTML, JS, WASM e PCK.
A cena exportada permanece `main.tscn`, que é 2D; a composição 3D
`forest_preview.tscn` segue independente. O diretório temporário
já é removido pelo rollback/sucesso.

O release estático novo é preparado no mesmo filesystem de /var/www,
incluindo uma cópia inalterada do atual `/godot/nov-preview/`, se
presente. A publicação move a pasta Web antiga para
`/var/backups/live-infinita/forest-web-001.*/previous` e em seguida
renomeia a nova pasta para o caminho servido pelo Nginx.
**Existe uma janela muito curta de troca de diretórios**; um navegador
que já estava no export antigo pode precisar atualizar a página, porque
os recursos Godot mantêm nomes como index.pck. Não é um deploy
atômico multiarquivo para sessões antigas.

Após a troca, confere pela URL local Nginx
`/godot/build.json` o commit completo/visual_stage, HTTP dos recursos
Web, preview Nov preservado e PIDs anteriores de mundo, renderer,
API e áudio. Qualquer falha reverte o diretório Web anterior e verifica
o hash do build.json original. O backup é mantido após sucesso.
Não há modificação do Nginx nem systemctl restart/reload.

Marcadores esperados: `FOREST_WEB_ISOLATED_SOURCE_OK`,
`FOREST_WEB_IMPORT_OK`, `FOREST_WEB_ARTIFACT_OK`,
`FOREST_WEB_RELEASE_READY`, `FOREST_WEB_PUBLICATION_SWITCHED`,
`FOREST_WEB_PUBLISHED_OK`,
`FOREST_WEB_WORLD_RENDERER_AUDIO_UNCHANGED`,
`FOREST_WEB_BACKUP_PATH`.

Resultado a verificar do celular:

- https://live.etbra.com.br/godot/
- https://live.etbra.com.br/godot/build.json
- https://live.etbra.com.br/manage/ → Simulador → Mundo ao vivo.

Este é o preview Web; **não** é uma retransmissão da captura nativa
da porta UDP 5600, que permanece somente no servidor. A experiência
Web depende da inicialização do Godot no navegador e do stream de
World State pelo endpoint existente. Nenhum asset, mapa ou memória
foi gravado na Memoria.ia neste rollout.
