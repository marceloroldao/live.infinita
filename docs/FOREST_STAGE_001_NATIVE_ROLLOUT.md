# Visual 001 — publicação controlada do cenário florestal no renderer nativo

A composição visual foi integrada pela PR #107 e passou no CI com Godot
4.7.2, incluindo captura de biomas. Ela não reiniciou o servidor.
A VM tem o checkout em `/home/etbra/live.infinita`, enquanto o projeto
executado sob o usuário `liveinfinita` reside em
`/opt/live.infinita/apps/renderer-godot`.

O operador executa apenas:

```bash
cd ~/live.infinita && bash deploy/visual-forest-stage-001.sh
```

O wrapper executa `git pull --ff-only` como `etbra`, exige
`main` rastreada limpa e testes locais, solicita autenticação
`sudo -v` no terminal e aciona o instalador root com o commit exato.

O instalador recusa alterações se o broadcaster externo estiver ativo.
Guarda PIDs dos serviços de World State, API, áudio e relay; todos devem
continuar ativos com os mesmos PIDs. Cria backup root-only em
`/var/backups/live-infinita/forest-stage-001.*` e instala
**somente** `diorama.gd`, `forest_preview.gd` e
`forest_preview.tscn` no projeto nativo. Compila `diorama.gd`
isoladamente em projeto temporário para não reimportar recursos
enquanto o renderer está no ar. Reinicia apenas
`live-infinita-renderer.service`, aguarda nova instância e confirma
o sky otimizado, estabilidade de PID e ausência de erros de script.
Falha após o início da instalação restaura os três arquivos e
reinicia somente o renderer se necessário. O backup permanece para
inspeção/manual rollback.

Marcadores: `FOREST001_SOURCE_INSTALLED`,
`FOREST001_RENDERER_PARSE_OK`,
`FOREST001_NATIVE_DEPLOY_OK`,
`FOREST001_WORLD_AUDIO_UNCHANGED` e
`FOREST001_WEB_EXPORT_NOT_CHANGED`. Em erro:
`FOREST001_ROLLBACK_STARTED` e `FOREST001_ROLLBACK_OK`
ou `FOREST001_ROLLBACK_BLOCKED`.

**Limite do corte:** a atualização é do renderer nativo enviado ao
barramento de vídeo do servidor. O export Web atualmente publicado em
`/godot/` não muda; a prévia 3D separada não substitui `main.tscn`.
O próximo rollout deverá exportar o Web de um snapshot imutável, de
forma atômica e sem apagar a importação do processo nativo. Nenhuma
modificação no World State, memória, NPCs, TTS, transmissão externa
ou persistência é autorizada aqui.
