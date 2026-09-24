# MVP-001 — Protótipo Ubuntu Server

Objetivo: provar o ciclo mínimo **World State -> WebSocket -> Renderer Web** em uma VM Ubuntu Server sem desktop gráfico e sem GPU dedicada.

## Status

**Validado em VM Ubuntu Server real em 2026-09-10.**

Foram confirmados:

- serviço `live-infinita` ativo via `systemd`;
- `GET /api/health` respondendo `200 OK`;
- acesso externo ao runtime na porta `8080`;
- Nginx servindo o preview na porta `80`;
- WebSocket conectado no navegador;
- World State renderizando árvore e fogueira corretamente.

O IP da VM de validação não é registrado aqui por segurança operacional.

## O que este protótipo executa

- `world-runtime` em Python/FastAPI, escutando em `0.0.0.0:8080` durante a fase de testes.
- `WebSocket /ws` enviando o World State ao navegador.
- `GET /api/world` para inspeção do estado atual.
- `GET /api/health` para diagnóstico.
- `POST /api/simulate` para eventos determinísticos de teste.
- renderer Web em PixiJS, servido pelo próprio runtime.
- Nginx na porta `80`, fazendo proxy HTTP/WebSocket.
- serviço `systemd` chamado `live-infinita`.
- estado mínimo persistido em `examples/world-state.mvp001.json`.
- estado canônico de reset em `examples/world-state.mvp001.bootstrap.json`.

O renderer não é autoridade. O estado JSON é a fonte de verdade do protótipo.

## Requisitos da VM

- Ubuntu Server 22.04 LTS ou 24.04 LTS.
- acesso à Internet durante a instalação.
- porta TCP 80 liberada no firewall/security group.
- porta TCP 8080 liberada somente enquanto for desejado acesso direto ao runtime de testes.
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

Também é possível testar diretamente o runtime:

```text
http://IP_DA_VM:8080/api/health
http://IP_DA_VM:8080/api/world
```

## Simulator

O HUD do preview possui controles para gerar mudanças determinísticas no mundo:

- `+ visitante` — adiciona `person_01`;
- `mover árvore` — alterna a posição de `tree_01`;
- `acender/apagar fogo` — altera `properties.lit` de `fire_01`;
- `noite` — define `environment.period = night`;
- `dia` — define `environment.period = day`;
- `reset` — restaura o bootstrap canônico.

Cada ação passa pelo runtime, incrementa `world.version`, registra `last_event`, persiste o World State e só então transmite o novo estado aos clientes pelo WebSocket.

Também pode ser acionado pela API:

```bash
curl -X POST http://127.0.0.1:8080/api/simulate \
  -H 'Content-Type: application/json' \
  -d '{"action":"spawn_person"}'
```

Ações disponíveis: `spawn_person`, `move_tree`, `toggle_fire`, `set_night`, `set_day` e `reset`.

## Portas

| Porta | Exposição | Uso |
|---|---|---|
| 80/tcp | pública/LAN | Preview, API e WebSocket via Nginx |
| 8080/tcp | temporariamente pública/LAN | FastAPI/Uvicorn para diagnóstico direto do MVP |

Na implantação futura, a recomendação é voltar a restringir `8080` e expor somente Nginx/HTTPS.

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

O instalador atualiza `/opt/live.infinita` e reinicia os serviços.

## Limites intencionais do MVP-001

Este protótipo ainda não implementa TikTok/YouTube, LLM, TTS real, Memoria.ia, votação, autenticação do preview ou simulação física. Essas integrações ficam fora do caminho crítico desta prova.

O ciclo validado agora é:

```text
Simulator / futura Live
        |
        v
 evento determinístico
        |
        v
   world-runtime
        |
     valida/muta
        |
        v
 World State persistido
        |
        v
      WebSocket
        |
        v
   Renderer Web
```

O próximo incremento deve introduzir **Delta/Event Log explícito e replay**, antes de conectar fontes externas ou IA. Isso preserva a regra central: eventos propõem mudanças, o runtime valida, e o renderer apenas projeta o estado aprovado.
