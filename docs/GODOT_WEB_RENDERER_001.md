# Godot Web Renderer 001

## Objetivo
Adicionar Godot como renderer alternativo do Live.infinita sem substituir o renderer web já validado.

## Princípio
Godot não é autoridade do mundo. Ele recebe o mesmo `World State` pelo mesmo WebSocket `/ws` e apenas projeta visualmente entidades e ambiente.

## Fluxo
`World Runtime -> /ws -> Godot Web -> navegador`

## Primeira cena
- clareira 2D;
- árvore;
- fogueira com estado `lit`;
- visitante humano;
- mudança dia/noite;
- narração textual;
- painel com status WebSocket, versão e sequência do World State.

## Execução em servidor headless
O servidor não precisa de desktop. O projeto é exportado com Godot em modo `--headless` para Web e servido pelo Nginx em `/godot/`.

## Instalação
1. instalar normalmente a branch com `sudo bash deploy/install-ubuntu.sh`;
2. exportar o Godot Web com `sudo bash deploy/install-godot-web.sh`;
3. abrir `http://IP_DA_VM/godot/`.

O preview clássico permanece em `http://IP_DA_VM/`.

## Versão do engine
Prototype fixado em Godot 4.7.2 stable para reprodutibilidade.

## Critério de validação
- `/godot/` carrega no navegador;
- status muda para `conectado`;
- árvore/fogueira/visitante refletem `/api/world`;
- comandos já existentes (`dia`, `noite`, `+ visitante`, etc.) atualizam o Godot via WebSocket;
- `/api/replay/verify` permanece `ok=true`.
