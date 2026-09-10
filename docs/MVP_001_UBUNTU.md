# MVP-001 — Protótipo Ubuntu Server

Objetivo: provar o ciclo mínimo **World State -> WebSocket -> Renderer Web** em uma VM Ubuntu Server sem desktop gráfico e sem GPU dedicada.

## O que este protótipo executa

- `world-runtime` em Python/FastAPI, escutando somente em `127.0.0.1:8080`.
- `WebSocket /ws` enviando o World State ao navegador.
- `GET /api/world` para inspeção do estado atual.
- `GET /api/health` para diagnóstico.
- renderer Web em PixiJS, servido pelo próprio runtime.
- Nginx na porta `80`, fazendo proxy HTTP/WebSocket.
- serviço `systemd` chamado `live-infinita`.
- estado mínimo persistido em `examples/world-state.mvp001.json`.

O renderer não é autoridade. O estado JSON é a fonte de verdade do protótipo.

## Requisitos da VM

- Ubuntu Server 22.04 LTS ou 24.04 LTS.
- acesso à Internet durante a instalação.
- porta TCP 80 liberada no firewall/security group.
- acesso autenticado ao repositório privado `marceloroldao/live.infinita` para o clone inicial.

Não é necessário instalar GNOME, KDE, X11, Wayland ou outro ambiente gráfico.

## Instalação

Na VM, clone a branch usando sua autenticação GitHub já configurada. Exemplo via SSH:

```bash
git clone --branch mvp/ubuntu-prototype-001 git@github.com:marceloroldao/live.infinita.git
cd live.infinita
sudo bash deploy/install-ubuntu.sh
```

Se você usa HTTPS autenticado, clone normalmente por HTTPS e depois execute o mesmo instalador.

O instalador copia o checkout para `/opt/live.infinita`, cria o ambiente Python, instala FastAPI/Uvicorn, configura Nginx e ativa o serviço no boot.

## Teste

Na própria VM:

```bash
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/world
systemctl status live-infinita --no-pager
systemctl status nginx --no-pager
```

De outro computador, abra:

```text
http://IP_DA_VM/
```

O navegador deve mostrar uma clareira simples contendo uma árvore e uma fogueira animada. O HUD deve indicar `conectado` quando o WebSocket estiver ativo.

Também é possível testar:

```text
http://IP_DA_VM/api/health
http://IP_DA_VM/api/world
```

## Portas

| Porta | Exposição | Uso |
|---|---|---|
| 80/tcp | pública/LAN | Preview, API e WebSocket via Nginx |
| 8080/tcp | localhost | FastAPI/Uvicorn; não precisa ser exposta externamente |

## Logs e diagnóstico

```bash
journalctl -u live-infinita -f
sudo nginx -t
curl -v http://127.0.0.1:8080/api/health
```

## Atualização manual do MVP

Atualize seu checkout autenticado e rode o instalador novamente:

```bash
cd ~/live.infinita
git pull
sudo bash deploy/install-ubuntu.sh
```

O `rsync` atualiza `/opt/live.infinita` e o instalador reinicia os serviços.

## Limites intencionais do MVP-001

Este protótipo ainda não implementa TikTok/YouTube, LLM, TTS real, Memoria.ia, votação, autenticação do preview ou simulação física. Essas integrações ficam fora do caminho crítico desta prova.

A primeira validação é somente:

```text
World State versionado
        |
        v
   world-runtime
        |
        v
     WebSocket
        |
        v
   Renderer Web
        |
        v
 árvore + fogueira
```

Depois que este ciclo estiver validado na VM, o próximo incremento deve adicionar eventos/deltas mutáveis e um Simulator antes de conectar fontes externas ou IA.
