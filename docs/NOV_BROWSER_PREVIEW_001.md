# Nov 3D — prévia no navegador

A transmissão Godot atual fica em https://live.etbra.com.br/godot/ e usa a
cena principal 2D. Esta prévia é exportada separadamente usando a cena
res://nov_character_preview.tscn.

## Publicar no servidor existente

O Nginx já usa /godot/ como alias para /var/www/live-infinita-godot/.
O novo script publica APENAS o subdiretório nov-preview/. Ele clona o projeto
Godot para um diretório temporário, substitui a cena inicial só nessa cópia,
importa modelos, exporta Web, valida index.html/.wasm/.pck e publica a prévia.

No terminal do servidor:

    cd ~/live.infinita
    git fetch origin
    git switch main
    git pull --ff-only origin main
    sudo bash deploy/export-nov-preview-web.sh

Abra no PC ou celular:

    https://live.etbra.com.br/godot/nov-preview/

Confirme os arquivos e a resposta HTTP:

    sudo test -s /var/www/live-infinita-godot/nov-preview/index.html
    sudo test -s /var/www/live-infinita-godot/nov-preview/build.json
    curl -kI https://live.etbra.com.br/godot/nov-preview/

O exportador depende da engine Godot e dos templates Web já instalados em
/opt/live-infinita-godot/ pelo instalador deploy/install-godot-web.sh.
Ele aborta sem alterar nada quando a publicação principal /godot/ não existe.

## O que será visível

- Elementos naturais 3D do Quaternius já versionados no GitHub.
- Nov provisória: placeholder em forma de cápsula, identificado na tela.
- O corpo Universal Base Characters Standard e animações ainda não estão
  incorporados. Importação e retargeting serão etapas separadas.

Esta é uma demonstração visual independente; ela não usa o estado cognitivo
em tempo real, não altera World State nem controla a simulação autônoma.

## Isolamento e atualização

- A cena principal original continua como main.tscn; nenhum script a modifica.
- Sem alteração do Nginx, restart de serviços ou escrita em cold-store.
- Erro de import/export mantém a live e a prévia anterior intactas.
- O exportador principal preserva /nov-preview/ ao usar rsync --delete.
- Godot Web exige WebAssembly e WebGL 2.0 no navegador.
- Há suporte a PROJECT_DIR, WEB_ROOT, GODOT_ENGINE_ROOT e
  LIVE_INFINITA_SOURCE_SHA para instalações não padronizadas.
